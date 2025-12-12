#!/usr/bin/env python3
"""
Rebuild DPO data from iteration outputs using the latest reward logic.
"""

import json
import os
import re
from collections import defaultdict
from typing import Dict, List, Set, Tuple
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
MANUAL_DPO_DIR = PROJECT_ROOT / "manual_dpo"
OUT_FILE = PROJECT_ROOT / "dpo_data.jsonl"
SEEN_FILE = PROJECT_ROOT / "seen_pairs.json"


def resolve_run_dirs() -> List[Path]:
    """
    Determine which run directories to extract from.
    If DPO_OUTPUT_BASE/OUTPUT_BASE points to a specific run, only that run is used.
    Otherwise, gather every run under $LLM_OUTPUT_ROOT (default /scratch/$USER/llm_outputs_runs).
    """
    env_override = os.environ.get("DPO_OUTPUT_BASE") or os.environ.get("OUTPUT_BASE")
    if env_override:
        base_path = Path(env_override).expanduser()
        if not base_path.exists():
            raise SystemExit(f"[ERROR] OUTPUT_BASE override '{base_path}' not found.")
        if any(base_path.glob("iter_*")):
            print(f"[INFO] Using single run folder from environment: {base_path}")
            return [base_path]
        run_dirs = sorted(
            [
                p
                for p in base_path.iterdir()
                if p.is_dir() and any(p.glob("iter_*"))
            ],
            key=lambda p: p.stat().st_mtime,
        )
        if not run_dirs:
            raise SystemExit(f"[ERROR] No iter_* directories found under {base_path}")
        print(f"[INFO] Using {len(run_dirs)} run folders under {base_path}")
        return run_dirs

    user = os.environ.get("USER", os.getlogin())
    runs_root = Path(os.environ.get("LLM_OUTPUT_ROOT", f"/scratch/{user}/llm_outputs_runs"))
    run_dirs: List[Path] = []
    if runs_root.exists():
        run_dirs = sorted(
            [
                p
                for p in runs_root.iterdir()
                if p.is_dir() and any(p.glob("iter_*"))
            ],
            key=lambda p: p.stat().st_mtime,
        )
    legacy = Path(f"/scratch/{user}/llm_outputs")
    if legacy.exists() and any(legacy.glob("iter_*")):
        run_dirs.append(legacy)

    if not run_dirs:
        raise SystemExit("[ERROR] No run directories found. Set DPO_OUTPUT_BASE or run the pipeline first.")

    print(f"[INFO] Found {len(run_dirs)} run folders for extraction.")
    return run_dirs


RUN_DIRS = resolve_run_dirs()


def compute_reward(iter_dir: Path, code_id: int) -> float:
    """
    Reward combines compile success, KLEE health, and CodeQL signal.
    """
    compiled_dir = iter_dir / "compiled_output"
    feedback_dir = iter_dir / "feedback"
    klee_dir = iter_dir / "klee_output"

    base = f"code_{code_id}"

    compile_ok = 1
    compile_warnings = 0
    compile_failures = compiled_dir / "compile_failures.txt"
    if compile_failures.exists():
        txt = compile_failures.read_text(encoding="utf-8", errors="ignore")
        if re.search(rf"\b{base}\b", txt):
            compile_ok = 0

    compile_log = compiled_dir / f"{base}_compile.log"
    if compile_log.exists():
        for line in compile_log.read_text(encoding="utf-8", errors="ignore").splitlines():
            if "warning:" in line:
                compile_warnings += 1

    code_klee_dir = klee_dir / base
    klee_errs = 0
    klee_tests = 0
    klee_crashed = 0
    if code_klee_dir.exists():
        all_errs = [p for p in code_klee_dir.glob("*.err") if "mock" not in p.name.lower()]
        klee_errs = len(all_errs)
        klee_tests = sum(1 for _ in code_klee_dir.glob("*.ktest"))
        log_file = klee_dir / f"klee_{base}.log"
        if log_file.exists():
            log_txt = log_file.read_text(encoding="utf-8", errors="ignore").lower()
            if any(tok in log_txt for tok in ("haltimer", "timeout", "segmentation fault", "dumped core")):
                klee_crashed = 1

    codeql_file = feedback_dir / f"{base}_codeql.txt"
    codeql_issues = 0
    if codeql_file.exists():
        txt = codeql_file.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r"—\s*([0-9]+)\s+issues found", txt)
        if m:
            codeql_issues = int(m.group(1))

    compile_score = 1.0 if compile_ok else 0.0
    warning_penalty = min(0.5, 0.02 * compile_warnings)

    klee_score = 0.0
    if klee_tests > 0:
        klee_score += 0.4
    if klee_tests > 0 and klee_errs == 0:
        klee_score += 0.6
    else:
        klee_score -= 0.1 * klee_errs
    if klee_crashed:
        klee_score -= 0.5
    klee_score = max(-1.0, min(1.0, klee_score))

    codeql_score = 1.0 if codeql_issues == 0 else 1.0 / (1.0 + codeql_issues)

    return 3.0 * compile_score + 2.0 * klee_score + 1.0 * codeql_score - warning_penalty


def structural_ok(current_code: str, fixed_code: str) -> bool:
    def func_names(blob: str) -> Set[str]:
        pattern = r'\b(?:int|void|char|float|double|long|short|unsigned|struct\s+\w+)\s+(\w+)\s*\('
        return set(re.findall(pattern, blob))

    cur_lines = [ln for ln in current_code.splitlines() if ln.strip()]
    fix_lines = [ln for ln in fixed_code.splitlines() if ln.strip()]
    if len(cur_lines) >= 10 and len(fix_lines) < max(5, int(len(cur_lines) * 0.5)):
        return False

    cur_funcs = func_names(current_code)
    fix_funcs = func_names(fixed_code)
    cur_non_main = {f for f in cur_funcs if f != "main"}
    fix_non_main = {f for f in fix_funcs if f != "main"}

    if cur_non_main and not fix_non_main:
        return False
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


def collect_records(run_dirs: List[Path]) -> Dict[int, List[dict]]:
    records = defaultdict(list)
    for run_dir in run_dirs:
        for iter_dir in sorted(run_dir.glob("iter_*")):
            try:
                iter_idx = int(iter_dir.name.split("_")[1])
            except (IndexError, ValueError):
                continue

            cleaned_dir = iter_dir / "cleaned_code"
            gen_dir = iter_dir / "generated_code"
            if not cleaned_dir.exists() or not gen_dir.exists():
                continue

            for cur_file in cleaned_dir.glob("code_*.c"):
                try:
                    code_id = int(cur_file.stem.split("_")[1])
                except (IndexError, ValueError):
                    continue

                rep_file = gen_dir / f"repair_prompt_{code_id}.txt"
                fix_file = gen_dir / f"code_{code_id}.c"
                if not rep_file.exists() or not fix_file.exists():
                    continue

                cur_text = cur_file.read_text(encoding="utf-8", errors="ignore")
                fix_text = fix_file.read_text(encoding="utf-8", errors="ignore")
                if not structural_ok(cur_text, fix_text):
                    continue

                reward = compute_reward(iter_dir, code_id)
                prompt = build_prompt(cur_text, rep_file.read_text(encoding="utf-8", errors="ignore"))

                records[code_id].append(
                    {
                        "iter": iter_idx,
                        "run": run_dir.name,
                        "prompt": prompt,
                        "fixed_code": fix_text,
                        "reward": reward,
                    }
                )

    return records


def main():
    seen_pairs: Set[Tuple] = set()
    out_lines: List[str] = []

    records = collect_records(RUN_DIRS)

    for code_id, attempts in records.items():
        if len(attempts) < 2:
            continue
        attempts.sort(key=lambda r: (r["reward"], r["iter"]))
        worst = attempts[0]
        best = attempts[-1]
        if best["reward"] <= worst["reward"]:
            continue

        key = (code_id, best["run"], best["iter"], worst["run"], worst["iter"])
        if key in seen_pairs:
            continue
        seen_pairs.add(key)

        out_lines.append(
            json.dumps(
                {
                    "prompt": best["prompt"],
                    "chosen": best["fixed_code"],
                    "rejected": worst["fixed_code"],
                    "code_id": code_id,
                },
                ensure_ascii=False,
            )
        )

    manual_added = 0
    if MANUAL_DPO_DIR.is_dir():
        for subdir in sorted(MANUAL_DPO_DIR.iterdir()):
            if not subdir.is_dir():
                continue
            m = re.match(r"code_(\d+)$", subdir.name)
            if not m:
                continue
            code_id = int(m.group(1))
            cur = subdir / "current.c"
            rep = subdir / "repair_instructions.txt"
            chosen = subdir / "chosen.c"
            rejected = subdir / "rejected.c"
            if not (cur.exists() and rep.exists() and chosen.exists() and rejected.exists()):
                continue

            key = ("manual", code_id)
            if key in seen_pairs:
                continue
            seen_pairs.add(key)

            out_lines.append(
                json.dumps(
                    {
                        "prompt": build_prompt(
                            cur.read_text(encoding="utf-8", errors="ignore"),
                            rep.read_text(encoding="utf-8", errors="ignore"),
                        ),
                        "chosen": chosen.read_text(encoding="utf-8", errors="ignore"),
                        "rejected": rejected.read_text(encoding="utf-8", errors="ignore"),
                        "code_id": code_id,
                    },
                    ensure_ascii=False,
                )
            )
            manual_added += 1

    unique_lines: List[str] = []
    line_hash: Set[str] = set()
    for line in out_lines:
        if line not in line_hash:
            unique_lines.append(line)
            line_hash.add(line)

    SEEN_FILE.write_text(
        json.dumps([list(item) for item in seen_pairs], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    OUT_FILE.write_text("\n".join(unique_lines) + ("\n" if unique_lines else ""), encoding="utf-8")

    print(f"[INFO] Generated {len(unique_lines)} total DPO samples ({manual_added} manual).")
    print(f"[INFO] Aggregated {len(RUN_DIRS)} run(s): {[p.name for p in RUN_DIRS]}")


if __name__ == "__main__":
    main()
