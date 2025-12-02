#!/usr/bin/env python3
"""
Test script for code extraction improvements
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

# Test cases
print("Testing code extraction...")

# Test 1: Code with proper tags
test1 = """<FIXED_CODE>
#include <stdio.h>
int main() { return 0; }
</FIXED_CODE>"""
result1 = extract_c_code_from_text(test1, fallback='fallback')
assert '#include' in result1 and 'main' in result1, "Test 1 failed"
print("✓ Test 1: Code with tags")

# Test 2: Code without tags but with #include
test2 = """Some text
#include <stdio.h>
int main() { 
    printf("hello");
    return 0; 
}
More text"""
result2 = extract_c_code_from_text(test2, fallback='fallback')
assert '#include' in result2 and 'main' in result2, "Test 2 failed"
print("✓ Test 2: Code without tags")

# Test 3: Empty output should use fallback
test3 = ""
result3 = extract_c_code_from_text(test3, fallback='fallback_code')
assert result3 == 'fallback_code', "Test 3 failed"
print("✓ Test 3: Empty/fallback")

# Test 4: Code in markdown block
test4 = """```c
#include <stdio.h>
int main() { 
    return 0; 
}
```"""
result4 = extract_c_code_from_text(test4, fallback='fallback')
assert '#include' in result4 and 'main' in result4, "Test 4 failed"
print("✓ Test 4: Markdown code block")

print("\n✅ All tests passed!")
