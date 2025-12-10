#include <stdio.h>

int MAX_RECURSION = 10; // Adjust this value as needed

int gcd(int a, int b, int recursion_count) {
  if (recursion_count >= MAX_RECURSION) {
    printf("Recursion limit exceeded.\n");
    return -1;
  }
  if (b == 0 || (a == 1 && b == 0))
    return a;
  if (a == 0)
    return b;
  return gcd(b, a % b, recursion_count + 1);
}

int main() {
  int num1, num2;
  printf("Enter two positive integers: ");
  if(scanf("%d %d", &num1, &num2) != 2 || num1 <= 0 || num2 <= 0) {
    printf("Invalid input.\n");
    return 1;
  }
  int result = gcd(num1, num2, 1);
  if(result != -1)
    printf("GCD of %d and %d is %d.\n", num1, num2, result);
  return 0;
}
