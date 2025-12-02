#!/usr/bin/env python3
"""
Test extraction logic with the new prompt structure (markdown blocks)
"""
import re

def extract_c_code_from_text(text: str, fallback: str = "", repair_hint: str = "") -> str:
    """Extract C code from model output with multiple strategies."""
    if not text: 
        return fallback.strip()
    
    # 1) <FIXED_CODE> tags
    m = re.search(r"<FIXED_CODE>(.*?)</FIXED_CODE>", text, re.S | re.I)
    if m and "#include" in m.group(1): 
        return m.group(1).strip()

    # 2) Fenced code blocks (```c ... ```)
    blocks = re.findall(r"```(?:c|C|cpp|C\+\+)?\s*(.*?)```", text, re.S)
    if blocks:
        # Try each block from last to first
        for block in reversed(blocks):
            cand = block.strip()
            if "#include" in cand and "{" in cand:
                return cand

    # 3) Find from first #include to last }
    inc_idx = text.find("#include")
    if inc_idx != -1:
        # Find the last closing brace after the include
        code_section = text[inc_idx:]
        last_brace = code_section.rfind('}')
        if last_brace != -1:
            return code_section[:last_brace + 1].strip()
        return code_section.strip()

    # 4) Look for any function definition
    func_match = re.search(r'(int|void|char|float|double)\s+\w+\s*\([^)]*\)\s*{', text)
    if func_match:
        code_from_func = text[func_match.start():]
        last_brace = code_from_func.rfind('}')
        if last_brace != -1:
            return "#include <stdio.h>\n" + code_from_func[:last_brace + 1].strip()

    return fallback.strip()

print("Testing extraction with new prompt structure...")

# Scenario: Prompt ends with ```c
# Model output starts directly with code, maybe ends with ```
output_1 = """#include <stdio.h>

int main() {
    printf("Hello");
    return 0;
}
```
"""

result_1 = extract_c_code_from_text(output_1, fallback="FAIL")
print(f"Test 1 (Implicit block): {'PASS' if '#include' in result_1 and 'main' in result_1 and '```' not in result_1 else 'FAIL'}")
if '```' in result_1:
    print(f"  -> Failed: Result contains backticks:\n{result_1}")

# Scenario: Partial block (closing fence only)
output_1b = """#include <stdio.h>
int main() { return 0; }
```"""
result_1b = extract_c_code_from_text(output_1b, fallback="FAIL")
print(f"Test 1b (Partial block): {'PASS' if '#include' in result_1b and 'main' in result_1b and '```' not in result_1b else 'FAIL'}")
if '```' in result_1b:
    print(f"  -> Failed: Result contains backticks:\n{result_1b}")

# Scenario: Model repeats the block start (unlikely but possible)
output_2 = """```c
#include <stdio.h>
int main() { return 0; }
```"""
result_2 = extract_c_code_from_text(output_2, fallback="FAIL")
print(f"Test 2 (Explicit block): {'PASS' if '#include' in result_2 and 'main' in result_2 else 'FAIL'}")

# Scenario: Model outputs explanation then code
output_3 = """Here is the fixed code:
```c
#include <stdio.h>
int main() { return 0; }
```"""
result_3 = extract_c_code_from_text(output_3, fallback="FAIL")
print(f"Test 3 (Explanation + block): {'PASS' if '#include' in result_3 and 'main' in result_3 else 'FAIL'}")

print("\nDone.")
