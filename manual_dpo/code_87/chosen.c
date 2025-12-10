#include <stdio.h>

double compute_series(int n, double x) {
    double sum = 0.0;
    for (int i = 1; i <= n; ++i) {
        sum += (double)i / (x + i);
    }
    return sum;
}

int main(void) {
    int n;
    double x;

    if (scanf("%d", &n) != 1 || n <= 0) {
        return 1;
    }
    if (scanf("%lf", &x) != 1) {
        return 1;
    }

    double sum = compute_series(n, x);
    printf("Sum of the series is: %.6f\n", sum);
    return 0;
}
