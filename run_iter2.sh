#!/bin/bash
# ==========================================================
# Secure Code Generation & Analysis — Iterative Feedback Loop (strict, per-file, naive+mock)
# Two-Stage LLM Fixer Compatible Version
# ==========================================================
#set -o pipefail

# -------- Tunables --------
MAX_ITERS=${MAX_ITERS:-20}
TIMEOUT_KLEE=${TIMEOUT_KLEE:-10s}
STOP_ON_ZERO_ISSUES=${STOP_ON_ZERO_ISSUES:-1}
REQUIRE_TOOLS=${REQUIRE_TOOLS:-1}
LLVM_PREFIX=${LLVM_PREFIX:-/scratch/$(whoami)/llvm-14/bin}
CODEQL_HOME=${CODEQL_HOME:-/scratch/$(whoami)/codeql}
KLEE_BIN=${KLEE_BIN:-/scratch/$(whoami)/klee/build/bin/klee}
VENV_PATH=${VENV_PATH:-/scratch/$(whoami)/klee-venv}
OUTPUT_BASE=${OUTPUT_BASE:-/scratch/$(whoami)/llm_outputs}
PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

USER_ID=$(whoami)
export PATH="$LLVM_PREFIX:$PATH"
export CODEQL_HOME
export LD_LIBRARY_PATH="/scratch/${USER_ID}/z3-build/lib:/scratch/${USER_ID}/sqlite/lib:$LD_LIBRARY_PATH"
export KLEE_INCLUDE=${KLEE_INCLUDE:-/scratch/$(whoami)/klee/include}

export HF_HOME="/scratch/$USER/hf_cache"
export TRANSFORMERS_CACHE="/scratch/$USER/hf_cache"
export HF_DATASETS_CACHE="/scratch/$USER/hf_cache"

echo "🚀 Iterative Secure CodeGen Pipeline (strict, per-file)"
echo "📁 PROJECT_DIR : $PROJECT_DIR"
echo "📦 KLEE headers: $KLEE_INCLUDE"
echo "Base           : $OUTPUT_BASE"
echo "Iters          : $MAX_ITERS"
echo "=========================================="

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

# ==========================================================
# 🧹 Pre-run Cleanup (only when running standalone)
# ==========================================================
if [ -z "$SKIP_MAIN_LOOP" ]; then
  echo "🧹 Cleaning $OUTPUT_BASE ..."
  rm -rf "$OUTPUT_BASE"
  mkdir -p "$OUTPUT_BASE"

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
fi

# ==========================================================
# Feedback Builder (unchanged, keep your full logic)
# ==========================================================
build_feedback_per_file() {
  local iter_dir="$1"
  local fb_dir="$iter_dir/feedback"
  local comp_dir="$iter_dir/compiled_output"
  local klee_dir="$iter_dir/klee_output"
  shopt -s nullglob

  for src in "$iter_dir/cleaned_code"/code_*.c; do
    local base=$(basename "$src" .c)   # e.g. code_1
    
    # Separated feedback files for strict priority
    local out_klee="$fb_dir/feedback_klee_${base}.txt"
    local out_compile="$fb_dir/feedback_compile_${base}.txt"
    local out_codeql="$fb_dir/feedback_codeql_${base}.txt"

    : > "$out_klee"
    : > "$out_compile"
    : > "$out_codeql"

    # ----- 1. CodeQL Processing -> out_codeql -----
    if [ -s "$fb_dir/${base}_codeql.txt" ]; then
      if grep -qE "— [1-9][0-9]* issues found" "$fb_dir/${base}_codeql.txt"; then
        echo "### CodeQL findings for ${base}.c" >> "$out_codeql"
        grep -Ei "database create failed|warning|error|unsafe|overflow|taint|leak|\[cpp/" \
          "$fb_dir/${base}_codeql.txt" | head -n 200 >> "$out_codeql"
        echo "" >> "$out_codeql"

        # 💡 针对 cpp/incomplete-parity-check 给一个可执行的 HINT
        if grep -q "cpp/incomplete-parity-check" "$fb_dir/${base}_codeql.txt"; then
          cat >> "$out_codeql" << 'EOF'
[HINT][CODEQL] Fix parity check: avoid "x % 2 == 1" on signed or possibly-negative values. Prefer "x % 2 != 0" or "(x & 1) != 0", or ensure x is non-negative before taking modulo.
EOF
          echo "" >> "$out_codeql"
        fi
      fi
    fi

    # ----- 2. Compilation Processing -> out_compile -----
    if [ -s "$comp_dir/compile_failures.txt" ]; then
      # Capture output first to avoid empty headers
      comp_out=$(grep -E "^${base}\b" "$comp_dir/compile_failures.txt")
      
      if [ -n "$comp_out" ]; then
        echo "### Compilation failures for ${base}.c" >> "$out_compile"
        echo "$comp_out" >> "$out_compile"
        echo "" >> "$out_compile"

        local clog="$comp_dir/${base}_compile.log"
        if [ -s "$clog" ]; then
          echo "----- compiler log excerpt -----" >> "$out_compile"
          grep -E "error:|warning:" "$clog" | head -n 8 | sed 's/^/    /' >> "$out_compile"
          echo "" >> "$out_compile"

          # 💡 常见错误 1：隐式声明（比如 min_operations）
          if grep -q "implicit declaration of function 'min_operations'" "$clog"; then
            echo "[HINT][COMPILER] Implement 'min_operations' or add its prototype *before* main; do not rely on implicit declarations." >> "$out_compile"
            echo "" >> "$out_compile"
          fi

          # 💡 常见错误 2：VLA / 变长数组导致的编译器/静态分析抱怨（辅助 KLEE HINT）
          if grep -q "variable length array" "$clog"; then
            echo "[HINT][COMPILER] Replace variable-length arrays like 'int a[n];' with fixed-size arrays (e.g. 'int a[MAX_N];') and check 'n <= MAX_N' before use." >> "$out_compile"
            echo "" >> "$out_compile"
          fi
        fi
      fi
    fi

    # ----- 3. KLEE Processing -> out_klee -----
    if [ -d "$klee_dir/$base" ]; then
      local find_out=($(find "$klee_dir/$base" -maxdepth 1 -type f -name "*.err" 2>/dev/null))
      local err_files=()
      if [ ${#find_out[@]} -gt 0 ]; then
        err_files=($(grep -L "mock_" "${find_out[@]}" 2>/dev/null))
      fi
      local nerrs=${#err_files[@]}

      if [ "$nerrs" -gt 0 ]; then
        echo "### KLEE errors for ${base}.c" >> "$out_klee"
        echo "${base} : ${nerrs} KLEE error(s)" >> "$out_klee"
        echo "" >> "$out_klee"

        for err in "${err_files[@]}"; do
          # Extract error type and line number
          local err_type=$(grep -i "^Error:" "$err" | head -1 | sed 's/Error: //')
          local err_line=$(grep -i "^Line:" "$err" | head -1 | sed 's/Line: //')
          
          # Get the actual code content at the error line
          local code_content=""
          if [ -n "$err_line" ] && [ -f "$iter_dir/cleaned_code/${base}.c" ]; then
            code_content=$(sed -n "${err_line}p" "$iter_dir/cleaned_code/${base}.c" 2>/dev/null)
          fi
          
          if grep -qi "concretized symbolic size" "$err"; then
            if [ -n "$err_line" ]; then
              echo "    Line $err_line: KLEE cannot handle symbolic-sized malloc/array (size depends on input)" >> "$out_klee"
              if [ -n "$code_content" ]; then
                echo "    Code: $code_content" >> "$out_klee"
              fi
            else
              echo "    KLEE error: Symbolic-sized allocation detected (malloc/array size depends on input)" >> "$out_klee"
            fi
            echo "    Fix: Replace with fixed-size array (e.g., int arr[MAX_N]) and add bounds check" >> "$out_klee"
          elif grep -qi "memory error" "$err"; then
            echo "    Memory error detected: $err_type" >> "$out_klee"
            if [ -n "$err_line" ]; then
              echo "    At line: $err_line" >> "$out_klee"
              if [ -n "$code_content" ]; then
                echo "    Code: $code_content" >> "$out_klee"
              fi
            fi
          else
            echo "    KLEE error: $err_type" >> "$out_klee"
            if [ -n "$err_line" ]; then
              echo "    At line: $err_line" >> "$out_klee"
              if [ -n "$code_content" ]; then
                echo "    Code: $code_content" >> "$out_klee"
              fi
            fi
          fi
          echo "" >> "$out_klee"
        done

      else
        # 没有 .err，但 log 可能有 crash / timeout 信息
        local logf="$klee_dir/klee_${base}.log"
        if grep -qiE "Segmentation fault|dumped core|KLEE: ERROR" "$logf" 2>/dev/null; then
          echo "### KLEE runtime issue for ${base}.c" >> "$out_klee"
          grep -iE "KLEE: ERROR|Segmentation fault|out of memory|dumped core|concretized symbolic size" "$logf" | head -n 10 | sed 's/^/    /' >> "$out_klee"
          echo "" >> "$out_klee"
        fi
      fi


    fi

    # Note: Priority logic (KLEE > Compile > CodeQL) is now handled in run_llm3.py
    # The separated feedback files are read directly by the analyzer

    # ---- Simplify each separated feedback file before LLM sees it ----
    for feedback_file in "$out_klee" "$out_compile" "$out_codeql"; do
      if [ ! -s "$feedback_file" ]; then continue; fi
      
      tmp_s="${feedback_file}.simplified"
      awk '
        /^[[:space:]]*$/ { next }
        /-----/ { next }
        /assembly\.ll/ { next }
        /Stack:/ { next }
        /State:/ { next }
        /Info:/ { next }
        /\.ktest/ { next }
        /\.err/ && !/KLEE_RULE|Error|Line/ { next }

        {
          if ($0 ~ /Line.*KLEE|Fix:|Memory error|KLEE error|Error|WARNING|Code:/) print
          else if ($0 ~ /^###/) print
          else if ($0 ~ /\[cpp\//) print
        }
      ' "$feedback_file" > "$tmp_s"

      # If simplified non-empty, overwrite
      if [ -s "$tmp_s" ]; then
        mv "$tmp_s" "$feedback_file"
        
        # Check if file contains ONLY a header (starts with ###) and nothing else
        # Count non-header lines (lines that don't start with ###)
        non_header_lines=$(grep -v '^###' "$feedback_file" | grep -v '^[[:space:]]*$' | wc -l)
        if [ "$non_header_lines" -eq 0 ]; then
          # File has only header(s), no actual error content - remove it
          rm -f "$feedback_file"
          : > "$feedback_file"  # Create empty file to maintain consistency
        fi
      else
        rm -f "$tmp_s"
      fi
    done
  done
}

# ==========================================================
# Stopping condition (unchanged)
# ==========================================================
should_stop_now(){
  local d="$1"
  [ "$REQUIRE_TOOLS" = "0" ] && return 1
  [ -f "$d/signals/codeql_ok.flag" ]   || return 1
  [ -f "$d/signals/compile_ok.flag" ]  || return 1
  [ -f "$d/signals/klee_ok.flag" ]     || return 1
  return 0
}

# ==========================================================
#                 🔥 Iteration Core Logic 🔥
# ==========================================================
run_iteration(){
  local iter="$1"
  local d="$OUTPUT_BASE/iter_${iter}"
  local g="$d/generated_code" c="$d/cleaned_code" b="$d/bitcode" bl="$d/bitcode_linked" \
        co="$d/compiled_output" k="$d/klee_output" f="$d/feedback" r="$d/reports" s="$d/signals"
  mkdir -p "$g" "$c" "$b" "$bl" "$co" "$k" "$f" "$r" "$s"

  echo ""; echo "==============================="
  echo "🌀 Iteration $iter  →  $d"
  echo "==============================="

  # ==========================================================
  # 1) LLM Generation (Two-Model: Analyze -> Repair)
  # ==========================================================
  echo "Step 1: LLM generate/repair..."

  # Load Config for Models
  MODEL_FIXER="deepseek-ai/deepseek-coder-6.7b-instruct"
  MODEL_ANALYZER="mistralai/Mistral-7B-Instruct-v0.2"

  if [ "$iter" -eq 1 ]; then
    # ------ First iteration: Generate with Fixer ------
    echo "🤖 Iter 1: Generating with Model A (Fixer): $MODEL_FIXER"
    
    OUTPUT_DIR="$g" MODEL="$MODEL_FIXER" python "$PROJECT_DIR/run_llm3.py" --task generate \
      || fail "LLM gen failed (iter $iter)"
      
  else
    # ------ Subsequent iterations: Clean → Analyze → CodeQL/KLEE → Analyze → Repair ------
    local pd="$OUTPUT_BASE/iter_1/generated_code/prompts"
    [ -d "$pd" ] || fail "Missing prompts snapshot from iter_1: $pd"

    local prev_clean="$OUTPUT_BASE/iter_$((iter-1))/cleaned_code"
    local prev_fb="$OUTPUT_BASE/iter_$((iter-1))/feedback"
    [ -d "$prev_clean" ] || fail "Missing cleaned_code: $prev_clean"
    [ -d "$prev_fb" ] || fail "Missing feedback dir: $prev_fb"

    # Copy previous clean code as baseline for all files
    cp -a "$prev_clean"/code_*.c "$g"/ 2>/dev/null || true
    
    # --- STEP 1: Clean code first to prepare for analysis ---
    echo "   🧹 [1/4] Cleaning code..."
    shopt -s nullglob
    for fsrc in "$g"/code_*.c; do
      base=$(basename "$fsrc")
      python "$PROJECT_DIR/clean_code.py" "$fsrc" "$c/$base" \
        || fail "clean_code failed"
    done

    # --- IDENTIFY FILES THAT PASSED BOTH TESTS IN PREVIOUS ITERATION ---
    echo "   🔍 Identifying files that passed all tests in previous iteration..."
    declare -A PASSED_FILES
    prev_signals="$OUTPUT_BASE/iter_$((iter-1))/signals"
    
    for src in "$c"/code_*.c; do
      base=$(basename "$src" .c)
      num=${base#code_}
      
      # Check if file passed CodeQL in previous iteration
      prev_codeql_ok=0
      if [ -f "$prev_fb/${base}_codeql.txt" ]; then
        if ! grep -qE "— [1-9][0-9]* issues found" "$prev_fb/${base}_codeql.txt" 2>/dev/null; then
          prev_codeql_ok=1
        fi
      fi
      
      # Check if file passed KLEE in previous iteration
      prev_klee_ok=0
      prev_klee_dir="$OUTPUT_BASE/iter_$((iter-1))/klee_output"
      if [ -d "$prev_klee_dir/$base" ]; then
        # Count non-mock errors
        local find_out=($(find "$prev_klee_dir/$base" -maxdepth 1 -type f -name "*.err" 2>/dev/null))
        local err_files=()
        if [ ${#find_out[@]} -gt 0 ]; then
          err_files=($(grep -L "mock_" "${find_out[@]}" 2>/dev/null))
        fi
        if [ ${#err_files[@]} -eq 0 ]; then
          prev_klee_ok=1
        fi
      fi
      
      # Mark as passed if both tests passed
      if [ "$prev_codeql_ok" -eq 1 ] && [ "$prev_klee_ok" -eq 1 ]; then
        PASSED_FILES[$base]=1
        echo "      ✅ $base passed both tests in iter $((iter-1)), will skip retesting"
      fi
    done

    # --- STEP 2: Reuse feedback from previous iteration's final check ---
    # Instead of re-running CodeQL and KLEE, we use the results from the previous iteration's
    # final check, which already tested the code after repairs.
    echo "   📋 [2/4] Reusing feedback from previous iteration's final check (iter $((iter-1)))..."
    
    # The previous iteration's final check already generated feedback
    # We just need to ensure it exists
    prev_final_fb="$OUTPUT_BASE/iter_$((iter-1))/feedback"
    if [ ! -d "$prev_final_fb" ]; then
      fail "Missing final feedback from iter $((iter-1)): $prev_final_fb"
    fi
    
    # Copy the feedback files to current iteration for the analyze/repair step to use
    echo "   📂 Copying feedback from iter $((iter-1)) final check..."
    cp -a "$prev_final_fb"/feedback_*.txt "$f"/  2>/dev/null || true
    cp -a "$prev_final_fb"/*_codeql.txt "$f"/  2>/dev/null || true
    
    echo "   ✅ Feedback reused successfully (no redundant testing)"


    # --- STEP 3: Collect problematic files from separated feedback files ---
    # Check all three feedback sources to identify files that need repair
    mapfile -t FIX_LIST < <(
      { grep -l . "$f"/feedback_klee_code_*.txt 2>/dev/null; 
        grep -l . "$f"/feedback_compile_code_*.txt 2>/dev/null; 
        grep -l . "$f"/feedback_codeql_code_*.txt 2>/dev/null; } | 
        sed 's/.*feedback_[^_]*_code_//; s/.txt//' | sort -u
    )

    echo "   ℹ️  Found ${#FIX_LIST[@]} problematic files: ${FIX_LIST[*]}"

    if [ ${#FIX_LIST[@]} -eq 0 ]; then
      echo "🟢 No problematic files detected — iteration complete"
    else
      echo "♻️  Fixing ${#FIX_LIST[@]} files: ${FIX_LIST[*]}"
      printf "%s\n" "${FIX_LIST[@]}" > "$g/regenerated_files.list"

      # --- STEP 4a: Analyze (Model B) with FRESH feedback ---
      echo "   🔍 [3/4] Analyzing with Model B (Analyzer): $MODEL_ANALYZER"
      
      export OUTPUT_DIR="$g"
      export FEEDBACK_DIR="$f"  # CRITICAL: Use current iteration's feedback!
      export MODEL="$MODEL_ANALYZER"
      
      python "$PROJECT_DIR/run_llm3.py" --task analyze --only "${FIX_LIST[@]}" \
        || fail "LLM analysis failed (iter $iter)"

      # --- STEP 4b: Repair (Model A) ---
      echo "   🛠️  [4/4] Repairing with Model A (Fixer): $MODEL_FIXER"
      
      export MODEL="$MODEL_FIXER"
      
      python "$PROJECT_DIR/run_llm3.py" --task repair --only "${FIX_LIST[@]}" \
        || fail "LLM repair failed (iter $iter)"
        
    fi
  fi

  # ==========================================================
  # Remaining steps: Re-run full analysis pipeline on repaired code
  # ==========================================================

  # 2) clean (for repaired files)
  echo "🧹 Step 2: Cleaning repaired code..."
  shopt -s nullglob
  for fsrc in "$g"/code_*.c; do
    base=$(basename "$fsrc")
    python "$PROJECT_DIR/clean_code.py" "$fsrc" "$c/$base" \
      || fail "clean_code failed"
  done

  # 3) CodeQL
  echo "🔍 Step 3: CodeQL (final check)..."
  export CC=/scratch/$(whoami)/llvm-14/bin/clang
  export CXX=/scratch/$(whoami)/llvm-14/bin/clang++

  python "$PROJECT_DIR/run_codeql2.py" "$c"
  rm -f "$s/codeql_ok.flag"
  if [ -s "$f/codeql_feedback.txt" ]; then
    if grep -qiE "Issue Rate:\s*0.00%" "$f/codeql_feedback.txt"; then : > "$s/codeql_ok.flag"; fi
  fi
  [ -f "$s/codeql_ok.flag" ] && echo "✅ CodeQL OK" || echo "❌ CodeQL issues detected"


  # 4) compile → bitcode + mocks + nm self-check
  echo "🔧 Step 4: Compile to LLVM bitcode & link mocks..."
  : > "$co/compile_failures.txt"; rm -f "$s/compile_ok.flag"

  if [ -n "$CLANG_BIN" ]; then
    for src in "$c"/code_*.c; do
      bn=$(basename "$src" .c); bc="$b/${bn}.bc"; log="$co/${bn}_compile.log"
      if "$CLANG_BIN" -Wall -Wextra -std=c11 -O1 -emit-llvm -c -g "$src" -o "$bc" 2> "$log"; then
        echo "   ✅ $bn"
        # link with both mocks
        echo "[LLVM-LINK] $bn: $bc  +  $MOCK_SCANF_BC  +  $MOCK_LIBC_BC  →  $bl/${bn}.bc"
        "$LLVM_LINK" -o "$bl/${bn}.bc" "$bc" "$MOCK_SCANF_BC" "$MOCK_LIBC_BC" 2>>"$co/${bn}_compile.log" || {
          echo "$bn failed at link(mock) stage" | tee -a "$co/compile_failures.txt"
          continue
        }
        # nm 自检（直接打印到终端）
        echo "[NM] $bl/${bn}.bc :: scanf symbols"
        "$LLVM_NM" "$bl/${bn}.bc" | egrep " __isoc99_scanf$| scanf$" || true
        # 强制必须有 T __isoc99_scanf / T scanf
        "$LLVM_NM" "$bl/${bn}.bc" | grep -q " T __isoc99_scanf" || { echo "❌ nm check failed: missing T __isoc99_scanf"; exit 1; }
        "$LLVM_NM" "$bl/${bn}.bc" | egrep -q " T scanf$" || { echo "❌ nm check failed: missing T scanf"; exit 1; }
        # 可选提示未解析
        for u in strcpy strlen memcpy memset; do
          "$LLVM_NM" "$bl/${bn}.bc" | grep -q " U $u$" && echo "⚠️  unresolved external after link: $u"
        done
      else
        echo "$bn failed (see $(realpath --relative-to="$d" "$log"))" >> "$co/compile_failures.txt"
        echo "   ❌ $bn"
      fi
    done
    [ ! -s "$co/compile_failures.txt" ] && : > "$s/compile_ok.flag"
  else
    echo "⚠️ clang missing — skip compile"
  fi
  [ -f "$s/compile_ok.flag" ] && echo "✅ Compile+Link OK" || echo "❌ Compile/Link issues present or tool missing"


  # 5) KLEE
  echo "🧠 Step 5: KLEE (naive, scanf mocked)..."
  rm -f "$s/klee_ok.flag"; : > "$k/klee_errors_summary.txt"
  touch "$s/mark_before_klee"

  if [ -n "$KLEE_BIN" ] && ls "$bl"/code_*.bc > /dev/null 2>&1; then
    for bc in "$bl"/code_*.bc; do
      bn=$(basename "$bc" .bc)
      base="${bn%.bc}"
      out="$k/$bn"
      logfile="$k/klee_${bn}.log"

      # Skip if file passed KLEE in previous iteration
      if [ -n "${PASSED_FILES[$base]}" ]; then
        echo "      ⏭️  Skipping final KLEE check for $base (passed in iter $((iter-1)))"
        # Copy previous KLEE output
        prev_klee_out="$OUTPUT_BASE/iter_$((iter-1))/klee_output/$base"
        if [ -d "$prev_klee_out" ]; then
          cp -r "$prev_klee_out" "$k/"
        fi
        continue
      fi

      # 清理旧输出
      if [ -e "$out" ]; then
        echo "     [KLEE] Removing old directory → $out"
        chmod -R u+w "$out" 2>/dev/null || true
        rm -rf "$out"
      fi
      find "$k" -type f \( -name "*.shm" -o -name "*.wal" -o -name "*.db" \) -delete 2>/dev/null

      echo "   ▶ $bn"
      echo "     [KLEE] naive mode (no --posix-runtime, mocks linked)"
      echo "     [KLEE] Output dir → $out"
      echo "     [KLEE] Log file   → $logfile"
      echo "--------------------------------------------------------"

      logtmp=$(mktemp /tmp/klee_${bn}.XXXXXX)

      /usr/bin/timeout --foreground --preserve-status "$TIMEOUT_KLEE" "$KLEE_BIN" \
      "${EXIT_OPTS[@]}" \
      --max-time="${TIMEOUT_KLEE}" \
      --max-solver-time=3s \
      --max-memory=1024 \
      --max-sym-array-size=4096 \
      --max-instructions=200000 \
      --only-output-states-covering-new \
      --output-dir="$out" \
      "$bc" >"$logtmp" 2>&1
      klee_exit=$?

      if [ "$klee_exit" -eq 134 ]; then
        echo "KLEE: ERROR: abort detected (symbolic-sized allocation or invalid IR)" >> "$logtmp"

        mkdir -p "$out"
        echo "[KLEE_RULE] SYMBOLIC_SIZED_ALLOCATION" > "$out/abort.err"
        echo "Cause: allocation size depends on symbolic input." >> "$out/abort.err"
        echo "Required fix:" >> "$out/abort.err"
        echo "- Introduce a compile-time upper bound constant (MAX_N)." >> "$out/abort.err"
        echo "- Replace all symbolic-sized malloc/arrays with MAX_N." >> "$out/abort.err"
        echo "- Add an input range guard before using the size." >> "$out/abort.err"
        echo "- Do NOT invent numeric constants." >> "$out/abort.err"
      fi
      mv "$logtmp" "$logfile"
      echo "--------------------------------------------------------"
      touch "$s/mark_after_klee_${bn}"

      # 统计产物
      if [ -d "$out" ]; then
        errs=$(find "$out" -maxdepth 1 -type f -name "*.err" | wc -l | tr -d ' ')
        tests=$(find "$out" -maxdepth 1 -type f -name "*.ktest" | wc -l | tr -d ' ')
      else
        errs=0; tests=0
      fi

      # 检测 soft/hard crash
      soft_errs=0
      grep -qiE 'HaltTimer|timeout|Execution halting|out of memory' "$logfile" && soft_errs=1
      crashed=0
      if [ "$klee_exit" -ne 0 ] || grep -qiE 'Segmentation fault|dumped core|SIGSEGV' "$logfile"; then
        crashed=1
      fi

      # 打印状态
      if [ "$errs" -gt 0 ]; then
        echo "     [KLEE] Done → Tests=$tests  Errors=$errs"
      elif [ "$crashed" -eq 1 ]; then
        echo "     [KLEE] Done → Tests=$tests  (crash exit=$klee_exit)"
      elif [ "$soft_errs" -eq 1 ]; then
        echo "     [KLEE] Done → Tests=$tests  (soft error: timeout/resource)"
      elif [ "$tests" -eq 0 ]; then
        echo "     [KLEE] Done → Tests=0  (no tests generated)"
      else
        echo "     [KLEE] Done → Tests=$tests  (no actual errors)"
      fi

      # 写入错误汇总
      if [ "$errs" -gt 0 ]; then
        echo "$bn : $errs KLEE error(s)" >> "$k/klee_errors_summary.txt"
      fi
      [ "$crashed" -eq 1 ] && echo "💥 $bn : KLEE crashed (exit=$klee_exit)" >> "$k/klee_errors_summary.txt"
      [ "$soft_errs" -eq 1 ] && echo "⚠️  $bn : KLEE soft error (timeout/resource)" >> "$k/klee_errors_summary.txt"
      [ "$tests" -eq 0 ] && echo "⚠️  $bn : no test generated" >> "$k/klee_errors_summary.txt"

      # 保存 log tail 到独立目录
      if [ -f "$logfile" ]; then
        mkdir -p "$k/logs"
        tail -n 200 "$logfile" > "$k/logs/${bn}.tail.log" || true
      fi
    done

    # ✅ 更稳健的 KLEE OK 判定逻辑
    total_errs=$(find "$k" -maxdepth 2 -type f -name "*.err" | wc -l | tr -d ' ')
    total_tests=$(find "$k" -maxdepth 2 -type f -name "*.ktest" | wc -l | tr -d ' ')
    has_crash_or_soft=0
    grep -qiE '💥|soft error' "$k/klee_errors_summary.txt" && has_crash_or_soft=1

    if [ "$total_errs" -eq 0 ] && [ "$has_crash_or_soft" -eq 0 ] && [ "$total_tests" -gt 0 ]; then
      : > "$s/klee_ok.flag"
    fi
  else
    echo "⚠️  KLEE missing or no linked bitcode — skip"
  fi

  [ -f "$s/klee_ok.flag" ] && echo "✅ KLEE OK (continuing)" || echo "❌ KLEE issues present"
  touch "$s/mark_end_of_klee"



  echo "[DEBUG] summary: reached succ()"
  echo "[DEBUG] summary: f=$f"
  echo "[DEBUG] summary: co=$co"
  echo "[DEBUG] summary: k=$k"

  # 6) summary + reports
  succ=$(ls "$b"/code_*.bc 2>/dev/null | wc -l | tr -d ' ')
  if [ -s "$co/compile_failures.txt" ]; then
    comp_fail=$(wc -l < "$co/compile_failures.txt")
  else
    comp_fail=0
  fi
  echo "[DEBUG] summary: comp_fail=$comp_fail"
  

  # ---- CodeQL issues：只统计 “>0 issues found” 的文件数 ----
  codeql_reports=( "$f"/*_codeql.txt )
  if [ ${#codeql_reports[@]} -gt 0 ] && [ -e "${codeql_reports[0]}" ]; then
      codeql_errs=$(grep -lE "— [1-9][0-9]* issues found" "${codeql_reports[@]}" 2>/dev/null | wc -l)
  else
      codeql_errs=0
  fi

echo "[DEBUG] summary: codeql_errs=$codeql_errs"

  # ---- KLEE errors：统计过滤后的 err（内容中不包含 "mock_"）----
  # 先收集所有 .err
  echo "[DEBUG] summary: before mapfile"
  mapfile -t all_errs < <(find "$k" -maxdepth 2 -type f -name "*.err" 2>/dev/null)
  echo "[DEBUG] summary: after mapfile"
  if [ ${#all_errs[@]} -gt 0 ]; then
    # 过滤掉包含 "mock_" 的 .err
    klee_errs=$(grep -L "mock_" "${all_errs[@]}" 2>/dev/null | wc -l | tr -d ' ')
  else
    klee_errs=0
  fi
  echo "[DEBUG] summary: before writing summary file"
  {
    echo "======================================================"
    echo "📋 Iteration $iter Summary"
    echo "======================================================"
    echo "Bitcode files (raw):         $succ"
    echo "Compilation+Link failures:   $comp_fail"
    echo "Detected CodeQL issues:      $codeql_errs"
    echo "Detected KLEE errors (.err): $klee_errs"
    echo "------------------------------------------------------"
    echo "CodeQL OK:            $([ -f "$s/codeql_ok.flag" ] && echo yes || echo no)"
    echo "Compile+Link OK:      $([ -f "$s/compile_ok.flag" ] && echo yes || echo no)"
    echo "KLEE OK:              $([ -f "$s/klee_ok.flag" ] && echo yes || echo no)"
  } > "$r/summary_iter_${iter}.txt"

  # 同时打印在终端
  cat "$r/summary_iter_${iter}.txt"

  build_feedback_per_file "$d"
  echo "✅ Iteration $iter summary → $r/summary_iter_${iter}.txt"
}

# ==========================================================
# Main loop (only run if not being sourced)
# ==========================================================
if [ -z "$SKIP_MAIN_LOOP" ]; then
  overall_start=$(date +%s); last_good_iter=0
  for i in $(seq 1 "$MAX_ITERS"); do
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
    echo "🏁 Final Evaluation Report"
    echo "======================================================"
    echo "Project : $PROJECT_DIR"
    echo "Base    : $OUTPUT_BASE"
    echo "Iters   : $MAX_ITERS"
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
fi
