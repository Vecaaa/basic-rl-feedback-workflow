#!/usr/bin/env python3
"""
run_llm3.py – Strict Two-Model Repair Loop (Generate / Analyze / Repair)

Modes (--task):
1. generate : PROMPT → code_i.c
   - Used in Iteration 1.
   - Model A (Fixer).

2. analyze  : CURRENT_CODE + FEEDBACK → repair_prompt.txt
   - Used in Iteration 2+ (Step 1).
   - Model B (Analyzer).
   - Output: Text-only repair instructions. NO CODE.

3. repair   : CURRENT_CODE + REPAIR_PROMPT → code_i.c
   - Used in Iteration 2+ (Step 2).
   - Model A (Fixer).
   - Output: Fixed C code.

Environment:
- MODEL comes from env MODEL or config.json
- OUTPUT_DIR, PROMPTS_DIR, FEEDBACK_DIR
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
    help="Task mode: generate (initial), analyze (create repair prompt), repair (apply fix)"
)
parser.add_argument(
    "--only",
    nargs="*",
    help="Only process specified indices (e.g. 1 3 5). "
)
args = parser.parse_args()
ONLY_SET = set(args.only or [])
TASK = args.task

# ==========================================================
# HF cache setup
# ==========================================================
user = os.getlogin()
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

subset_size = config.get("subset_size", 10)
max_new_tokens = config.get("max_new_tokens", 512)

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
    device_map="auto"
).to(device)

# ==========================================================
# Utils
# ==========================================================
def run_model_prompt(content: str, max_tokens: int = None) -> str:
    """
    Minimal, stable generate: raw text → raw text.
    """
    if max_tokens is None:
        max_tokens = max_new_tokens
    
    enc = tokenizer(
        content,
        return_tensors="pt",
        padding=False,
        truncation=False,
    )
    enc = {k: v.to(device) for k, v in enc.items()}

    outputs = model.generate(
        **enc,
        max_new_tokens=max_tokens,
        temperature=0.4,  # Consistent temperature for all tasks
        top_k=40,
        top_p=0.9,
        do_sample=True,
        eos_token_id=tokenizer.eos_token_id,
        pad_token_id=tokenizer.pad_token_id,
    )

    # Slice the output to remove the input prompt
    input_length = enc['input_ids'].shape[1]
    generated_tokens = outputs[0][input_length:]
    return tokenizer.decode(generated_tokens, skip_special_tokens=True)

def clean_problem_prompt(p: str) -> str:
    lines = p.splitlines()
    new = []
    skip = False
    for line in lines:
        if re.search(r'^\s*-{2,}\s*Examples', line, re.I): skip = True; continue
        if re.search(r'^\s*-{2,}\s*Note', line, re.I): skip = True; continue
        if skip:
            if line.strip() == "": skip = False
            continue
        if line.strip().startswith("END"): continue
        new.append(line)
    return "\n".join(new).strip()

def extract_c_code_from_text(text: str, fallback: str = "", repair_hint: str = "") -> str:
    """Extract C code from model output with multiple strategies."""
    if not text: 
        return fallback.strip()
    
    # 1) <FIXED_CODE> tags
    m = re.search(r"<FIXED_CODE>(.*?)</FIXED_CODE>", text, re.S | re.I)
    if m and "#include" in m.group(1): 
        return m.group(1).strip()

    # 2) Fenced code blocks (```c ... ```)
    blocks = re.findall(r"```(?:c|C|cpp|C\+\+)?\s*(.*?)```", text, re.S)
    if blocks:
        # Try each block from last to first
        for block in reversed(blocks):
            cand = block.strip()
            if "#include" in cand and "{" in cand:
                return cand
    
    # 2b) Handle case where prompt ended with ```c, so output starts with code and ends with ```
    # Look for content ending with ```
    m_end = re.search(r"(.*?)```", text, re.S)
    if m_end:
        cand = m_end.group(1).strip()
        if "#include" in cand and "{" in cand:
            return cand

    # 3) Find from first #include to last }
    inc_idx = text.find("#include")
    if inc_idx != -1:
        # Find the last closing brace after the include
        code_section = text[inc_idx:]
        last_brace = code_section.rfind('}')
        if last_brace != -1:
            return code_section[:last_brace + 1].strip()
        return code_section.strip()

    # 4) Look for any function definition
    func_match = re.search(r'(int|void|char|float|double)\s+\w+\s*\([^)]*\)\s*{', text)
    if func_match:
        code_from_func = text[func_match.start():]
        last_brace = code_from_func.rfind('}')
        if last_brace != -1:
            return "#include <stdio.h>\n" + code_from_func[:last_brace + 1].strip()

    return fallback.strip()

# ==========================================================
# Task Handlers
# ==========================================================

def add_line_numbers(code: str) -> str:
    """Add line numbers to code for better LLM reference."""
    lines = code.splitlines()
    return "\n".join([f"{i+1:3}: {line}" for i, line in enumerate(lines)])

# ==========================================================
# Task Handlers
# ==========================================================

def task_generate(idx: int, problem_prompt: str, output_dir: str):
    """
    Iteration 1: Generate initial code from problem description.
    """
    code_path = Path(output_dir) / f"code_{idx}.c"
    raw_path = Path(output_dir) / f"raw_code_{idx}.txt"

    print(f"🟢 [GENERATE] code_{idx}.c")

    prompt = f"""You are an expert C programmer.

Write a complete ANSI C solution for the following problem.
- Your output MUST contain at least one '#include <...>' line.

[[PROBLEM]]
{clean_problem_prompt(problem_prompt)}
now start to write your code, write code ONLY:
"""
    raw = run_model_prompt(prompt)
    raw_path.write_text(raw)

    fixed = extract_c_code_from_text(raw)
    if not fixed.strip():
        fixed = "/* generation failed: empty output */\nint main(){return 0;}\n"

    code_path.write_text(fixed)


def task_analyze(idx: int, current_code: str, feedback: str, output_dir: str):
    """
    Iteration 2+ (Step 1): Analyze code + feedback, produce REPAIR PROMPT.
    NO CODE GENERATION HERE.
    """
    repair_prompt_path = Path(output_dir) / f"repair_prompt_{idx}.txt"
    
    print(f"🔍 [ANALYZE] code_{idx}.c")

    numbered_code = add_line_numbers(current_code)
    
    # Check if this is a KLEE symbolic size error
    is_klee_symbolic_error = "concretized symbolic size" in feedback.lower() or "symbolic malloc" in feedback.lower()
    
    # Check if this is a CodeQL constant-comparison issue
    is_constant_comparison = "cpp/constant-comparison" in feedback.lower()

    if is_klee_symbolic_error:
        prompt = f"""You are an KLEE ERROR repair prompt generator.

YOUR TASK: Find malloc/calloc/realloc lines in the code. Replace with fixed-size arrays. 

IMPORTANT:
1. You MUST identify the exact source line by QUOTING THE FULL LINE OF CODE ITSELF.
2. Do NOT output any C code block.
3. Output ONLY ONE single-line repair instruction
4. Do NOT generate explanations or descriptions.
5. Check for error of the line number mentioned in ERROR first if mentioned.

CODE:
{numbered_code}

ERROR:
{feedback}

Output ONE specific repair instruction referencing the line number from the feedback."""
    elif is_constant_comparison:
        prompt = f"""CodeQL detected impossible comparisons that are always true or always false.
YOUR TASK: Look at the specific line mentioned in the feedback. Either:
1. Remove the impossible check if overflow detection isn't needed
2. Fix the overflow detection logic (check before overflow happens, not after)

IMPORTANT:
1. You MUST identify the exact source line by QUOTING THE FULL LINE OF CODE ITSELF.
2. Do NOT output any C code block.
3. Output ONLY ONE single-line repair instruction
4. Do NOT generate explanations or descriptions.
5. Check for error of the line number mentioned in ERROR first if mentioned.

CODE (with line numbers):
{numbered_code}

CODEQL FEEDBACK:
{feedback}

Output ONE specific repair instruction referencing the line number from the feedback, DO NOT output any code."""
    else:
        prompt = f"""You are a C code compiler expert. Analyze the code and feedback below.

Generate ONLY a single, precise, and actionable line of repair instruction. Do NOT output any code.
Reference specific line numbers from the provided code AND quote the code content.

IMPORTANT:
1. You MUST identify the exact source line by QUOTING THE FULL LINE OF CODE ITSELF.
2. Do NOT output any C code block.
3. Output ONLY ONE single-line repair instruction
4. Do NOT generate explanations or descriptions.
5. Check for error of the line number mentioned in ERROR first if mentioned.

CURRENT CODE (with line numbers):
{numbered_code}

COMPILER FEEDBACK:
{feedback}

Repair Instruction:"""
    analysis = run_model_prompt(prompt)
    
    # Remove "Explanation:" section if it exists
    lines = analysis.strip().split('\n')
    cleaned_lines = []
    for line in lines:
        # Stop at "Explanation:" (case-insensitive)
        if line.strip().lower().startswith('explanation:'):
            break
        cleaned_lines.append(line)
    
    analysis = '\n'.join(cleaned_lines).strip()
    
    repair_prompt_path.write_text(analysis)
    print(f"   -> Saved repair prompt to {repair_prompt_path.name}")


def task_repair(idx: int, current_code: str, repair_instructions: str, output_dir: str):
    """
    Iteration 2+ (Step 2): Apply the repair to the code.
    """
    code_path = Path(output_dir) / f"code_{idx}.c"
    raw_path = Path(output_dir) / f"raw_code_{idx}.txt"

    print(f"🛠️ [REPAIR] code_{idx}.c")

    # Check for NO_REPAIR_NEEDED
    if "NO_REPAIR_NEEDED" in repair_instructions:
        print(f"   🟢 No repair needed for code_{idx}.c (Analyzer decision)")
        code_path.write_text(current_code)
        return

    # Load original problem description to preserve functionality
    prompts_dir = os.environ.get("OUTPUT_DIR", "./generated_code")
    if "/iter_" in prompts_dir:
        # Extract base dir and get iter_1 prompts
        base_dir = prompts_dir.split("/iter_")[0]
        original_prompt_path = Path(base_dir) / "iter_1" / "generated_code" / "prompts" / f"prompt_{idx}.txt"
    else:
        original_prompt_path = Path(prompts_dir) / "prompts" / f"prompt_{idx}.txt"
    
    problem_description = ""
    if original_prompt_path.exists():
        problem_description = original_prompt_path.read_text().strip()
        # Clean it up
        problem_description = clean_problem_prompt(problem_description)
    
    # Enhanced prompt that preserves functionality
    if problem_description:
        numbered_code = add_line_numbers(current_code)
        prompt = f"""You are fixing a C program. The program MUST solve this problem:

PROBLEM:
{problem_description}

CURRENT CODE (with line numbers):
{numbered_code}

FIX REQUIRED:
{repair_instructions}

IMPORTANT: 
1. Keep the same algorithm and logic. Only fix the specific error mentioned above.
2. Use the line numbers in CURRENT CODE to locate the error.
3. Verify the location using the quoted code in the FIX REQUIRED section (if present).
4. Output the FIXED CODE without line numbers.

FIXED CODE:
```c
"""
    else:
        # Fallback if we can't find the original prompt
        numbered_code = add_line_numbers(current_code)
        prompt = f"""Fix the following C code by applying ONLY the specified repair.
Do NOT change the algorithm or logic. Only fix the error.

CURRENT CODE (with line numbers):
{numbered_code}

FIX REQUIRED:
{repair_instructions}

IMPORTANT: Output the FIXED CODE without line numbers.

FIXED CODE:
```c
"""
    # Use more tokens for repair to ensure complete code generation
    raw = run_model_prompt(prompt, max_tokens=1024)
    raw_path.write_text(raw)
    
    # Debug output
    # Suppress verbose preview output during repair
    # print(f"   📝 Raw output length: {len(raw)} chars")
    # if len(raw) > 0:
    #     print(f"   📝 First 200 chars: {raw[:200]}")

    fixed = extract_c_code_from_text(raw, fallback=current_code, repair_hint=repair_instructions)
    
    # Validate that functionality wasn't drastically changed
    def get_function_names(code):
        """Extract function names from C code"""
        pattern = r'\b(int|void|char|float|double|long|short|unsigned)\s+(\w+)\s*\('
        return set(re.findall(pattern, code))
    
    original_funcs = get_function_names(current_code)
    fixed_funcs = get_function_names(fixed)
    
    # Check if major functions disappeared or new ones appeared
    removed_funcs = original_funcs - fixed_funcs
    added_funcs = fixed_funcs - original_funcs
    
    if removed_funcs:
        print(f"   ⚠️  WARNING: Functions removed: {[f[1] for f in removed_funcs]}")
    if added_funcs:
        print(f"   ⚠️  WARNING: New functions added: {[f[1] for f in added_funcs]}")
    
    # Check for no-op
    if re.sub(r"\s+", "", current_code) == re.sub(r"\s+", "", fixed):
        print(f"   ⚠️ No changes detected for code_{idx}.c")
    else:
        # Show line count change
        orig_lines = len(current_code.splitlines())
        fixed_lines = len(fixed.splitlines())
        if abs(orig_lines - fixed_lines) > orig_lines * 0.3:  # >30% change
            print(f"   ⚠️  WARNING: Significant size change: {orig_lines} → {fixed_lines} lines ({fixed_lines - orig_lines:+d})")
    
    code_path.write_text(fixed)


# ==========================================================
# Main Dispatch
# ==========================================================
def main():
    output_dir = os.environ.get("OUTPUT_DIR", "./generated_code")
    prompts_dir = os.environ.get("PROMPTS_DIR", "") # For generate
    feedback_dir = os.environ.get("FEEDBACK_DIR", "") # For analyze
    repair_prompts_dir = os.environ.get("REPAIR_PROMPTS_DIR", "") # For repair
    
    os.makedirs(output_dir, exist_ok=True)

    # We need to determine which indices to process.
    # Usually we look at prompts_dir or existing files.
    
    # For GENERATE, we need prompts.
    if TASK == "generate":
        # If prompts_dir is set, use it. Else load prompts.txt (Iter 1 legacy mode)
        if prompts_dir:
            files = sorted(Path(prompts_dir).glob("prompt_*.txt"))
            indices = [int(f.stem.split("_")[1]) for f in files]
        else:
            # Legacy Iter 1 mode: load prompts.txt
            print("📦 Loading local prompts.txt ...")
            if not Path("prompts.txt").exists():
                print("❌ prompts.txt missing"); sys.exit(1)
            raw_text = Path("prompts.txt").read_text().strip()
            blocks = [b.strip() for b in raw_text.split('---') if b.strip()]
            subset = blocks[:subset_size]
            
            # Save prompts for later
            snap_dir = Path(output_dir) / "prompts"
            snap_dir.mkdir(parents=True, exist_ok=True)
            
            for i, p in enumerate(subset, 1):
                (snap_dir / f"prompt_{i}.txt").write_text(p)
                if ONLY_SET and str(i) not in ONLY_SET: continue
                task_generate(i, p, output_dir)
            return

    # For ANALYZE and REPAIR, we usually operate on a list of problematic files
    # passed via --only or inferred from directory.
    # However, the caller (run_iter2.sh) usually sets --only for specific files.
    
    # If --only is not set, we might scan the directory.
    # But for safety, let's rely on --only or scan existing code_*.c
    
    target_indices = []
    if ONLY_SET:
        target_indices = sorted([int(x) for x in ONLY_SET])
    else:
        # Fallback: scan output_dir for code_*.c
        files = sorted(Path(output_dir).glob("code_*.c"))
        target_indices = [int(f.stem.split("_")[1]) for f in files]

    for idx in target_indices:
        if TASK == "generate":
            # Directory mode generate (if prompts_dir was set)
             p_file = Path(prompts_dir) / f"prompt_{idx}.txt"
             if p_file.exists():
                 task_generate(idx, p_file.read_text(), output_dir)
        
        elif TASK == "analyze":
            # Need current code and feedback
            c_file = Path(output_dir) / f"code_{idx}.c"
            
            # Use separated feedback files with strict priority: KLEE > Compile > CodeQL
            f_klee = Path(feedback_dir) / f"feedback_klee_code_{idx}.txt"
            f_compile = Path(feedback_dir) / f"feedback_compile_code_{idx}.txt"
            f_codeql = Path(feedback_dir) / f"feedback_codeql_code_{idx}.txt"
            
            if not c_file.exists():
                print(f"❌ Missing code_{idx}.c, skipping analysis"); continue
            
            # Priority: KLEE > Compile > CodeQL
            fb = ""
            if f_klee.exists() and f_klee.stat().st_size > 0:
                fb = f_klee.read_text()
            elif f_compile.exists() and f_compile.stat().st_size > 0:
                fb = f_compile.read_text()
            elif f_codeql.exists() and f_codeql.stat().st_size > 0:
                fb = f_codeql.read_text()
            
            if not fb.strip():
                print(f"⚠️ No feedback for code_{idx}.c, skipping analysis"); continue
                
            task_analyze(idx, c_file.read_text(), fb, output_dir)


        elif TASK == "repair":
            # Need current code and repair instructions
            c_file = Path(output_dir) / f"code_{idx}.c"
            # Repair prompt comes from the PREVIOUS step (analyze), which saved to output_dir
            # or a specific repair prompts dir.
            # Let's assume they are in output_dir/repair_prompt_{idx}.txt for simplicity
            # unless REPAIR_PROMPTS_DIR is set.
            rp_dir = repair_prompts_dir if repair_prompts_dir else output_dir
            rp_file = Path(rp_dir) / f"repair_prompt_{idx}.txt"
            
            if not c_file.exists():
                print(f"❌ Missing code_{idx}.c, skipping repair"); continue
            if not rp_file.exists():
                print(f"❌ Missing repair_prompt_{idx}.txt, skipping repair"); continue
                
            task_repair(idx, c_file.read_text(), rp_file.read_text(), output_dir)

if __name__ == "__main__":
    main()
