#include <stdio.h>

static int memo1[32];
static int memo2[32];

static void init_memo(int n) {
    for (int i = 0; i <= n; ++i) {
        memo1[i] = -1;
        memo2[i] = -1;
    }
}

static int min_val(int a, int b) {
    return (a < b) ? a : b;
}

static int minTimeRec(int n, int t1, int t2, int *cache_self, int *cache_other) {
    if (n == 0) {
        return 0;
    }
    if (cache_self[n] != -1) {
        return cache_self[n];
    }

    int option1 = t1 + minTimeRec(n - 1, t1, t2, cache_self, cache_other);
    int option2 = t2 + minTimeRec(n - 1, t2, t1, cache_other, cache_self);

    cache_self[n] = min_val(option1, option2);
    return cache_self[n];
}

int minTime(int n, int t1, int t2) {
    init_memo(n);
    return minTimeRec(n, t1, t2, memo1, memo2);
}

int main(void) {
    int n = 5;
    int t1 = 2;
    int t2 = 3;

    int value = minTime(n, t1, t2);
    printf("Minimum time: %d\n", value);
    return 0;
}
