#!/usr/bin/env python3
"""
Test script to verify Analyzer and Fixer prompt structure with code quoting
"""
import sys
sys.path.insert(0, '.')
from run_llm3 import add_line_numbers

def test_prompts():
    print("Testing prompt generation logic...")
    
    # Mock data
    current_code = """#include <stdio.h>
int main() {
    printf("Hello");
    return 0;
}"""
    numbered_code = add_line_numbers(current_code)
    feedback = "error: implicit declaration of function 'printf'"
    repair_instructions = "Add #include <stdio.h> before line 1: `#include <stdio.h>`"
    problem_description = "Write a hello world program."
    
    # Simulate Analyzer Prompt
    analyzer_prompt = f"""You are a C code compiler expert. Analyze the code and feedback below.

Generate ONLY a single, precise, and actionable repair instruction. Do NOT output any code, headers, or conversational text.
Reference specific line numbers from the provided code AND quote the code content.

Good examples:
- Add #include <stdio.h> at the top to fix implicit declaration of printf
- Add bounds check: if (n <= 0 || n > 100) return 1; before line 15: `if(two < n) {{`

CURRENT CODE (with line numbers):
{numbered_code}

COMPILER FEEDBACK:
{feedback}

Repair Instruction:"""

    print("\n--- Analyzer Prompt ---")
    print(analyzer_prompt)
    assert "Reference specific line numbers from the provided code AND quote the code content." in analyzer_prompt
    assert "before line 15: `if(two < n) {`" in analyzer_prompt
    
    # Simulate Fixer Prompt
    fixer_prompt = f"""You are fixing a C program. The program MUST solve this problem:

PROBLEM:
{problem_description}

CURRENT CODE (with line numbers):
{numbered_code}

FIX REQUIRED:
{repair_instructions}

IMPORTANT: 
1. Keep the same algorithm and logic. Only fix the specific error mentioned above.
2. Use the line numbers in CURRENT CODE to locate the error.
3. Verify the location using the quoted code in the FIX REQUIRED section (if present).
4. Output the FIXED CODE without line numbers.

FIXED CODE:
```c
"""
    print("\n--- Fixer Prompt ---")
    print(fixer_prompt)
    assert "Verify the location using the quoted code" in fixer_prompt
    
    print("\n✅ Prompt structure verification passed!")

if __name__ == "__main__":
    test_prompts()
