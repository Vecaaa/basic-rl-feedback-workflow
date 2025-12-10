#include <stdio.h>
#include <ctype.h>
#include <limits.h>

int my_atoi(const char *str) {
    long long result = 0;
    int sign = 1;

    while (isspace((unsigned char)*str)) {
        ++str;
    }

    if (*str == '+' || *str == '-') {
        if (*str == '-') {
            sign = -1;
        }
        ++str;
    }

    while (isdigit((unsigned char)*str)) {
        result = result * 10 + (*str - '0');
        if (result * sign > INT_MAX) {
            return INT_MAX;
        }
        if (result * sign < INT_MIN) {
            return INT_MIN;
        }
        ++str;
    }

    return (int)(result * sign);
}

int main(void) {
    char str[] = "   -123456";
    printf("%d\n", my_atoi(str));
    return 0;
}
