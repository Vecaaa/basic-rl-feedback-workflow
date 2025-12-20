#!/usr/bin/env bash
set -euo pipefail

# ---- Adjust these variables for your environment (if needed) ----
LLVM_PREFIX=${LLVM_PREFIX:-/scratch/$(whoami)/llvm-14/bin}
KLEE_BIN=${KLEE_BIN:-/scratch/$(whoami)/klee/build/bin/klee}
PROJECT_DIR=${PROJECT_DIR:-$(pwd)}
MOCK_DIR="${PROJECT_DIR}/klee_mocks"
ITER_TMP_DIR=${ITER_TMP_DIR:-/scratch/$(whoami)/llm_tmp}
CODE_BC=${CODE_BC:-/scratch/$(whoami)/llm_outputs/iter_1/bitcode/code_1.bc}
OUT_LINKED_BC="${ITER_TMP_DIR}/code_1.linked.bc"
OUT_KLEE_DIR="${ITER_TMP_DIR}/klee_code_1_debug"
TIMEOUT_SEC=${TIMEOUT_SEC:-20}

CLANG="${LLVM_PREFIX}/clang"
LLVM_LINK="${LLVM_PREFIX}/llvm-link"
LLVM_NM="${LLVM_PREFIX}/llvm-nm"

mkdir -p "$MOCK_DIR" "$ITER_TMP_DIR" "$OUT_KLEE_DIR"

echo "Runiter: CLANG=$CLANG  LLVM_LINK=$LLVM_LINK  KLEE=$KLEE_BIN"
echo "Mock dir: $MOCK_DIR"
echo "Target bc: $CODE_BC"
echo

# 1) build mocks -> .bc
echo ">>> Building mock_scanf.bc"
"$CLANG" -I"${MOCK_DIR}" -emit-llvm -O1 -c -g "${MOCK_DIR}/mock_scanf.c" -o "${MOCK_DIR}/mock_scanf.bc"

echo ">>> Building mock_libc.bc"
"$CLANG" -emit-llvm -O1 -c -g "${MOCK_DIR}/mock_libc.c" -o "${MOCK_DIR}/mock_libc.bc"

# 2) link target + mocks
echo ">>> Linking to $OUT_LINKED_BC"
"$LLVM_LINK" -o "$OUT_LINKED_BC" "$CODE_BC" "${MOCK_DIR}/mock_scanf.bc" "${MOCK_DIR}/mock_libc.bc"

echo ">>> nm check (exports/unresolved)"
"$LLVM_NM" "$OUT_LINKED_BC" | egrep " T (scanf|__isoc99_scanf|getchar|strcpy|memcpy|memset|strlen|printf)" || true
"$LLVM_NM" "$OUT_LINKED_BC" | grep " U " || echo "no unresolved (except klee_make_symbolic etc.)"

# 3) run KLEE with short timeout for debugging
echo ">>> Running KLEE (outdir=$OUT_KLEE_DIR, timeout=${TIMEOUT_SEC}s)"
rm -rf "$OUT_KLEE_DIR"
TMP_LOG=$(mktemp)
timeout "${TIMEOUT_SEC}s" "$KLEE_BIN" \
  --exit-on-error \
  --max-time="${TIMEOUT_SEC}s" \
  --max-solver-time=3s \
  --only-output-states-covering-new \
  --output-dir="$OUT_KLEE_DIR" \
  "$OUT_LINKED_BC" > "$TMP_LOG" 2>&1 || true

if [ -d "$OUT_KLEE_DIR" ]; then
  mv "$TMP_LOG" "$OUT_KLEE_DIR/klee.log"
  echo "Saved KLEE log -> $OUT_KLEE_DIR/klee.log"
else
  echo "KLEE did not create outdir. Dumping captured stdout:"
  cat "$TMP_LOG"
  rm -f "$TMP_LOG"
fi

echo ">>> Listing $OUT_KLEE_DIR"
ls -lah "$OUT_KLEE_DIR" || true
echo ">>> ktest summary (if exists)"
[ -f "$OUT_KLEE_DIR/test000001.ktest" ] && "$KLEE_BIN/klee-replay" >/dev/null 2>&1 || true

echo "Done."
