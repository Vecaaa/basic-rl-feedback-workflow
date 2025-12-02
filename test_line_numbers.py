#!/usr/bin/env python3
"""
Test line number addition and prompt formatting
"""
import sys
sys.path.insert(0, '.')
from run_llm3 import add_line_numbers

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
