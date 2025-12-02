#!/usr/bin/env python3
"""
Test the improved repair prompt to ensure it preserves functionality
"""

# Simulated test case
problem_description = """
Fill two instances of all numbers from 1 to n in a specific way.
A backtracking based C Program to fill two instances of numbers.
"""

current_code = """
#include <stdio.h>
#include <stdlib.h>

int *arr;

int fillUtil(int n, int pos, int *count) {
    if (pos > n) {
        (*count)++;
        return 1;
    }
    
    int i, ans = 0;
    for (i = 1; i <= n && ans == 0; i++) {
        if (arr[i] == 0 && arr[i + pos] == 0) {
            arr[i] = arr[i + pos] = 1;
            ans = fillUtil(n, pos + 1, count);
            if (ans == 1) return 1;
            arr[i] = arr[i + pos] = 0;
        }
    }
    return ans;
}

int main() {
    int n;
    scanf("%d", &n);
    // Missing bounds check here - KLEE error
    arr = (int*)malloc(sizeof(int)*(2*n + 1));
    // ... rest of code
    return 0;
}
"""

repair_instructions = "Add bounds check: if (n <= 0 || n > 100) return 1; before malloc"

# OLD PROMPT (causes functionality change)
old_prompt = f"""// Task: {repair_instructions}

// Original code:
{current_code}

// Fixed code:
<FIXED_CODE>
"""

# NEW PROMPT (preserves functionality)
new_prompt = f"""You are fixing a C program. The program MUST solve this problem:

PROBLEM:
{problem_description}

CURRENT CODE (has errors):
{current_code}

FIX REQUIRED:
{repair_instructions}

IMPORTANT: Keep the same algorithm and logic. Only fix the specific error mentioned above.

FIXED CODE:
```c
"""

print("=" * 70)
print("OLD PROMPT (may change functionality):")
print("=" * 70)
print(old_prompt[:300] + "...")
print()

print("=" * 70)
print("NEW PROMPT (preserves functionality):")
print("=" * 70)
print(new_prompt[:500] + "...")
print()

print("✅ New prompt includes:")
print("  - Original problem description")
print("  - Explicit instruction to preserve algorithm/logic")
print("  - Clear separation of problem, current code, and fix")
