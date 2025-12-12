#!/bin/bash
# ==========================================================
# Resume Iterative Feedback Loop from Iteration N
# ==========================================================
# Usage: START_ITER=2 ./run_iter_from.sh
# This script skips iteration 1 and starts from a specified iteration.
# Useful for testing changes to the analysis/repair loop.
# ==========================================================

# -------- Configuration --------
START_ITER=${START_ITER:-8}  # Default: start from iteration 2
MAX_ITERS=${MAX_ITERS:-20}
TIMEOUT_KLEE=${TIMEOUT_KLEE:-10s}
STOP_ON_ZERO_ISSUES=${STOP_ON_ZERO_ISSUES:-1}
REQUIRE_TOOLS=${REQUIRE_TOOLS:-1}
LLVM_PREFIX=${LLVM_PREFIX:-/scratch/$(whoami)/llvm-14/bin}
CODEQL_HOME=${CODEQL_HOME:-/scratch/$(whoami)/codeql}
KLEE_BIN=${KLEE_BIN:-/scratch/$(whoami)/klee/build/bin/klee}
VENV_PATH=${VENV_PATH:-/scratch/$(whoami)/klee-venv}
PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

USER_ID=$(whoami)
DEFAULT_OUTPUT_ROOT="/scratch/${USER_ID}/llm_outputs_runs"
if [ -z "${OUTPUT_BASE}" ]; then
  OUTPUT_ROOT=${OUTPUT_ROOT:-$DEFAULT_OUTPUT_ROOT}
  if [ ! -d "$OUTPUT_ROOT" ]; then
    echo "❌ OUTPUT_ROOT not found: $OUTPUT_ROOT"
    echo "   Set OUTPUT_BASE to an existing run directory."
    exit 1
  fi
  latest_run=$(ls -1t "$OUTPUT_ROOT" 2>/dev/null | head -n 1)
  if [ -z "$latest_run" ]; then
    echo "❌ No run directories found under $OUTPUT_ROOT"
    echo "   Set OUTPUT_BASE manually before running."
    exit 1
  fi
  OUTPUT_BASE="$OUTPUT_ROOT/$latest_run"
else
  OUTPUT_ROOT=$(dirname "$OUTPUT_BASE")
fi
RUN_TAG=${RUN_TAG:-$(basename "$OUTPUT_BASE")}

export PATH="$LLVM_PREFIX:$PATH"
export CODEQL_HOME
export LD_LIBRARY_PATH="/scratch/${USER_ID}/z3-build/lib:/scratch/${USER_ID}/sqlite/lib:$LD_LIBRARY_PATH"
export KLEE_INCLUDE=${KLEE_INCLUDE:-/scratch/$(whoami)/klee/include}

export HF_HOME="/scratch/$USER/hf_cache"
export TRANSFORMERS_CACHE="/scratch/$USER/hf_cache"
export HF_DATASETS_CACHE="/scratch/$USER/hf_cache"

echo "🚀 Iterative Secure CodeGen Pipeline (resuming from iteration $START_ITER)"
echo "📁 PROJECT_DIR : $PROJECT_DIR"
echo "📦 KLEE headers: $KLEE_INCLUDE"
echo "Output root    : $OUTPUT_ROOT"
echo "Run tag        : $RUN_TAG"
echo "Base           : $OUTPUT_BASE"
echo "Start Iter     : $START_ITER"
echo "Max Iters      : $MAX_ITERS"
echo "=========================================="

# Validate START_ITER
if [ "$START_ITER" -lt 2 ]; then
    echo "❌ START_ITER must be >= 2 (use run_iter2.sh for full pipeline)"
    exit 1
fi

# Check that previous iteration exists
PREV_ITER=$((START_ITER - 1))
PREV_DIR="$OUTPUT_BASE/iter_${PREV_ITER}"
if [ ! -d "$PREV_DIR" ]; then
    echo "❌ Previous iteration directory not found: $PREV_DIR"
    echo "   You need iteration $PREV_ITER to exist before starting from iteration $START_ITER"
    exit 1
fi

if [ ! -d "$PREV_DIR/cleaned_code" ] || [ ! -d "$OUTPUT_BASE/iter_1/generated_code/prompts" ]; then
    echo "❌ Required directories missing from previous iteration:"
    echo "   - $PREV_DIR/cleaned_code"
    echo "   - $OUTPUT_BASE/iter_1/generated_code/prompts"
    exit 1
fi

# -------- tools --------
CLANG_BIN="${LLVM_PREFIX}/clang"
[ -x "$CLANG_BIN" ] || CLANG_BIN=$(command -v clang || true)
[ -x "$KLEE_BIN" ] || KLEE_BIN=""
CODEQL_CLI=$(command -v "$CODEQL_HOME/codeql" || command -v codeql || true)
LLVM_NM="${LLVM_PREFIX}/llvm-nm"
LLVM_LINK="${LLVM_PREFIX}/llvm-link"
LLVM_DIS="${LLVM_PREFIX}/llvm-dis"

if [ -z "$CLANG_BIN" ] || [ -z "$KLEE_BIN" ] || [ -z "$CODEQL_CLI" ] || [ ! -x "$LLVM_LINK" ]; then
  echo "🧰 Tooling:"
  echo "   clang  = ${CLANG_BIN:-MISSING}"
  echo "   klee   = ${KLEE_BIN:-MISSING}"
  echo "   codeql = ${CODEQL_CLI:-MISSING}"
  echo "   llvm-link = ${LLVM_LINK:-MISSING}"
  [ "$REQUIRE_TOOLS" = "1" ] && { echo "❌ Required tools missing"; exit 1; }
fi

# -------- paths for mocks --------
MOCK_DIR="$PROJECT_DIR/klee_mocks"
MOCK_SCANF_C="$MOCK_DIR/mock_scanf.c"
MOCK_SCANF_BC="$MOCK_DIR/mock_scanf.bc"
MOCK_LIBC_C="$MOCK_DIR/mock_libc.c"
MOCK_LIBC_BC="$MOCK_DIR/mock_libc.bc"
mkdir -p "$MOCK_DIR"

log(){ echo -e "$@"; }
fail(){ echo "❌ $1"; exit 1; }
assert_file(){ [ -f "$1" ] || fail "missing file: $1"; }

# -------- venv & config --------
[ -d "$VENV_PATH" ] || fail "venv not found: $VENV_PATH"
source "$VENV_PATH/bin/activate" || fail "venv activate failed"
[ -f "$PROJECT_DIR/config.json" ] || fail "config.json missing"

# -------- build mocks --------
assert_file "$MOCK_SCANF_C"
assert_file "$MOCK_LIBC_C"

log "🧩 Building scanf mock  → $MOCK_SCANF_BC"
"$CLANG_BIN" -I"$KLEE_INCLUDE" -emit-llvm -O1 -c -g "$MOCK_SCANF_C" -o "$MOCK_SCANF_BC" \
  || fail "compile mock_scanf.c failed"

log "🧩 Building libc mock   → $MOCK_LIBC_BC"
"$CLANG_BIN" -I"$KLEE_INCLUDE" -emit-llvm -O1 -c -g "$MOCK_LIBC_C" -o "$MOCK_LIBC_BC" \
  || fail "compile mock_libc.c failed"

# ==========================================================
# Source the functions from run_iter2.sh
# ==========================================================
# We need: build_feedback_per_file, should_stop_now, run_iteration
# Skip the cleanup, venv, and mock building (already done above)

export SKIP_MAIN_LOOP=1
source "$PROJECT_DIR/run_iter2.sh"


# ==========================================================
# Clean up future iterations
# ==========================================================
echo "🧹 Cleaning up iterations $START_ITER to $MAX_ITERS ..."
for i in $(seq "$START_ITER" "$MAX_ITERS"); do
    iter_dir="$OUTPUT_BASE/iter_${i}"
    if [ -d "$iter_dir" ]; then
        echo "   Removing old directory: $iter_dir"
        rm -rf "$iter_dir"
    fi
done

# ==========================================================
# Main loop (starting from START_ITER)
# ==========================================================
overall_start=$(date +%s); last_good_iter=0
for i in $(seq "$START_ITER" "$MAX_ITERS"); do
  run_iteration "$i"
  if [ "$STOP_ON_ZERO_ISSUES" = "1" ] && should_stop_now "$OUTPUT_BASE/iter_${i}"; then
    last_good_iter="$i"
    echo "🎉 All checks passed at iteration $i — stopping."
    break
  fi
done

overall_end=$(date +%s)
FINAL_REPORT="$OUTPUT_BASE/final_summary.txt"

{
  echo "======================================================"
  echo "🏁 Final Evaluation Report (resumed from iter $START_ITER)"
  echo "======================================================"
  echo "Project : $PROJECT_DIR"
  echo "Base    : $OUTPUT_BASE"
  echo "Iters   : $START_ITER to $MAX_ITERS"
  echo "Runtime : $((overall_end-overall_start))s"
  echo ""
  echo "Iterations:"; ls -1 "$OUTPUT_BASE" | grep -E '^iter_' | sed 's/^/  - /'
  echo ""
  if [ "$last_good_iter" -gt 0 ]; then
    echo "✅ Converged at: iter_${last_good_iter}"
  else
    echo "⚠️ No convergence"
  fi
  echo ""
  echo "Per-iteration dirs: generated_code/ cleaned_code/ bitcode/ bitcode_linked/ compiled_output/ klee_output/ reports/ signals/"
  echo "Mocks: $MOCK_SCANF_BC , $MOCK_LIBC_BC"
  echo "======================================================"
} > "$FINAL_REPORT"

echo "✅ Final report: $FINAL_REPORT"
