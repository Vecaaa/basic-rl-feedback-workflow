#!/usr/bin/env python3
import sys, re

src = sys.argv[1]
dst = sys.argv[2]

# Read raw LLM output
text = open(src, encoding="utf-8", errors="ignore").read()
original_length = len(text)

# ============================================================
# 1. Remove markdown code fences first
# ============================================================
# Remove ```c, ```C, ```cpp, etc. and closing ```
text = re.sub(r'```[a-zA-Z0-9]*\n?', '', text)
text = text.replace("```", "")

# ============================================================
# 2. Remove common LLM response patterns
# ============================================================
# Remove "You are an AI..." preambles
text = re.sub(r'You are an (AI|expert)[^\n]*\n', '', text, flags=re.IGNORECASE)

# Remove instruction markers
text = re.sub(r'(Instruction|Task|Problem|Question):\s*', '', text, flags=re.IGNORECASE)

# Remove "Here is", "Here's", "The code is" type phrases
text = re.sub(r'(Here is|Here\'s|The code is|Below is)[^\n]*:\s*', '', text, flags=re.IGNORECASE)

# Remove XML-style tags
block_patterns = [
    r'<ORIGINAL_PROMPT>[\s\S]*?</ORIGINAL_PROMPT>',
    r'<CURRENT_CODE>[\s\S]*?</CURRENT_CODE>',
    r'<STRUCTURED_FEEDBACK>[\s\S]*?</STRUCTURED_FEEDBACK>',
    r'<PROBLEM>[\s\S]*?</PROBLEM>',
    r'<FIXED_CODE>[\s\S]*?</FIXED_CODE>',
    r'\[\[ORIGINAL_PROBLEM\]\][\s\S]*?\[\[CURRENT_CODE\]\]',
    r'\[\[CURRENT_CODE\]\][\s\S]*?\[\[STRUCTURED_FEEDBACK\]\]',
    r'\[\[STRUCTURED_FEEDBACK\]\][\s\S]*?\[\[REPAIR_INSTRUCTIONS\]\]',
]
for pat in block_patterns:
    text = re.sub(pat, '', text, flags=re.IGNORECASE)

# Remove "now start to write" type phrases
text = re.sub(r'now start to write[^\n]*\n', '', text, flags=re.IGNORECASE)
text = re.sub(r'write code ONLY[^\n]*\n', '', text, flags=re.IGNORECASE)

# Remove non-ASCII characters
text = re.sub(r'[^\x00-\x7F]+', ' ', text)

# ============================================================
# 3. Extract C code - find first #include to last }
# ============================================================
# Find first #include
inc_match = re.search(r'#include\s*[<"][^>"]+[>"]', text)
if not inc_match:
    # No include found - try to find any function definition
    func_match = re.search(r'(int|void|char|float|double)\s+\w+\s*\([^)]*\)\s*{', text)
    if func_match:
        text = text[func_match.start():]
        # Prepend a basic include
        text = "#include <stdio.h>\n" + text
    else:
        # Complete failure - create stub
        print(f"WARNING: No C code found in {src}, creating stub", file=sys.stderr)
        open(dst, "w").write("#include <stdio.h>\nint main(void){return 0;}\n")
        sys.exit(0)
else:
    text = text[inc_match.start():]

# Find last closing brace
last_brace = text.rfind('}')
if last_brace != -1:
    text = text[:last_brace + 1]
else:
    # No closing brace found - this is problematic
    print(f"WARNING: No closing brace found in {src}", file=sys.stderr)

# ============================================================
# 4. Clean up the extracted code
# ============================================================
# Remove any remaining explanatory text after the code
# (lines that don't look like C code)
lines = text.split('\n')
cleaned_lines = []
in_code = False
for line in lines:
    stripped = line.strip()
    
    # Start of code
    if stripped.startswith('#include') or stripped.startswith('//') or stripped.startswith('/*'):
        in_code = True
    
    # Skip lines that look like explanations (only if we haven't started code yet)
    if not in_code and stripped and not any(c in stripped for c in ['#', '{', '}', '(', ')', ';']):
        continue
    
    cleaned_lines.append(line)

text = '\n'.join(cleaned_lines).strip() + '\n'

# ============================================================
# 5. Final validation and fallback
# ============================================================
if "int main" not in text and "void main" not in text:
    print(f"WARNING: No main function found in {src}, adding stub main", file=sys.stderr)
    text += "\nint main(void){return 0;}\n"

# Ensure at least one include
if "#include" not in text:
    text = "#include <stdio.h>\n" + text

# Write result
open(dst, "w").write(text)

# Log statistics
final_length = len(text)
print(f"Cleaned {src}: {original_length} -> {final_length} bytes", file=sys.stderr)
