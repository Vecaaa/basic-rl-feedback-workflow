#!/usr/bin/env python3
"""
run_llm.py – Minimal Two-Stage LLM Driver (Generate / Analyze / Repair)

Modes (--task):
1. generate : PROMPT → code_i.c
   - Used in Iteration 1.
   - Model = Fixer (controlled by external scripts via the MODEL environment variable)

2. analyze  : CURRENT_CODE + FEEDBACK → repair_prompt_i.txt
   - Used in Iteration 2+ (Step 1).
   - Model = Analyzer

3. repair   : CURRENT_CODE + REPAIR_PROMPT → code_i.c
   - Used in Iteration 2+ (Step 2).
   - Model = Fixer
"""

import os
import sys
import re
import json
import argparse
from pathlib import Path

import torch
from transformers import AutoTokenizer, AutoModelForCausalLM

# ==========================================================
# argparse
# ==========================================================
parser = argparse.ArgumentParser()
parser.add_argument(
    "--task",
    choices=["generate", "analyze", "repair"],
    default="generate",
    help="Task mode: generate (initial), analyze (create repair prompt), repair (apply fix)",
)
parser.add_argument(
    "--only",
    nargs="*",
    help="Only process specified indices (e.g. 1 3 5).",
)
args = parser.parse_args()
ONLY_SET = {str(x) for x in (args.only or [])}
TASK = args.task

# ==========================================================
# HF cache setup
# ==========================================================
user = os.environ.get("USER") or "user"
cache_dir = os.environ.get("HF_CACHE", f"/scratch/{user}/hf_cache")
os.makedirs(cache_dir, exist_ok=True)

os.environ["HF_HOME"] = cache_dir
os.environ["TRANSFORMERS_CACHE"] = cache_dir
os.environ["HF_HUB_CACHE"] = cache_dir
os.environ["HF_DATASETS_CACHE"] = cache_dir

LOCAL_ONLY = os.environ.get("HF_LOCAL_ONLY", "0") == "1"

# ==========================================================
# Load config / model
# ==========================================================
try:
    with open("config.json", "r") as f:
        config = json.load(f)
except FileNotFoundError:
    config = {}

model_path = os.environ.get("MODEL", config.get("MODEL_PATH", ""))
if not model_path:
    print("❌ MODEL_PATH missing in config.json and env MODEL not set.")
    sys.exit(1)

subset_size = int(config.get("subset_size", 10))
max_new_tokens = int(config.get("max_new_tokens", 512))

device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Task        : {TASK}")
print(f"Using model : {model_path}")
print(f"Device      : {device}")

tokenizer = AutoTokenizer.from_pretrained(
    model_path,
    trust_remote_code=True,
    cache_dir=cache_dir,
    local_files_only=LOCAL_ONLY,
)

# Prevent chat templates from interfering
if getattr(tokenizer, "chat_template", None):
    tokenizer.chat_template = None

if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token

model = AutoModelForCausalLM.from_pretrained(
    model_path,
    trust_remote_code=True,
    cache_dir=cache_dir,
    local_files_only=LOCAL_ONLY,
    dtype=torch.float16 if device == "cuda" else torch.float32,
    device_map="auto",
)


# ==========================================================
# Basic utility functions
# ==========================================================
def run_model_prompt(prompt: str, max_tokens: int | None = None) -> str:
    """Minimal wrapper: take plain text input and return plain text output."""
    if max_tokens is None:
        max_tokens = max_new_tokens

    enc = tokenizer(
        prompt,
        return_tensors="pt",
        padding=False,
        truncation=False,
    )
    enc = {k: v.to(device) for k, v in enc.items()}

    outputs = model.generate(
        **enc,
        max_new_tokens=max_tokens,
        temperature=0.4,
        top_k=40,
        top_p=0.9,
        do_sample=True,
        eos_token_id=tokenizer.eos_token_id,
        pad_token_id=tokenizer.pad_token_id,
    )

    input_len = enc["input_ids"].shape[1]
    gen_tokens = outputs[0][input_len:]
    return tokenizer.decode(gen_tokens, skip_special_tokens=True)


def clean_problem_prompt(p: str) -> str:
    """Remove Examples / Note sections from the prompt if present."""
    lines = p.splitlines()
    new = []
    skip = False
    for line in lines:
        if re.search(r"^\s*-{2,}\s*Examples", line, re.I):
            skip = True
            continue
        if re.search(r"^\s*-{2,}\s*Note", line, re.I):
            skip = True
            continue
        if skip:
            if line.strip() == "":
                skip = False
            continue
        if line.strip().startswith("END"):
            continue
        new.append(line)
    return "\n".join(new).strip()


def extract_c_code(text: str, fallback: str = "") -> str:
    """
    Extract C code from model output (simple stable version):
    1. Prefer ```c ... ```
    2. Then look for ``` ... ```
    3. Then slice from '#include' to the last '}'
    4. Otherwise fallback
    """
    if not text.strip():
        return fallback

    # 1) ```c ... ```
    m = re.findall(r"```(?:c|C|cpp)?\s*(.*?)```", text, re.S)
    if m:
        # Choose the longest block
        m_sorted = sorted(m, key=lambda s: len(s), reverse=True)
        code = m_sorted[0].strip()
        if "#include" in code or "int main" in code:
            return code

    # 2) Any ``` ... ```
    m2 = re.findall(r"```(.*?)```", text, re.S)
    if m2:
        m2_sorted = sorted(m2, key=lambda s: len(s), reverse=True)
        code = m2_sorted[0].strip()
        if "#include" in code or "int main" in code:
            return code

    # 3) Slice starting from #include
    idx = text.find("#include")
    if idx != -1:
        tail = text[idx:]
        last_brace = tail.rfind("}")
        if last_brace != -1:
            return tail[: last_brace + 1].strip()
        return tail.strip()

    # 4) Fallback
    return fallback or text.strip()


def add_line_numbers(code: str) -> str:
    """Add line numbers to the code to help the analyze stage reference positions."""
    lines = code.splitlines()
    return "\n".join(f"{i+1:3}: {line}" for i, line in enumerate(lines))


# ==========================================================
# === NEW === Error classification + strategy block
# ==========================================================
def classify_error_and_strategy(feedback: str) -> tuple[str, str]:
    """
    Roughly categorize errors based on compiler / KLEE / CodeQL text,
    and provide the analyzer with a stronger strategy hint.

    Returns: (error_type, strategy_block)
    """
    fb = feedback.lower()

    # 1) assigning to ... from incompatible type 'void'
    if "assigning to '" in fb and "incompatible type 'void'" in fb:
        return (
            "VOID_ASSIGN_FIX",
            """- The compiler reports: assigning to a variable from incompatible type 'void'.
- This usually means a function declared 'void' (e.g. mirror) is used on the right-hand side of an assignment.

You MUST:
- Find every line that has the shape:
    something = <void_function>(...);
  and rewrite it to:
    <void_function>(...);

- Treat the void function as a procedure that mutates its argument in-place.
- Do NOT change the function's return type just to make the assignment compile.
- Do NOT introduce malloc/free in this fix."""
        )

    # 2) called object type 'int' is not a function or function pointer
    if "called object type" in fb and "is not a function or function pointer" in fb:
        return(
            "CALLED_OBJECT_NOT_FUNCTION_FIX",
            """- The compiler reports: called object type 'T' is not a function or function pointer.
- This almost always means a variable shadows a function name, for example:
    int equilibriumIndex = equilibriumIndex(arr, n);

You MUST:
- Rename the *variable* to a different name (e.g. 'result', 'idx'), while keeping the function name unchanged.
- Do NOT delete the function definition.
- Do NOT change the function signature."""
        )

    # 3) Line-number prefix pollution: strings like "2: #include <stdio.h>"
    if "unknown type name '2'" in fb or re.search(r"\n\s*\d+:\s*#include", feedback):
        return(
            "LINE_PREFIX_CLEANUP",
            """- The compiler is seeing tokens like "2:" in front of #include or code lines.
- These are line-number prefixes accidentally written into the source.

You MUST:
- Remove numeric prefixes like "2: " / "15: " in front of #include or other code lines.
Example:
- Replace "2: #include <stdio.h>" with "#include <stdio.h>".
Do not change the actual include list or control flow."""
        )

    # 4) bool / true / false undeclared
    if ("use of undeclared identifier 'bool'" in fb
        or "use of undeclared identifier 'true'" in fb
        or "use of undeclared identifier 'false'" in fb
        or "unknown type name 'bool'" in fb):
        return(
            "BOOL_FIX",
            """- The compiler reports 'bool', 'true' or 'false' is undeclared.
- Standard C requires either including <stdbool.h> or using int / 0 / 1 instead.

You MUST choose one consistent strategy:
- EITHER add '#include <stdbool.h>' together with the other #include lines,
- OR replace 'bool' with 'int' and 'true'/'false' with 1/0 consistently.

Do NOT change the algorithm or I/O format when doing this."""
        )

    # 5) implicit declaration of function ...
    if "implicit declaration of function" in fb:
        # Try to extract the function name
        m = re.search(r"implicit declaration of function '([^']+)'", feedback)
        fn = m.group(1) if m else "the function"
        return(
            "IMPLICIT_DECL_FIX",
            f"""- The compiler reports an implicit declaration of {fn}.
- This means {fn} is called before it is declared/defined.

You MUST:
- Either move the full definition of {fn} so it appears before main and before the first call,
- OR add a correct prototype for {fn} before main, matching its definition.

Do NOT silently rename the function or change its parameter list in a way that breaks the intent."""
        )

    # 6) variable length array with static / VLA issue
    if "variable length array" in fb and "static" in fb:
        return(
            "VLA_STATIC_FIX",
            """- The compiler reports a variable length array (VLA) cannot have 'static' storage duration.

You MUST:
- Either remove the 'static' keyword from the VLA declaration,
- OR introduce a compile-time bound (e.g. '#define MAX_N ...') and replace the VLA with
  a fixed-size array 'int a[MAX_N];' plus an explicit check 'if (n > MAX_N) return ...;'.

Do NOT keep any declaration of the form 'static T a[n];' where n is not a compile-time constant."""
        )

    # 7) KLEE invalid free / double free
    if "invalid free" in fb or "free of address" in fb or "double free" in fb:
        return(
            "INVALID_FREE_FIX",
            """- KLEE reports invalid free / double free.
- This means a pointer is freed when it should not be, or is freed twice.

You MUST:
- Ensure each dynamically allocated region is freed exactly once.
- Do NOT free pointers that alias arrays or memory returned to the caller and still in use.
- If a function returns a pointer to a buffer owned by the caller, do not free it inside that function."""
        )

    # 8) symbolic malloc / symbolic-sized allocation
    if ("symbolic-sized malloc" in fb
        or "concretized symbolic size" in fb
        or "symbolic size" in fb):
        return(
            "SYMBOLIC_MALLOC_FIX",
            """- KLEE reports a symbolic-sized malloc/array (size depends on symbolic input).
You MUST:
- Introduce a compile-time upper bound constant (e.g. MAX_N).
- Replace symbolic-sized malloc/arrays with fixed-size arrays using that bound.
- Add an input range guard so runtime size never exceeds MAX_N.
Do NOT invent random numeric constants; keep MAX_N small but reasonable."""
        )

    # 9) out-of-bounds / null / division by zero
    if ("out of bound" in fb or "out-of-bounds" in fb
        or "null page access" in fb
        or "division by zero" in fb
        or "div by zero" in fb):
        return(
            "BOUNDS_OR_DIV_FIX",
            """- The tool reports out-of-bounds access, null dereference, or division by zero.

You MUST:
- Add explicit guards around the problematic access or division.
  * For array access: ensure '0 <= index && index < size'.
  * For pointer dereference: ensure 'ptr != NULL' before dereferencing.
  * For division/modulo: ensure the divisor is non-zero before dividing."""
        )

    # 10) fallback
    return(
        "GENERAL",
        """- The error type is not matched to a specific bucket.
You should still propose concrete, local fixes:
- Adjust conditions, loop bounds, or missing base cases.
- Add simple guards for bad inputs.
Avoid large refactors or changing the overall algorithm."""
    )


# ==========================================================
# Task implementations
# ==========================================================
def task_generate(idx: int, problem_prompt: str, output_dir: Path):
    """Iteration 1: generate initial C code from the problem prompt."""
    output_dir.mkdir(parents=True, exist_ok=True)
    code_path = output_dir / f"code_{idx}.c"
    raw_path = output_dir / f"raw_code_{idx}.txt"

    print(f"🟢 [GENERATE] code_{idx}.c")

    prompt = f"""You are an expert C programmer.

Write a complete ANSI C solution for the following problem.
Requirements:
- Output MUST be a single, complete C file.
- It MUST contain at least one '#include <...>' line.
- It MUST define a main function.
- Do NOT explain; only write code.

PROBLEM:
{clean_problem_prompt(problem_prompt)}

NOW OUTPUT ONLY C CODE:
```c
"""

    raw = run_model_prompt(prompt)
    raw_path.write_text(raw, encoding="utf-8")

    code = extract_c_code(raw)
    if not code.strip():
        code = "/* generation failed */\n#include <stdio.h>\nint main(void){return 0;}\n"

    code_path.write_text(code, encoding="utf-8")


def pick_feedback(feedback_dir: Path, idx: int) -> str:
    """
    Choose per-file feedback (priority: KLEE > compile > CodeQL)
      feedback_klee_code_{i}.txt
      feedback_compile_code_{i}.txt
      feedback_codeql_code_{i}.txt
    """
    f_klee = feedback_dir / f"feedback_klee_code_{idx}.txt"
    f_compile = feedback_dir / f"feedback_compile_code_{idx}.txt"
    f_codeql = feedback_dir / f"feedback_codeql_code_{idx}.txt"

    if f_klee.exists() and f_klee.stat().st_size > 0:
        return f_klee.read_text(encoding="utf-8")
    if f_compile.exists() and f_compile.stat().st_size > 0:
        return f_compile.read_text(encoding="utf-8")
    if f_codeql.exists() and f_codeql.stat().st_size > 0:
        return f_codeql.read_text(encoding="utf-8")
    return ""


def task_analyze(idx: int, current_code: str, feedback: str, output_dir: Path):
    """
    Iteration 2+ Step 1: generate natural-language repair instructions from CURRENT_CODE + TOOL FEEDBACK.
    Note: the output here is plain-text repair instructions, not code.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    rp_path = output_dir / f"repair_prompt_{idx}.txt"

    print(f"🔍 [ANALYZE] code_{idx}.c")

    numbered = add_line_numbers(current_code)

    # === NEW === Call the error classifier to generate the strategy block
    err_type, strategy_block = classify_error_and_strategy(feedback)

    prompt = f"""You are a C static analysis assistant.

ERROR_TYPE (rough classification):
  {err_type}

RECOMMENDED REPAIR STRATEGY:
{strategy_block}

Your job:
- Read the CURRENT CODE and TOOL FEEDBACK.
- Produce **clear, concrete, step-by-step repair instructions**.
- These instructions will be consumed later by another agent that actually edits the code.
- You MUST NOT output any C code here.
- You MUST NOT include markdown code fences.
- Focus on:
  * fixing compile errors and warnings,
  * fixing memory safety issues (out-of-bounds, null dereference, division by zero),
  * fixing obvious logical bugs reported by tools.

CURRENT CODE (with line numbers):
{numbered}

TOOL FEEDBACK:
{feedback}

Now write REPAIR INSTRUCTIONS that describe what to change in the code.
Rules:
- Refer to lines using the shown line numbers, but do not rewrite the entire code.
- Be specific: mention which variables, conditions, or expressions to change.
- You can suggest adding or modifying guards, changing loop bounds, moving function definitions, etc.
- Follow the RECOMMENDED REPAIR STRATEGY above whenever it applies.
- Do NOT invent new functionality; just repair.

REPAIR INSTRUCTIONS:
"""

    analysis = run_model_prompt(prompt, max_tokens=max_new_tokens)
    # Simple cleanup: remove accidental ``` blocks, etc.
    analysis = analysis.strip()
    if "```" in analysis:
        analysis = analysis.split("```", 1)[0].strip()

    if not analysis:
        analysis = "(No repair instructions generated.)"

    rp_path.write_text(analysis, encoding="utf-8")
    print(f"   -> Saved repair_prompt_{idx}.txt")


def task_repair(idx: int, current_code: str, repair_instructions: str, output_dir: Path):
    """
    Iteration 2+ Step 2: generate repaired, complete C code based on the repair instructions.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    code_path = output_dir / f"code_{idx}.c"
    raw_path = output_dir / f"raw_code_{idx}.txt"

    print(f"🛠️ [REPAIR] code_{idx}.c")

    numbered = add_line_numbers(current_code)

    prompt = f"""You are a C code repair agent.

Your job:
- Fix the CURRENT CODE according to the REPAIR INSTRUCTIONS.
- Keep the original algorithm and intended functionality.
- Apply only the changes that are necessary to satisfy the instructions and fix the issues.
- Output ONLY the full, corrected C code.
- Do NOT output any explanation.
- Do NOT output the original unmodified code.

CURRENT CODE (with line numbers):
{numbered}

REPAIR INSTRUCTIONS:
{repair_instructions}

Now output the fixed code:

```c
"""

    raw = run_model_prompt(prompt, max_tokens=1024)
    raw_path.write_text(raw, encoding="utf-8")

    fixed = extract_c_code(raw, fallback=current_code)

    if not fixed.strip():
        print("⚠️ Repair produced empty output, keeping original code.")
        fixed = current_code

    code_path.write_text(fixed, encoding="utf-8")


# ==========================================================
# Main entry point
# ==========================================================
def main():
    output_dir = Path(os.environ.get("OUTPUT_DIR", "./generated_code"))
    prompts_dir_env = os.environ.get("PROMPTS_DIR", "")
    feedback_dir_env = os.environ.get("FEEDBACK_DIR", "")
    repair_prompts_dir_env = os.environ.get("REPAIR_PROMPTS_DIR", "")

    prompts_dir = Path(prompts_dir_env) if prompts_dir_env else None
    feedback_dir = Path(feedback_dir_env) if feedback_dir_env else None
    repair_prompts_dir = Path(repair_prompts_dir_env) if repair_prompts_dir_env else None

    # GENERATE mode
    if TASK == "generate":
        if prompts_dir is not None and prompts_dir.exists():
            files = sorted(prompts_dir.glob("prompt_*.txt"))
            indices = [int(f.stem.split("_")[1]) for f in files]
            for idx in indices:
                if ONLY_SET and str(idx) not in ONLY_SET:
                    continue
                p_file = prompts_dir / f"prompt_{idx}.txt"
                if not p_file.exists():
                    continue
                task_generate(idx, p_file.read_text(encoding="utf-8"), output_dir)
            return
        else:
            prompts_txt = Path("prompts.txt")
            if not prompts_txt.exists():
                print("❌ No PROMPTS_DIR and prompts.txt missing.")
                sys.exit(1)
            raw_text = prompts_txt.read_text(encoding="utf-8").strip()
            blocks = [b.strip() for b in raw_text.split("---") if b.strip()]
            subset = blocks[:subset_size]

            (output_dir / "prompts").mkdir(parents=True, exist_ok=True)
            for i, p in enumerate(subset, 1):
                (output_dir / "prompts" / f"prompt_{i}.txt").write_text(p, encoding="utf-8")
                if ONLY_SET and str(i) not in ONLY_SET:
                    continue
                task_generate(i, p, output_dir)
            return

    # ANALYZE / REPAIR mode
    if ONLY_SET:
        target_indices = sorted(int(x) for x in ONLY_SET)
    else:
        files = sorted(output_dir.glob("code_*.c"))
        target_indices = [int(f.stem.split("_")[1]) for f in files]

    for idx in target_indices:
        if TASK == "analyze":
            if feedback_dir is None or not feedback_dir.exists():
                print("❌ FEEDBACK_DIR not set or does not exist.")
                sys.exit(1)

            c_file = output_dir / f"code_{idx}.c"
            if not c_file.exists():
                print(f"⚠️ Missing code_{idx}.c, skip analyze.")
                continue

            fb = pick_feedback(feedback_dir, idx)
            if not fb.strip():
                print(f"⚠️ No feedback for code_{idx}.c, skip analyze.")
                continue

            task_analyze(idx, c_file.read_text(encoding="utf-8"), fb, output_dir)

        elif TASK == "repair":
            rp_dir = repair_prompts_dir if repair_prompts_dir and repair_prompts_dir.exists() else output_dir
            c_file = output_dir / f"code_{idx}.c"
            rp_file = rp_dir / f"repair_prompt_{idx}.txt"

            if not c_file.exists():
                print(f"⚠️ Missing code_{idx}.c, skip repair.")
                continue
            if not rp_file.exists():
                print(f"⚠️ Missing repair_prompt_{idx}.txt, skip repair.")
                continue

            task_repair(
                idx,
                c_file.read_text(encoding="utf-8"),
                rp_file.read_text(encoding="utf-8"),
                output_dir,
            )


if __name__ == "__main__":
    main()
