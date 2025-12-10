# extract_training_data.py (append version)
import os
import re
import json
from pathlib import Path
from collections import defaultdict

def resolve_output_base() -> Path:
    """
    Determine which run directory to read when generating DPO data.
    Priority:
      1) DPO_OUTPUT_BASE env (explicit override)
      2) OUTPUT_BASE env (e.g., same as run_iter2)
      3) Most recent subdirectory under $LLM_OUTPUT_ROOT (default: /scratch/$USER/llm_outputs_runs)
      4) Legacy /scratch/$USER/llm_outputs fallback
    """
    env_override = os.environ.get("DPO_OUTPUT_BASE") or os.environ.get("OUTPUT_BASE")
    if env_override:
        path = Path(env_override).expanduser()
        if path.exists():
            print(f"[INFO] Using OUTPUT_BASE from environment: {path}")
            return path
        print(f"[WARN] OUTPUT_BASE override '{path}' not found, falling back to latest run.")

    user = os.environ.get("USER", "")
    runs_root = Path(os.environ.get("LLM_OUTPUT_ROOT", f"/scratch/{user}/llm_outputs_runs"))
    run_candidates = []
    if runs_root.exists():
        run_candidates = [p for p in runs_root.iterdir() if p.is_dir()]
        if run_candidates:
            latest = max(run_candidates, key=lambda p: p.stat().st_mtime)
            print(f"[INFO] Auto-detected latest run folder: {latest}")
            return latest

    legacy = Path(f"/scratch/{user}/llm_outputs")
    if legacy.exists():
        print(f"[INFO] Falling back to legacy OUTPUT_BASE: {legacy}")
        return legacy

    raise SystemExit("[ERROR] No OUTPUT_BASE found. Please set DPO_OUTPUT_BASE or run the pipeline first.")


OUTPUT_BASE = resolve_output_base()
MAX_CODE_ID = 50
PROJECT_ROOT = Path(__file__).resolve().parent
MANUAL_DPO_DIR = PROJECT_ROOT / "manual_dpo"

OUT_FILE = PROJECT_ROOT / "dpo_data.jsonl"
SEEN_FILE = PROJECT_ROOT / "seen_pairs.json"


# --------------------------
# Load seen pairs
# --------------------------
if SEEN_FILE.exists():
    raw = json.loads(SEEN_FILE.read_text())
    seen_pairs = set()

    # 兼容：raw 是列表，每个元素可能是 [code_id, best_iter, worst_iter]
    if isinstance(raw, list):
        for item in raw:
            # 之前保存的是 (code_id, best_iter, worst_iter)
            if isinstance(item, (list, tuple)) and len(item) == 3:
                seen_pairs.add(tuple(item))
            else:
                # 万一以后改格式，也不至于直接炸
                try:
                    seen_pairs.add(tuple(item))
                except TypeError:
                    pass
    else:
        # 非预期格式，就当空处理
        seen_pairs = set()
else:
    seen_pairs = set()


def save_seen():
    SEEN_FILE.write_text(json.dumps(list(seen_pairs)))


def read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None


def compute_reward(iter_dir: Path, code_id: int) -> int | None:
    compiled_dir = iter_dir / "compiled_output"
    feedback_dir = iter_dir / "feedback"
    klee_dir = iter_dir / "klee_output"

    # Compile reward
    compile_failures = compiled_dir / "compile_failures.txt"
    compile_ok = 1
    if compile_failures.exists():
        txt = compile_failures.read_text(encoding="utf-8")
        if f"code_{code_id} " in txt or f"code_{code_id}\n" in txt:
            compile_ok = 0

    # KLEE reward
    klee_errs = 0
    code_klee_dir = klee_dir / f"code_{code_id}"
    if code_klee_dir.exists():
        for err_file in code_klee_dir.rglob("*.err"):
            name = err_file.name.lower()
            if "mock" in name:
                continue
            content = err_file.read_text(encoding="utf-8", errors="ignore").lower()
            if "mock" in content:
                continue
            klee_errs += 1

    # CodeQL reward
    codeql_file = feedback_dir / f"code_{code_id}_codeql.txt"
    if codeql_file.exists():
        txt = codeql_file.read_text(encoding="utf-8")
        codeql_ok = ("— 0 issues found" in txt)
    else:
        codeql_ok = True

    return int(compile_ok) + int(klee_errs == 0) + int(codeql_ok)


def get_function_names(code: str) -> set[str]:
    """
    粗略提取函数名集合，用于结构健康检查。
    """
    pattern = r'\b(?:int|void|char|float|double|long|short|unsigned|struct\s+\w+)\s+(\w+)\s*\('
    return set(re.findall(pattern, code))


def structural_ok(current_code: str, fixed_code: str) -> bool:
    """
    结构健康检查，避免“删功能”式作弊修复进入数据集。

    规则：
      - 非空行数不能暴跌到 <50%（除非原始代码本身就很短）。
      - 原来的非 main 函数大部分仍然存在（至少 70% 保留）。
      - 如果原来有非 main 函数，修复后不能只剩一个 main。
    """
    cur_lines = [ln for ln in current_code.splitlines() if ln.strip()]
    fix_lines = [ln for ln in fixed_code.splitlines() if ln.strip()]

    cur_n = len(cur_lines)
    fix_n = len(fix_lines)

    # 行数健康检查：允许适度收缩，但不接受明显“缩成空壳”
    if cur_n >= 10:
        if fix_n < max(5, int(cur_n * 0.5)):
            return False

    cur_funcs = get_function_names(current_code)
    fix_funcs = get_function_names(fixed_code)

    cur_non_main = {f for f in cur_funcs if f != "main"}
    fix_non_main = {f for f in fix_funcs if f != "main"}

    # 如果原来有非 main 函数，修复后不能全没了
    if cur_non_main and not fix_non_main:
        return False

    # 要求至少保留大部分非 main 函数（70%）
    if cur_non_main:
        preserved = len(cur_non_main & fix_non_main)
        if preserved < max(1, int(len(cur_non_main) * 0.7)):
            return False

    return True


def build_prompt(current_code: str, repair_instructions: str) -> str:
    return (
        "You are a C code repair agent.\n"
        "Fix the following code according to the repair instructions.\n\n"
        "CURRENT CODE:\n"
        f"{current_code}\n\n"
        "REPAIR INSTRUCTIONS:\n"
        f"{repair_instructions}\n\n"
        "FIXED CODE:"
    )


def collect_records():
    records_by_code_id = defaultdict(list)

    for p in OUTPUT_BASE.glob("iter_*"):
        try:
            idx = int(p.name.split("_")[1])
        except:
            continue

        cleaned_dir = p / "cleaned_code"
        gen_dir = p / "generated_code"
        if not cleaned_dir.exists() or not gen_dir.exists():
            continue

        for code_id in range(1, MAX_CODE_ID + 1):
            cur = cleaned_dir / f"code_{code_id}.c"
            rep = gen_dir / f"repair_prompt_{code_id}.txt"
            fix = gen_dir / f"code_{code_id}.c"

            if not (cur.exists() and rep.exists() and fix.exists()):
                continue

            # 结构健康检查，过滤掉“删功能”式修复
            cur_text = cur.read_text()
            fix_text = fix.read_text()
            if not structural_ok(cur_text, fix_text):
                continue

            reward = compute_reward(p, code_id)
            if reward is None:
                continue

            prompt = build_prompt(
                cur_text,
                rep.read_text()
            )

            records_by_code_id[code_id].append(
                {
                    "iter": idx,
                    "prompt": prompt,
                    "fixed_code": fix.read_text(),
                    "reward": reward
                }
            )

    return records_by_code_id



def main():
    print(f"[INFO] Loading previous seen_pairs: {len(seen_pairs)} items")

    recs = collect_records()

    new_pairs = 0

    with OUT_FILE.open("a", encoding="utf-8") as f:  # APPEND MODE
        for code_id, attempts in recs.items():
            if len(attempts) < 2:
                continue

            attempts_sorted = sorted(attempts, key=lambda r: (r["reward"], r["iter"]))
            worst = attempts_sorted[0]
            best = attempts_sorted[-1]

            if best["reward"] <= worst["reward"]:
                continue

            key = (code_id, best["iter"], worst["iter"])
            if key in seen_pairs:
                continue

            # Append new DPO pair
            out = {
                "prompt": best["prompt"],
                "chosen": best["fixed_code"],
                "rejected": worst["fixed_code"],
                "code_id": code_id
            }
            f.write(json.dumps(out, ensure_ascii=False) + "\n")

            seen_pairs.add(key)
            new_pairs += 1

        # 追加手工黄金样本（manual_dpo 下的目录）
        if MANUAL_DPO_DIR.is_dir():
            for sub in MANUAL_DPO_DIR.iterdir():
                if not sub.is_dir():
                    continue
                m = re.match(r"code_(\d+)$", sub.name)
                if not m:
                    continue
                code_id = int(m.group(1))
                cur_path = sub / "current.c"
                rep_path = sub / "repair_instructions.txt"
                chosen_path = sub / "chosen.c"
                rejected_path = sub / "rejected.c"
                if not (cur_path.exists() and rep_path.exists() and chosen_path.exists() and rejected_path.exists()):
                    continue

                prompt = build_prompt(
                    cur_path.read_text(encoding="utf-8"),
                    rep_path.read_text(encoding="utf-8")
                )
                chosen = chosen_path.read_text(encoding="utf-8")
                rejected = rejected_path.read_text(encoding="utf-8")

                key = ("manual", code_id)
                if key in seen_pairs:
                    continue

                out = {
                    "prompt": prompt,
                    "chosen": chosen,
                    "rejected": rejected,
                    "code_id": code_id
                }
                f.write(json.dumps(out, ensure_ascii=False) + "\n")
                seen_pairs.add(key)
                new_pairs += 1

    save_seen()

    print(f"[INFO] Added {new_pairs} NEW DPO samples.")
    print(f"[INFO] Total seen_pairs: {len(seen_pairs)}")


if __name__ == "__main__":
    main()
