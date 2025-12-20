#!/bin/bash
set -e

USER_ID=$(whoami)
PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
OUTPUT_BASE=${OUTPUT_BASE:-/scratch/${USER_ID}/llm_outputs}
ITER=1

LLVM_PREFIX=${LLVM_PREFIX:-/scratch/${USER_ID}/llvm-14/bin}
CLANG_BIN="${LLVM_PREFIX}/clang"
LLVM_LINK="${LLVM_PREFIX}/llvm-link"
LLVM_NM="${LLVM_PREFIX}/llvm-nm"
CODEQL_HOME=${CODEQL_HOME:-/scratch/${USER_ID}/codeql}
KLEE_BIN=${KLEE_BIN:-/scratch/${USER_ID}/klee/build/bin/klee}

d="$OUTPUT_BASE/iter_${ITER}"
g="$d/generated_code"
c="$d/cleaned_code"
b="$d/bitcode"
bl="$d/bitcode_linked"
co="$d/compiled_output"
k="$d/klee_output"
f="$d/feedback"
r="$d/reports"
s="$d/signals"

mkdir -p "$b" "$bl" "$co" "$k" "$f" "$r" "$s"

echo "🧹 Re-cleaning code for iter_${ITER} ..."
for fsrc in "$g"/code_*.c; do
  base=$(basename "$fsrc")
  python "$PROJECT_DIR/clean_code.py" "$fsrc" "$c/$base"
done

echo "🔍 Re-running CodeQL ..."
export CC=/scratch/${USER_ID}/llvm-14/bin/clang
export CXX=/scratch/${USER_ID}/llvm-14/bin/clang++
python "$PROJECT_DIR/run_codeql2.py" "$c"

echo "🔧 Re-compiling + linking mocks ..."
: > "$co/compile_failures.txt"
for src in "$c"/code_*.c; do
  bn=$(basename "$src" .c); bc="$b/${bn}.bc"; log="$co/${bn}_compile.log"
  if "$CLANG_BIN" -Wall -Wextra -std=c11 -O1 -emit-llvm -c -g "$src" -o "$bc" 2> "$log"; then
    echo "   ✅ $bn"
    "$LLVM_LINK" -o "$bl/${bn}.bc" "$bc" "$PROJECT_DIR/klee_mocks/mock_scanf.bc" "$PROJECT_DIR/klee_mocks/mock_libc.bc" >>"$log" 2>&1 || {
      echo "$bn failed at link(mock) stage" >> "$co/compile_failures.txt"
      echo "   ❌ $bn (llvm-link failure)"
    }
  else
    echo "$bn failed (see $(realpath --relative-to="$d" "$log"))" >> "$co/compile_failures.txt"
    echo "   ❌ $bn"
  fi
done

echo "🧠 Re-running KLEE ..."
rm -f "$s/klee_ok.flag"; : > "$k/klee_errors_summary.txt"
for bc in "$bl"/code_*.bc; do
  bn=$(basename "$bc" .bc)
  out="$k/$bn"
  logfile="$k/klee_${bn}.log"
  rm -rf "$out"
  /usr/bin/timeout --foreground --preserve-status 10s "$KLEE_BIN" \
    --max-time=10s --max-solver-time=3s --max-memory=1024 \
    --max-sym-array-size=4096 --max-instructions=200000 \
    --only-output-states-covering-new \
    --output-dir="$out" "$bc" >"$logfile" 2>&1 || true
done

echo "📋 Rebuilding per-file feedback ..."
# Source run_iter2.sh to access the build_feedback_per_file function,
# and use SKIP_MAIN_LOOP=1 to avoid triggering the main loop and clearing OUTPUT_BASE.
SKIP_MAIN_LOOP=1 source "$PROJECT_DIR/run_iter2.sh"
build_feedback_per_file "$d"

echo "完成：iter_${ITER} 的 CodeQL/compile/KLEE/feedback 已按新逻辑重算（代码本身未改动）。"
