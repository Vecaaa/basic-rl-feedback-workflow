#include <stdio.h>
#include <stdlib.h>

long long mod_mul(long long a, long long b, long long mod) {
    if (mod <= 0) {
        fprintf(stderr, "mod must be positive\n");
        exit(EXIT_FAILURE);
    }
    a %= mod;
    b %= mod;
    long long result = 0;
    while (b > 0) {
        if (b & 1LL) {
            result = (result + a) % mod;
        }
        a = (a * 2LL) % mod;
        b >>= 1;
    }
    return result;
}

int main(void) {
    long long a = 987654321987654321LL;
    long long b = 123456789123456789LL;
    long long mod = 1000000007LL;
    long long result = mod_mul(a, b, mod);
    printf("%lld\n", result);
    return 0;
}
