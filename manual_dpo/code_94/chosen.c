#include <stdio.h>

int gcd(int a, int b) {
    while (b != 0) {
        int tmp = b;
        b = a % b;
        a = tmp;
    }
    return a;
}

int main(void) {
    int num1, num2;
    if (scanf("%d %d", &num1, &num2) != 2 || num1 <= 0 || num2 <= 0) {
        printf("Invalid input.\n");
        return 1;
    }
    printf("GCD of %d and %d is %d.\n", num1, num2, gcd(num1, num2));
    return 0;
}
