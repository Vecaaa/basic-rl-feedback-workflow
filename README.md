# Basic RL Feedback Workflow

An iterative secure code generation and repair pipeline that uses LLM inference, KLEE symbolic execution, and CodeQL static analysis to produce security-hardened C code. Generated (chosen / rejected) pairs are compiled into a DPO dataset for fine-tuning a code-repair model.

---

## Overview

The pipeline runs in two stages per iteration:

```
Iteration 1
  LLM (generate) → code_i.c
       │
       ▼
  CodeQL + KLEE (feedback)
       │
       ▼
Iteration 2+
  LLM (analyze)  → repair_prompt_i.txt
       │
       ▼
  LLM (repair)   → code_i.c  (repaired)
       │
       ▼
  CodeQL + KLEE (feedback)  ──► loop
       │
       ▼
  extract_training_data.py  → dpo_data.jsonl
       │
       ▼
  train_dpo.py              → fine-tuned model checkpoint
```

The `chosen` responses (code with fewer/no vulnerabilities) and `rejected` responses (original buggy code) are stored in `manual_dpo/` and automatically merged into `dpo_data.jsonl` by `extract_training_data.py`. The final DPO fine-tuning step uses TRL + LoRA on top of `deepseek-ai/deepseek-coder-1.3b-instruct`.

---

## Repository Structure

```
.
├── config.json                  # Model paths, generation parameters
├── gpu_requirements.txt         # Python/CUDA dependencies (pip)
├── klee_requirements.txt        # Reference list of system deps for KLEE
├── prerequisites-setup.sh       # Full from-source install: LLVM-14, KLEE, Z3, CodeQL
│
├── run_llm3.py                  # Main LLM driver (generate / analyze / repair)
├── run_codeql2.py               # CodeQL database build + security query runner
├── extract_training_data.py     # Collects iter outputs → dpo_data.jsonl
├── train_dpo.py                 # DPO fine-tuning with TRL + LoRA
├── clean_code.py                # Strips markdown fences from raw LLM output
│
├── runiter.sh                   # Single-iteration KLEE debug runner
├── run_iter2.sh                 # Full multi-iteration pipeline driver
├── run_iter_from.sh             # Resume pipeline from a specific iteration
├── batch_run_models.sh          # Sweep multiple models across a prompt list
├── analyze_only.sh              # Run only the analysis/feedback stage
├── rerun_iter1_analysis.sh      # Re-run iter-1 analysis on existing outputs
│
├── klee_mocks/
│   ├── mock_libc.c              # Symbolic stubs for libc functions
│   └── mock_scanf.c             # Symbolic stdin via klee_make_symbolic
│
├── manual_dpo/                  # Hand-curated DPO examples
│   └── code_<N>/
│       ├── current.c            # Original generated code
│       ├── chosen.c             # Secure repaired version
│       ├── rejected.c           # Buggy/vulnerable version
│       └── repair_instructions.txt
│
├── prompts.txt                  # Input prompts for code generation
├── dpo_data.jsonl               # Auto-generated DPO training pairs
├── seen_pairs.json              # Deduplication index for DPO extraction
│
└── compiled_output/             # Compiled bitcode output directory
```

---

## Prerequisites

### System Tools (built from source by `prerequisites-setup.sh`)

| Tool | Version | Purpose |
|---|---|---|
| LLVM / Clang | 14 | Compile C → LLVM bitcode for KLEE |
| KLEE | latest | Symbolic execution / path exploration |
| Z3 | latest | SMT solver backend for KLEE |
| CodeQL | latest | Static security analysis |
| CMake / Ninja | latest | Build system for KLEE |

Run the full setup (takes ~30–60 min, builds to `/scratch/$USER/`):

```bash
bash prerequisites-setup.sh
```

### Python Dependencies

Requires Python 3.10+ and CUDA 12.1.

```bash
pip install -r gpu_requirements.txt
```

Key packages: `torch 2.5.1+cu121`, `transformers 4.57.1`, `trl`, `peft`, `accelerate`, `datasets`.

---

## Configuration

Edit `config.json` before running:

```json
{
  "MODEL_PATH":   "deepseek-ai/deepseek-coder-1.3b-base",
  "HUGGINGFACE_TOKEN": "",
  "max_new_tokens": 1024,
  "num_return_sequences": 1,
  "subset_size": 100,
  "MODEL_SMALL": "deepseek-ai/deepseek-coder-1.3b-instruct",
  "MODEL_BIG":   "codellama/CodeLlama-13b-Instruct-hf"
}
```

Set `HUGGINGFACE_TOKEN` if accessing gated models (e.g. CodeLlama). The active model can be overridden at runtime via the `MODEL` environment variable.

---

## Usage

### 1. Single-iteration debug run (KLEE only)

```bash
# Check KLEE linking + symbolic execution on one bitcode file
CODE_BC=/scratch/$USER/llm_outputs/iter_1/bitcode/code_1.bc bash runiter.sh
```

### 2. Full multi-iteration pipeline

```bash
bash run_iter2.sh
```

This script drives the generate → analyze → repair → feedback loop for all `subset_size` code samples across multiple iterations.

### 3. Resume from a specific iteration

```bash
bash run_iter_from.sh 3   # resume from iteration 3
```

### 4. Batch sweep across models

```bash
bash batch_run_models.sh   # reads prompts.txt, runs each model in MODELS array
```

### 5. Rebuild DPO training data

```bash
python extract_training_data.py
```

Scans all iteration run directories and `manual_dpo/`, writes `dpo_data.jsonl`.

### 6. Fine-tune with DPO

```bash
python train_dpo.py
```

Trains `deepseek-coder-1.3b-instruct` with LoRA using the DPO pairs in `dpo_data.jsonl`. Checkpoint is saved to `/scratch/$USER/fixer-dpo-checkpoint/`.

---

## LLM Driver Modes (`run_llm3.py`)

```bash
# Iteration 1 — generate code from prompts
python run_llm3.py --task generate

# Iteration 2+ step 1 — analyze feedback, produce repair prompt
python run_llm3.py --task analyze

# Iteration 2+ step 2 — apply repair
python run_llm3.py --task repair

# Process only specific indices
python run_llm3.py --task repair --only 3 7 12
```

Environment variable overrides:

| Variable | Default | Description |
|---|---|---|
| `MODEL` | from `config.json` | HuggingFace model ID or local path |
| `HF_CACHE` | `/scratch/$USER/hf_cache` | HuggingFace cache dir |
| `HF_LOCAL_ONLY` | `0` | Set `1` to disable downloads |

---

## DPO Data Format

Each line in `dpo_data.jsonl` is a JSON object:

```json
{
  "prompt":   "Write a C function that parses user input...",
  "chosen":   "/* secure repaired version */\n...",
  "rejected": "/* original buggy version */\n..."
}
```

---

## Hardware Requirements

- GPU with ≥ 12 GB VRAM recommended (tested on RTX 4070 Super / A100)
- CUDA 12.1+ driver
- ~50 GB scratch disk space (LLVM build + HF model cache + KLEE outputs)

---

## Notes

- All tools are installed to `/scratch/$USER/` to avoid needing root access (HPC cluster–friendly).
- `clean_code.py` strips markdown code fences from raw LLM outputs before passing to CodeQL/KLEE.
- `seen_pairs.json` tracks already-extracted DPO pairs to prevent duplicates across incremental runs.
- Report files (`deepseek_report.txt`, `starcoder_report.txt`) contain sample analysis outputs from earlier evaluation runs.
