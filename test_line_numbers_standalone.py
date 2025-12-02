#!/usr/bin/env python3
"""
Standalone test for line number addition logic
"""

def add_line_numbers(code: str) -> str:
    """Add line numbers to code for better LLM reference."""
    lines = code.splitlines()
    return "\n".join([f"{i+1:3}: {line}" for i, line in enumerate(lines)])

def test_add_line_numbers():
    code = """#include <stdio.h>
int main() {
    printf("Hello");
    return 0;
}"""
    
    expected = """  1: #include <stdio.h>
  2: int main() {
  3:     printf("Hello");
  4:     return 0;
  5: }"""
    
    result = add_line_numbers(code)
    print("Code:")
    print(code)
    print("\nResult:")
    print(result)
    
    assert result == expected, f"Expected:\n{expected}\nGot:\n{result}"
    print("\n✅ add_line_numbers test passed!")

if __name__ == "__main__":
    test_add_line_numbers()
