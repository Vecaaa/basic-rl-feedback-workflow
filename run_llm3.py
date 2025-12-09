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
)

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
    """
    Extract C code from model output with robust heuristics.
    Prioritizes full files (includes + main) over snippets.
    """
    if not text: 
        return fallback.strip()
    
    # 1) <FIXED_CODE> tags (Highest priority if explicit)
    m = re.search(r"<FIXED_CODE>(.*?)</FIXED_CODE>", text, re.S | re.I)
    if m and "#include" in m.group(1): 
        return m.group(1).strip()

    # 2) Collect all fenced code blocks
    blocks = re.findall(r"```(?:c|C|cpp|C\+\+)?\s*(.*?)```", text, re.S)
    
    # 2b) Handle case where prompt ended with ```c, so output starts with code and ends with ```
    # or just code ending with ```
    m_end = re.search(r"(.*?)```", text, re.S)
    if m_end:
        blocks.append(m_end.group(1))

    # 3) If no blocks, try to find the largest chunk between #include and last }
    if not blocks:
        inc_idx = text.find("#include")
        if inc_idx != -1:
            code_section = text[inc_idx:]
            last_brace = code_section.rfind('}')
            if last_brace != -1:
                blocks.append(code_section[:last_brace + 1])
            else:
                blocks.append(code_section)

    # 4) Score candidates
    best_code = fallback
    best_score = -1

    for block in blocks:
        cand = block.strip()
        if not cand: continue

        score = 0
        # Heuristics
        if "#include" in cand: score += 10
        if "int main" in cand or "void main" in cand: score += 10
        if "{" in cand and "}" in cand: score += 5
        
        # Length heuristic: extremely short blocks are likely snippets
        if len(cand) < 50: score -= 20
        
        # Penalize if it looks like a diff or explanation
        if cand.startswith("Diff:") or cand.startswith("Here is"): score -= 100

        # Prefer the last block if scores are tied (often the final answer)
        # But if one block is clearly a full file (score >= 20) and others are snippets, take the full file.
        
        if score > best_score:
            best_score = score
            best_code = cand
        elif score == best_score:
            # Tie-breaker: prefer the one that appears later (likely the final iteration)
            # or the one that is longer?
            # Let's stick to "later is better" for ties, assuming the model improves or finalizes.
            best_code = cand

    # 5) Final fallback: if even the best candidate is garbage (score < 0), try function definition search
    if best_score < 5:
        # Try finding a function definition as a last resort
        func_match = re.search(r'(int|void|char|float|double)\s+\w+\s*\([^)]*\)\s*{', text)
        if func_match:
            code_from_func = text[func_match.start():]
            last_brace = code_from_func.rfind('}')
            if last_brace != -1:
                potential = "#include <stdio.h>\n" + code_from_func[:last_brace + 1].strip()
                return potential

    return best_code.strip()

# ==========================================================
# Task Handlers
# ==========================================================

def add_line_numbers(code: str) -> str:
    """Add line numbers to code for better LLM reference."""
    lines = code.splitlines()
    return "\n".join([f"{i+1:3}: {line}" for i, line in enumerate(lines)])

def detect_heap_usage(code: str):
    """
    粗略检测代码里是否有“堆内存模型”：
      - 是否有全局指针声明（形如：int *arr;）
      - 是否有 malloc / calloc / realloc 调用
    返回 (has_global_ptr, has_heap_alloc)
    """
    # 检测全局指针：匹配行首的 "type *name;"
    has_global_ptr = bool(
        re.search(r'^\s*(?:int|char|float|double|long|short|unsigned|struct\s+\w+)\s*\*\s*\w+\s*;',
                  code, re.MULTILINE)
    )

    lower = code.lower()
    has_heap_alloc = any(tok in lower for tok in ["malloc(", "calloc(", "realloc("])

    return has_global_ptr, has_heap_alloc

def validate_memory_model_fix(repair_text: str, original_code: str, must_fix: bool) -> bool:
    """
    严格内存模型修复完整性校验（带 must_fix 开关）

    must_fix = True  → 说明本轮是 KLEE symbolic malloc 触发的【强制内存模型修复】
    must_fix = False → 说明本轮根本不允许出现内存模型修改
    """

    original_lower = original_code.lower()
    repair_lower = repair_text.lower()

    # ✅ 如果本轮不需要内存模型修复 → 直接放行
    if not must_fix:
        return True

    # ===== 仅在 must_fix=True 时，才强制三件套 =====

    # 1️⃣ 是否真的存在全局指针 / malloc / free
    has_global_ptr = bool(re.search(r'\bint\s*\*\s*\w+', original_lower))
    has_malloc = any(tok in original_lower for tok in ["malloc(", "calloc(", "realloc("])
    has_free = "free(" in original_lower

    # 2️⃣ repair prompt 中是否真的完整处理了三件套
    replaces_global_ptr = bool(re.search(r'replace\s+"int\s*\*', repair_lower))
    removes_malloc = bool(re.search(r'remove\s+"malloc', repair_lower))
    removes_free = bool(re.search(r'remove\s+"free', repair_lower)) or not has_free

    # 3️⃣ 三件套强制约束逻辑
    if has_global_ptr and not replaces_global_ptr:
        return False

    if has_malloc and not removes_malloc:
        return False

    if has_free and not removes_free:
        return False

    return True


def classify_error_and_strategy(feedback_text: str) -> tuple[str, str]:
    """
    轻量级“策略路由”：
    根据编译器 / KLEE 文本粗略分类错误类型，并为 LLM 提供一个推荐的修复策略块。
    这相当于在 error_text → repair_prompt 之间插入一个 policy layer。
    """
    fb = feedback_text.lower()

    # 1) 典型 C 编译器错误模式
    if "assigning to '" in fb and "from incompatible type 'void'" in fb:
        return (
            "VOID_ASSIGN_FIX",
            """- The compiler reports: assigning to a pointer from incompatible type 'void'.
- This usually means a function with return type 'void' is being used on the right-hand side of an assignment.
- Your repair MUST:
  * Keep the function return type as 'void' OR change it to the correct pointer type, BUT NOT both.
  * Prefer the safer option: remove the assignment and call the function purely for its side effects, e.g.:
      ORIGINAL:   node->left = mirror(node->right);
      REPLACE:    mirror(node->right);
  * Do NOT remove the function or its logic; only adjust how it is called."""
        )

    if "too many arguments to function call" in fb or "too few arguments to function call" in fb or "too many arguments" in fb:
        return (
            "FUNC_ARITY_FIX",
            """- The compiler reports a mismatch between function declaration and call arity.
- Your repair MUST:
  * Either adjust the function declaration parameter list, OR adjust the call sites, but keep the overall algorithm identical.
  * Quote the full original line and the full new line for each change, using the allowed edit forms."""
        )

    if "unknown type name 'please'" in fb or "unknown type name '[[helper]]'" in fb or "unknown type name" in fb and "please note" in fb:
        return (
            "LLM_NOISE_CLEANUP",
            """- The compiler is treating natural-language text (e.g. 'Please note ...', '[[HELPER]]') as C code.
- Your repair MUST:
  * Remove all non-C narrative text blocks that appear after the real program.
  * Keep only ONE valid translation unit (includes, function definitions, main), and delete any duplicated helper code copied after explanations.
  * Use 'Remove "<full original line>"' edits for all purely natural-language lines."""
        )

    if "use of undeclared identifier 'm_pi'" in fb or ("use of undeclared identifier" in fb and "m_pi" in fb):
        return (
            "UNDECLARED_CONST_FIX",
            """- The compiler reports 'use of undeclared identifier M_PI'.
- Standard C does not guarantee M_PI; you MUST either:
  * Add a constant definition, e.g. '#define M_PI 3.141592653589793', OR
  * Replace 'M_PI' with an explicit numeric literal or 'acos(-1)'.
- You MUST NOT change the printed semantics (still print degrees or radians as requested)."""
        )

    if "divide by zero" in fb or "div by zero" in fb:
        return (
            "DIV_ZERO_GUARD",
            """- The tool reports a potential division by zero (e.g. in 'n % b' or 'x / y').
- Your repair MUST:
  * Introduce an explicit guard on the divisor BEFORE the division or modulo, e.g.:
      Insert 'if (b == 0) return ERROR_CODE;' before the line that divides by 'b'.
  * Or otherwise restrict the input range so the divisor is never zero.
  * Do NOT silently change the formula; add explicit guards instead."""
        )

    # 2) KLEE symbolic malloc / OOB 等已有规则：保持与现有逻辑一致
    if "symbolic malloc" in fb or "concretized symbolic size" in fb or "symbolic-sized malloc" in fb:
        return (
            "SYMBOLIC_MALLOC_FIX",
            """- KLEE reports symbolic-sized malloc / array.
- Your repair MUST:
  * Introduce a MAX_N style compile-time bound for the allocation size.
  * Replace symbolic-sized allocations with fixed-size arrays using that bound.
  * Add an input range guard so runtime values cannot exceed the bound.
  * Use only the allowed MEMORY MODEL FIX edit forms."""
        )

    if "out of bound" in fb or "out-of-bounds" in fb or "null page access" in fb:
        return (
            "BOUNDS_FIX",
            """- The tool reports an out-of-bounds or invalid memory access.
- Your repair MUST:
  * Add or tighten index / pointer guards so all array accesses are within valid bounds.
  * Prefer simple explicit checks such as 'if (0 <= i && i < size)' before the access."""
        )

    # 3) Fallback：未知错误 → 走 GENERAL FIX 模式
    return (
        "GENERAL_FIX",
        """- The error type is not in the predefined categories.
- You MUST still propose concrete, local edits:
  * Adjust conditions, loop bounds, or return expressions.
  * Add missing base cases or early-return guards.
- You MUST NOT change function signatures, the memory model, or I/O formats in this mode."""
    )

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

    升级版：支持多种错误同时存在（symbolic malloc + OOB + null deref 等），
    并强制输出两个结构化 section：
      1) MEMORY MODEL FIX
      2) BOUNDS / ACCESS FIX
    """
    repair_prompt_path = Path(output_dir) / f"repair_prompt_{idx}.txt"
    
    print(f"🔍 [ANALYZE] code_{idx}.c")

    numbered_code = add_line_numbers(current_code)
    fb = feedback.lower()

    # -------------------------------
    # Error detection (非互斥，多种可同时为 True)
    # -------------------------------
    is_klee_symbolic_error = (
        "symbolic malloc" in fb or
        "concretized symbolic size" in fb or
        "symbolic-sized malloc" in fb
    )

    is_klee_out_of_bounds = (
        "out of bound" in fb or
        "out-of-bounds" in fb or
        "null page access" in fb or
        "memory error" in fb
    )

    is_klee_null_deref = (
        ("null pointer" in fb) or
        ("dereference" in fb and "null" in fb)
    )

    is_klee_div_by_zero = (
        "division by zero" in fb or
        "div by zero" in fb
    )

    is_klee_path_explosion = (
        "path explosion" in fb or
        "halttimer" in fb or
        "exceeded time" in fb
    )

    is_constant_comparison = "cpp/constant-comparison" in fb

    # ===============================
    # GENERIC COMPILER / LOGIC ERROR TYPES (A方案核心)
    # ===============================

    is_func_arity_error = (
        "too many arguments" in fb or
        "too few arguments" in fb
    )

    is_type_mismatch = (
        "incompatible types" in fb or
        "invalid operands" in fb
    )

    is_implicit_decl = (
        "implicit declaration" in fb
    )

    is_missing_return = (
        "control reaches end of non-void function" in fb
    )

    is_recursion_logic = (
        "stack overflow" in fb or
        "infinite recursion" in fb
    )


    # 是否需要两个大类修复
    # ===============================
    # STRICT MEMORY MODEL TRIGGER
    # ===============================

    # ✅ 使用统一堆检测函数（这是唯一合法的触发来源）
    has_global_ptr, has_heap_alloc = detect_heap_usage(current_code)

    # ✅ 只有：KLEE 报 symbolic malloc + 代码里真的有指针/堆 才触发内存模型修复
    needs_memory_fix = is_klee_symbolic_error and (has_global_ptr or has_heap_alloc)

    # ✅ bounds 修复保持不变
    needs_bounds_fix = is_klee_out_of_bounds or is_klee_null_deref or is_klee_div_by_zero

    needs_signature_fix = is_func_arity_error or is_implicit_decl
    needs_type_fix = is_type_mismatch
    
    # -------------------------------
    # 错误摘要，喂给模型参考
    # -------------------------------
    error_summary_parts = []
    if is_klee_symbolic_error:
        error_summary_parts.append("- SYMBOLIC MALLOC / SYMBOLIC-SIZED ARRAY")
    if is_klee_out_of_bounds:
        error_summary_parts.append("- OUT-OF-BOUNDS / INVALID MEMORY ACCESS / NULL PAGE ACCESS")
    if is_klee_null_deref:
        error_summary_parts.append("- NULL POINTER DEREFERENCE")
    if is_klee_div_by_zero:
        error_summary_parts.append("- DIVISION BY ZERO")
    if is_klee_path_explosion:
        error_summary_parts.append("- PATH EXPLOSION / TIMEOUT")
    if is_constant_comparison:
        error_summary_parts.append("- CONSTANT COMPARISON (ALWAYS TRUE/FALSE)")

    if not error_summary_parts:
        error_summary_parts.append("- UNKNOWN ERROR TYPE")

    error_summary = "\n".join(error_summary_parts)

    # -------------------------------
    # 检测“未知错误类型”（用于 General Fix）
    # -------------------------------
    is_known_error = any([
        is_klee_symbolic_error,
        is_klee_out_of_bounds,
        is_klee_null_deref,
        is_klee_div_by_zero,
        is_klee_path_explosion,
        is_constant_comparison,
        is_func_arity_error,
        is_type_mismatch,
        is_implicit_decl,
        is_missing_return,
        is_recursion_logic,
    ])
    is_unknown_error = not is_known_error

    # ✅ GENERAL 模式：彻底关掉签名修复 / 类型修复通道
    if is_unknown_error:
        needs_signature_fix = False
        needs_type_fix = False

    # -------------------------------
    # 策略路由：根据 feedback 选择错误类型 + 推荐修复策略
    # -------------------------------
    error_type, strategy_block = classify_error_and_strategy(feedback)

    # -------------------------------
    # 最终 Prompt（两段式输出 + 策略指引）
    # -------------------------------
    general_fix_note = ""
    if is_unknown_error:
        general_fix_note = """
[GENERAL FIX MODE]

The error type is UNKNOWN / not covered by the predefined categories.

In this mode you MUST STILL PROPOSE CONCRETE FIXES.

- You MAY:
* change conditional expressions (e.g. if (...) return ...)
* change loop bounds / loop conditions
* change return expressions
* add missing base cases or early-return guards
- You MUST NOT:
* change function signatures
* change the memory model (no malloc/free/pointer model changes)
* change input/output format (no scanf/printf format changes)
* introduce new global state or new arrays

All edits for UNKNOWN errors MUST be placed in the:
BOUNDS / ACCESS FIX section,
treating it as a GENERAL FIX section for algorithm / logic corrections.

ABSOLUTE RULE (GENERAL MODE):
- You MUST output:

  FUNCTION SIGNATURE FIX:
  (none)

  TYPE FIX:
  (none)

- Any attempt to modify function signatures or types in GENERAL MODE makes the output INVALID.
"""
    heap_free_note = ""
    if not (has_global_ptr or has_heap_alloc):
        heap_free_note = """
[HEAP-FREE PROGRAM RULE]

The CURRENT CODE does NOT contain:
- Any global pointer (e.g., "int *arr;")
- Any malloc / calloc / realloc

Therefore:

- You MUST output exactly:

  MEMORY MODEL FIX:
  (none)

- You are STRICTLY FORBIDDEN to:
  * change scalar variables (e.g., "int n;") into arrays,
  * introduce MAX_N or any numeric buffer constant,
  * simulate memory using arrays.

Violating this rule makes the output INVALID.
"""
    prompt = f"""
You are a STATIC ANALYSIS REPAIR INSTRUCTION GENERATOR.
{general_fix_note}
{heap_free_note}

ERROR_TYPE (policy routing decision):
  {error_type}

RECOMMENDED REPAIR STRATEGY (high level actions):
{strategy_block}

You must read the CURRENT CODE and TOOL FEEDBACK below, and then output
a STRICTLY STRUCTURED repair instruction with TWO SECTIONS:

1) MEMORY MODEL FIX (MANDATORY IF ANY malloc/calloc/realloc EXISTS):

THIS SECTION IS A HARD CONTRACT. If violated, the output is INVALID.

You MUST follow ALL rules below:

[TRIGGER RULE]
If the CURRENT CODE contains ANY of the following:
- A global pointer declaration (e.g., "int *arr;")
- OR a call to malloc / calloc / realloc whose size depends on an input or symbolic value,

THEN this section is MANDATORY and CANNOT be "(none)".

You MUST include ALL of the following types of edits:

[A] GLOBAL POINTER ELIMINATION (MANDATORY IF PRESENT)
- If a global pointer like "int *arr;" exists, you MUST:
  - Replace "int *arr;" with a fixed-size static array declaration, for example:
    "static int arr[MAX_N + 2];"
- You MUST quote the FULL ORIGINAL LINE and the FULL NEW LINE.

[B] DYNAMIC ALLOCATION REMOVAL (MANDATORY IF PRESENT)
- If any line contains malloc, calloc, or realloc, you MUST:
  - Use: Remove "<full original malloc line>".
- You MUST quote the FULL ORIGINAL LINE.

[C] FREE REMOVAL (MANDATORY IF PRESENT)
- If the corresponding free() exists, you MUST:
  - Use: Remove "<full original free(...) line>".
- You MUST quote the FULL ORIGINAL LINE.

[FORBIDDEN ACTIONS]
- You MUST NOT replace a malloc assignment with a local array declaration inside a function.
  (For example, replacing
     "arr = malloc(...);"
   with
     "int arr[MAX_N];"
   inside the same function is STRICTLY FORBIDDEN.)
- You MUST NOT leave any global pointer that still refers to the removed dynamic memory.
- You MUST NOT keep free() if dynamic allocation is removed.

[OUTPUT FORMAT RULES]
- Every edit MUST be one of the following exact forms:
  - Replace "<full original line>" with "<full new line>".
  - Remove "<full original line>".
- You MUST NOT mention line numbers.
- You MUST NOT use vague phrases like:
  "fix memory", "change allocation", "handle malloc", "convert to static".


2) BOUNDS / ACCESS FIX:
   - This section is ONLY for fixes to array indices, loop bounds, pointer dereferences,
     division by zero checks, and other access/guard logic.
   - If the error summary includes OUT-OF-BOUNDS / NULL PAGE ACCESS / DIVISION BY ZERO,
     you MUST provide at least ONE concrete edit in this section.
   - Each edit MUST be of one of the following forms:
       * Replace "<full original line>" with "<full new line>".
       * Insert "<new guard line>" before "<full original line>".
       * Remove "<full original line>" (ONLY if safe).
   - QUOTE the FULL ORIGINAL LINE exactly as it appears in the code.
   - Do NOT mention line numbers.
   - Do NOT use vague phrases like "add bounds checks" or "add appropriate checks"
     without specifying exactly where and what.

If a section is truly not needed (no relevant errors), you MUST explicitly write:
   MEMORY MODEL FIX:
   (none)

or
   BOUNDS / ACCESS FIX:
   (none)

3) FUNCTION SIGNATURE FIX (MANDATORY IF ARITY OR IMPLICIT DECL ERROR EXISTS):
   - This section is ONLY for fixing:
     * too many arguments to function
     * too few arguments to function
     * implicit declaration of function
   - You may ONLY:
     * Replace a function definition line
     * OR replace a function call argument list
   - You MUST NOT:
     * change function body logic
     * modify loops
     * modify conditionals
     * modify return expressions

4) TYPE FIX (MANDATORY IF TYPE MISMATCH EXISTS):
   - This section is ONLY for:
     * incompatible types
     * invalid operands
   - You may ONLY:
     * change variable types
     * add explicit casts
   - You MUST NOT:
     * change control flow
     * change memory model

ERROR SUMMARY:
{error_summary}

CURRENT CODE (with line numbers for your reference only):
{numbered_code}

TOOL FEEDBACK:
{feedback}

NOW OUTPUT EXACTLY THE FOLLOWING FORMAT:

MEMORY MODEL FIX:
<one or more concrete edits as specified above, OR "(none)">

BOUNDS / ACCESS FIX:
<one or more concrete edits as specified above, OR "(none)">

FUNCTION SIGNATURE FIX:
<one or more concrete edits, OR "(none)">

TYPE FIX:
<one or more concrete edits, OR "(none)">
"""

    max_attempts = 3
    analysis = ""
    
    for attempt in range(1, max_attempts + 1):
        print(f"   🔁 Generating repair prompt (attempt {attempt}/{max_attempts})...")
        analysis = run_model_prompt(prompt)

        # ============================================
        # PATCH: GENERAL 模式下自动修正 / 清空错放的区块
        # ============================================
        if is_unknown_error:
            # 1) 强制 FUNCTION SIGNATURE FIX 变成 (none)，并把其中内容挪到 BOUNDS / ACCESS FIX（如果那边是空）
            m_fs = re.search(
                r"FUNCTION SIGNATURE FIX:(.*?)(TYPE FIX:)",
                analysis,
                re.S | re.I
            )
            if m_fs:
                fs_body = m_fs.group(1).strip()
                # 如果 body 不是空、也不是显式 (none)，说明模型乱写了
                if fs_body and "(none)" not in fs_body.lower() and "<none>" not in fs_body.lower():
                    print("⚠️ GENERAL MODE: Misplaced FUNCTION SIGNATURE FIX content → reclassify to BOUNDS / ACCESS FIX")
                    # 先把 FUNCTION SIGNATURE FIX 块替换成标准 (none)
                    analysis = re.sub(
                        r"FUNCTION SIGNATURE FIX:.*?TYPE FIX:",
                        "FUNCTION SIGNATURE FIX:\n(none)\n\nTYPE FIX:",
                        analysis,
                        flags=re.S | re.I
                    )
                    # 如果 BOUNDS / ACCESS FIX 目前是 (none)，用 fs_body 填进去
                    analysis = re.sub(
                        r"BOUNDS / ACCESS FIX:\s*\(none\)",
                        "BOUNDS / ACCESS FIX:\n" + fs_body,
                        analysis,
                        flags=re.I
                    )

            # 2) TYPE FIX 在 GENERAL 模式下一律强制为 (none)（不搬运，直接丢掉）
            m_ty = re.search(
                r"TYPE FIX:(.*)$",
                analysis,
                re.S | re.I
            )
            if m_ty:
                ty_body = m_ty.group(1).strip()
                if ty_body and "(none)" not in ty_body.lower() and "<none>" not in ty_body.lower():
                    print("⚠️ GENERAL MODE: Discarding TYPE FIX content (must be (none) in GENERAL mode)")
                    analysis = re.sub(
                        r"TYPE FIX:.*$",
                        "TYPE FIX:\n(none)",
                        analysis,
                        flags=re.S | re.I
                    )

        # ============================================
        # VALIDATION CHECKS (Retry if failed)
        # ============================================
        
        # 1. Check for garbage / separator lines (e.g. "----------------")
        # Allow some whitespace, but reject if it's mostly dashes/equals/underscores
        if re.match(r'^[-=_\s]*$', analysis):
            print("❌ INVALID: Output is just separator lines or whitespace.")
            continue

        # 2. Check for missing sections
        if "MEMORY MODEL FIX:" not in analysis:
            print("❌ INVALID: Missing 'MEMORY MODEL FIX:' section.")
            continue

        if "BOUNDS / ACCESS FIX:" not in analysis:
            print("❌ INVALID: Missing 'BOUNDS / ACCESS FIX:' section.")
            continue

        # 3. Check for hard-coded array sizes in MEMORY MODEL FIX
        mm = re.search(
            r"MEMORY MODEL FIX:(.*?)(BOUNDS / ACCESS FIX:)",
            analysis,
            re.S | re.I
        )
        if mm:
            mm_block = mm.group(1)
            if re.search(r"\[\s*\d+\s*\]", mm_block):
                print("❌ INVALID: Hard-coded array size inside MEMORY MODEL FIX")
                print(mm_block)
                continue

        # 4. Check for forbidden vague phrases
        forbidden = [
            "add bounds check",
            "add bounds checks",
            "fix bounds",
            "handle bounds",
            "add appropriate checks"
        ]
        if any(f in analysis.lower() for f in forbidden):
            print("❌ INVALID: Forbidden vague phrase detected.")
            continue

        # 5. Check for line-number style edits
        if re.search(r'^\s*\d+\s*:', analysis, re.MULTILINE):
            print("❌ INVALID: Detected line-number style edits (e.g. '1: ...').")
            continue

        # If we got here, basic structure is valid.
        # Perform cleanup (remove Explanation, etc.)
        lines = analysis.strip().split('\n')
        cleaned_lines = []
        for line in lines:
            if line.strip().lower().startswith('explanation'):
                break
            cleaned_lines.append(line)
        analysis = "\n".join(cleaned_lines).strip()
        
        # Double check line numbers after cleanup (just in case)
        if re.search(r'^\s*\d+\s*:', analysis, re.MULTILINE):
             print("❌ INVALID: Detected line-number style edits after cleanup.")
             continue

        # Warnings (non-fatal)
        if not needs_signature_fix and "FUNCTION SIGNATURE FIX:" in analysis and "(none)" not in analysis:
            print("⚠️ Spurious FUNCTION SIGNATURE FIX detected (will be cleaned / reclassified by PATCH).")

        if not needs_type_fix and "TYPE FIX:" in analysis and "(none)" not in analysis:
            print("⚠️ Spurious TYPE FIX detected (will be cleaned by PATCH).")

        print("   ✅ Valid repair prompt generated.")
        break
    
    # Save the final result (valid or not, if attempts exhausted)
    repair_prompt_path.write_text(analysis)
    print(f"   -> Saved MULTI-SECTION repair prompt to {repair_prompt_path.name}")



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

    # ===============================
    # FUNCTION SIGNATURE FIX SAFETY LOCK
    # ===============================
    if "FUNCTION SIGNATURE FIX:" in repair_instructions:
        block = repair_instructions.split("FUNCTION SIGNATURE FIX:")[1].strip()

        # ✅ ✅ ✅ 关键豁免：如果是 (none)，直接跳过整个校验
        if block.lower().startswith("(none)") or block.lower().startswith("<none>"):
            pass
        else:
            # ❌ 禁止一切控制流 & 逻辑修改
            forbidden_logic_tokens = [
                " if ", " for ", " while ", " return ",
                " printf", " scanf", " sscanf",
                "=", "{", "}"
            ]

            if any(tok in block for tok in forbidden_logic_tokens):
                print("❌ INVALID FUNCTION SIGNATURE FIX: Attempted to modify logic/control flow")
                print(block)
                return

            # ✅ 必须真的包含函数签名关键字
            if not any(k in block for k in ["int", "void", "char"]):
                print("❌ INVALID FUNCTION SIGNATURE FIX: No valid function signature change detected")
                print(block)
                return


    # ===============================
    # TYPE FIX SAFETY LOCK
    # ===============================
    if "TYPE FIX:" in repair_instructions:
        forbidden_control_tokens = [" if ", " for ", " while ", " malloc", " free"]

        block = repair_instructions.split("TYPE FIX:")[1]
        if any(tok in block for tok in forbidden_control_tokens):
            print("❌ INVALID TYPE FIX: Attempted to modify control flow or memory model")
            print(block)
            return


    # ===============================
    # MEMORY MODEL FIX SAFETY LOCK（三件套）
    # ===============================
    has_global_ptr, has_heap_alloc = detect_heap_usage(current_code)
    needs_memory_fix = (
        "symbolic malloc" in repair_instructions.lower()
        and (has_global_ptr or has_heap_alloc)
    )

    if not validate_memory_model_fix(repair_instructions, current_code, needs_memory_fix):
        print("❌ INVALID MEMORY MODEL FIX: global pointer / malloc / free 未被完整处理")
        print("❌ 当前 repair prompt 被拒绝，不进入修复阶段")
        print("❌ Repair Prompt 内容如下：")
        print(repair_instructions)
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
        prompt = f"""You are a C code repair agent.
Your task is to fix the following C code based on the provided error description.

RULES:
1. Output ONLY the FULL FIXED CODE.
2. Do NOT output any explanation, reasoning, or conversational text.
3. Do NOT output the original code.
4. The code must be a COMPLETE, COMPILABLE file (including imports and main).
5. Do NOT change the algorithm or logic, only fix the specified error.

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
        prompt = f"""You are a C code repair agent.
Your task is to fix the following C code based on the provided error description.

RULES:
1. Output ONLY the FULL FIXED CODE.
2. Do NOT output any explanation, reasoning, or conversational text.
3. Do NOT output the original code.
4. The code must be a COMPLETE, COMPILABLE file (including imports and main).
5. Do NOT change the algorithm or logic, only fix the specified error.

PROBLEM:
(No problem description available, fix based on code and error only)

CURRENT CODE (with line numbers):
{numbered_code}

FIX REQUIRED:
{repair_instructions}

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
        print(f"   ⚠️ No changes detected for code_{idx}.c — triggering FORCED REPAIR RETRY")

        retry_prompt = f"""You previously FAILED to apply the requested repair.

    Your last output made NO EFFECTIVE CHANGE to the code.

    You MUST now:
    - Apply the repair EXACTLY as specified.
    - Output ONLY the full corrected C code.
    - Do NOT include any explanation or markdown.
    - Do NOT repeat the original code without modifications.

    CURRENT CODE:
    {current_code}

    REPAIR INSTRUCTIONS:
    {repair_instructions}

    OUTPUT ONLY VALID C CODE:
    """

        raw_retry = run_model_prompt(retry_prompt, max_tokens=1024)
        raw_path.write_text(raw_retry)

        fixed_retry = extract_c_code_from_text(raw_retry, fallback="")
        if fixed_retry.strip():
            fixed = fixed_retry
            print("   ✅ Forced retry produced a new version.")
        else:
            print("   ❌ Forced retry also failed. Keeping original.")
    
    # After potential retry, perform structural safety checks
    orig_lines = len(current_code.splitlines())
    fixed_lines = len(fixed.splitlines())

    orig_func_names = {name for _, name in original_funcs}
    fixed_func_names = {name for _, name in fixed_funcs}
    critical_orig = {n for n in orig_func_names if n != "main"}
    critical_fixed = {n for n in fixed_func_names if n != "main"}

    # 1) 防止把完整程序简化成只剩 main（如 code_16 情况）
    if critical_orig and not critical_fixed:
        print("❌ Destructive repair detected: all non-main functions were removed.")
        print("   Keeping original code for this file.")
        code_path.write_text(current_code)
        return

    # 2) 防止行数变化过大导致“重写成空壳程序”
    if orig_lines >= 10 and abs(orig_lines - fixed_lines) > orig_lines * 0.5:
        print(f"❌ Destructive repair detected: line count changed too much ({orig_lines} → {fixed_lines}).")
        print("   Keeping original code for this file.")
        code_path.write_text(current_code)
        return

    # Show line count change as a soft warning
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

            # If feedback is too short after filtering (e.g., only a header line),
            # skip analysis to avoid blind, potentially destructive repairs.
            non_empty_lines = [ln for ln in fb.splitlines() if ln.strip()]
            if len(non_empty_lines) <= 1:
                print(f"⚠️ Feedback for code_{idx}.c too weak (only header), skipping analysis"); continue
                
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
