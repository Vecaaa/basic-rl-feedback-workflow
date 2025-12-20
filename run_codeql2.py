#!/usr/bin/env python3
import os, subprocess, json, glob, getpass, sys

user = getpass.getuser()

if len(sys.argv) < 2:
    print("❌ Usage: run_codeql2.py <path_to_cleaned_code>")
    sys.exit(1)

source_dir = os.path.abspath(sys.argv[1])
if not os.path.isdir(source_dir):
    print(f"❌ Not a directory: {source_dir}")
    sys.exit(1)

# =========================================================
# Paths
# =========================================================
feedback_dir = os.path.abspath(os.path.join(source_dir, "../feedback"))
os.makedirs(feedback_dir, exist_ok=True)

db_root = os.path.join(feedback_dir, "codeql_dbs")
os.makedirs(db_root, exist_ok=True)

db_path = os.path.join(db_root, "db_all")
sarif_path = os.path.join(feedback_dir, "all.sarif")

# =========================================================
# CodeQL binary
# =========================================================
codeql_bin = f"/scratch/{user}/codeql/codeql"
if not os.path.isfile(codeql_bin):
    codeql_bin = "codeql"

# =========================================================
# Query Suite
# =========================================================
ql_spec = "codeql/cpp-queries:codeql-suites/cpp-security-and-quality.qls"

# =========================================================
# Compiler
# =========================================================
CC = os.environ.get("CC", f"/scratch/{user}/llvm-14/bin/clang")

print(f"🔍 Using CodeQL: {codeql_bin}")
print(f"📦 Using queries: {ql_spec}")
print(f"🛠  Compiler: {CC}")

# =========================================================
# Collect C files
# =========================================================
code_files = sorted(glob.glob(os.path.join(source_dir, "code_*.c")))
if not code_files:
    print("❌ No code_*.c files found.")
    sys.exit(1)

file_basenames = [os.path.basename(x) for x in code_files]

print(f"✅ Found {len(file_basenames)} source files.")

# =========================================================
# Step 1: Build unified CodeQL Database
# =========================================================
print("\n📦 Creating unified CodeQL database...")

# Clean old DB
if os.path.exists(db_path):
    subprocess.run(["rm", "-rf", db_path])

# Generate per-file compile command
compile_cmds = []
for fn in file_basenames:
    # tolerent: compile error does not break CodeQL
    compile_cmds.append(
        f"echo 'Compiling {fn}' ; "
        f"{CC} -std=c11 -Wall -Wextra -c {fn} -o {fn}.o > /dev/null 2>&1 || true"
    )

bash_script = " ; ".join(compile_cmds)

# Single unified DB creation
create_cmd = [
    codeql_bin, "database", "create", db_path,
    "--language=c",
    f"--source-root={source_dir}",
    "--overwrite",
    "--command", f"bash -c \"{bash_script}\""
]

res = subprocess.run(create_cmd, capture_output=True, text=True, cwd=source_dir)
if res.returncode != 0:
    print("❌ Failed to create CodeQL DB")
    print(res.stderr or res.stdout)
    with open(os.path.join(feedback_dir, "codeql_db_failed.txt"), "w") as f:
        f.write(res.stderr or res.stdout)
    sys.exit(1)

print("✅ Unified CodeQL DB created successfully.")

# =========================================================
# Step 2: Analyze Database with Full Security Suite
# =========================================================
print("\n🧠 Running CodeQL analysis on unified database...")

analyze_cmd = [
    codeql_bin, "database", "analyze", db_path, ql_spec,
    "--format=sarif-latest",
    f"--output={sarif_path}",
    "--threads=18"
]

res = subprocess.run(analyze_cmd, capture_output=True, text=True)
if res.returncode != 0:
    print("❌ CodeQL analysis failed")
    print(res.stderr or res.stdout)
    sys.exit(1)

print(f"✅ Analysis completed. SARIF saved at {sarif_path}")

# =========================================================
# Step 3: Parse SARIF into per-file reports
# =========================================================
print("\n📄 Parsing SARIF...")

total_issues = 0
files_with_issues = 0
issues_by_file = {fn: [] for fn in file_basenames}

def get_basename(uri: str):
    import os
    return os.path.basename(uri)

try:
    with open(sarif_path, "r") as f:
        sarif = json.load(f)

    for run in sarif.get("runs", []):
        for r in run.get("results", []):
            msg = r.get("message", {}).get("text", "No description")
            rule = r.get("ruleId", "unknown-rule")

            loc = r.get("locations", [])
            basename = "?unknown?"
            line = "?"

            if loc:
                ploc = loc[0].get("physicalLocation", {})
                region = ploc.get("region", {})
                line = region.get("startLine", "?")

                art = ploc.get("artifactLocation", {})
                uri = art.get("uri", "")
                basename = get_basename(uri) if uri else "?unknown?"

            total_issues += 1
            if basename in issues_by_file:
                issues_by_file[basename].append(f"🔹 Line {line}: [{rule}] {msg}")

except Exception as e:
    print(f"⚠️ SARIF parse failed: {e}")

# Write per-file reports
for fn in file_basenames:
    issues = issues_by_file.get(fn, [])
    rp = os.path.join(feedback_dir, f"{fn.replace('.c','')}_codeql.txt")

    with open(rp, "w") as f:
        f.write(f"[{fn}] — {len(issues)} issues found\n")
        if issues:
            files_with_issues += 1
            f.write("\n".join(issues))

# =========================================================
# Step 4: Summary
# =========================================================
summary_path = os.path.join(feedback_dir, "codeql_feedback.txt")
with open(summary_path, "w") as f:
    f.write("CodeQL Unified Security Analysis Report\n")
    f.write("==============================================\n")
    f.write(f"Total files analyzed: {len(file_basenames)}\n")
    f.write(f"Files with issues: {files_with_issues}\n")
    f.write(f"Total issues: {total_issues}\n")
    rate = files_with_issues / len(file_basenames) * 100 if file_basenames else 0
    f.write(f"Issue Rate: {rate:.2f}%\n")
    f.write("==============================================\n")

print(f"\n✅ Summary saved to {summary_path}")
print("🎉 Unified CodeQL analysis completed.")
