#!/usr/bin/env python3
import sys
import re

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
# 2. Remove common LLM response patterns / explanations
# ============================================================
# Remove "You are an AI..." preambles
text = re.sub(r'You are an (AI|expert)[^\n]*\n', '', text, flags=re.IGNORECASE)

# Remove instruction markers
text = re.sub(r'(Instruction|Task|Problem|Question):\s*', '', text, flags=re.IGNORECASE)

# Remove "Here is", "Here's", "The code is" type phrases
text = re.sub(r'(Here is|Here\'s|The code is|Below is)[^\n]*:\s*', '', text, flags=re.IGNORECASE)

# Remove obvious English explanation paragraphs that often wrap code
explanation_patterns = [
    r'The above code[\s\S]*?(?=#include|int\s+main\b|struct\s+\w+\s*{)',
    r'Please note[\s\S]*?(?=#include|int\s+main\b|struct\s+\w+\s*{)',
    r'Now,\s*write the code[\s\S]*?(?=#include|int\s+main\b|struct\s+\w+\s*{)',
    r'If you are not familiar with[\s\S]*?(?=#include|int\s+main\b|struct\s+\w+\s*{)',
]
for pat in explanation_patterns:
    text = re.sub(pat, '', text, flags=re.IGNORECASE)

# Remove XML-style tags / meta blocks
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

# Remove obvious helper markers
text = re.sub(r'\[\[HELPER\]\]', '', text, flags=re.IGNORECASE)

# Trim at explicit LLM markup tokens like END_CODE / SOLUTION, keeping only the first program
for marker in ["END_CODE", "SOLUTION"]:
    idx = text.upper().find(marker)
    if idx != -1:
        text = text[:idx]
        break

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
    # Keep from the first true #include onwards
    text = text[inc_match.start():]

    # Heuristic: if there is a SECOND #include after we've already seen
    # some non-include code, treat everything from that point on as a
    # duplicated program and drop it. This matches typical LLM patterns:
    #   code + explanation + [[SOLUTION]] + repeated full program.
    lines = text.splitlines()
    i = 0
    # Skip the initial include block at the very top
    while i < len(lines) and lines[i].lstrip().startswith("#include"):
        i += 1
    # Search for a later include that likely starts a duplicated TU
    for j in range(i + 1, len(lines)):
        if lines[j].lstrip().startswith("#include"):
            lines = lines[:j]
            break
    text = "\n".join(lines)

# Find last closing brace
last_brace = text.rfind('}')
if last_brace != -1:
    text = text[:last_brace + 1]
else:
    # No closing brace found - this is problematic; append minimal main
    text = text.strip() + "\n\nint main(void){return 0;}\n"

# Final trim: strip leading/trailing blank lines
text = text.strip() + "\n"

open(dst, "w", encoding="utf-8").write(text)
