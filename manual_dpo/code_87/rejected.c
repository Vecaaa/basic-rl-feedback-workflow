#include <stdio.h>

int main() {
    int n;
    float x, sum = 0.0;

    printf("Enter the value of n: ");
    if(scanf("%d", &n) != 1) {
        printf("Invalid input for n\n");
        return 1;
    }

    printf("Enter the value of x: ");
    if(scanf("%f", &x) != 1) {
        printf("Invalid input for x\n");
        return 1;
    }

    for(int i = 1; i <= n; i++) {
        sum += (float)i / (float)i;
    }

    printf("Sum of the series is: %f", sum);

    return 0;
}
