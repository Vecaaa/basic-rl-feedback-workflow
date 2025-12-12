#include <stdio.h>
#include <string.h>
#include <stdlib.h>

#define MAX_LEN 101
#define PRIME 101
#define ALPHABET 256

static void rabin_karp(const char *text, const char *pattern) {
    int m = (int)strlen(pattern);
    int n = (int)strlen(text);
    if (m == 0 || n == 0 || m > n) {
        return;
    }

    int h = 1;
    for (int i = 0; i < m - 1; ++i) {
        h = (h * ALPHABET) % PRIME;
    }

    int p_hash = 0;
    int t_hash = 0;
    for (int i = 0; i < m; ++i) {
        p_hash = (ALPHABET * p_hash + pattern[i]) % PRIME;
        t_hash = (ALPHABET * t_hash + text[i]) % PRIME;
    }

    for (int i = 0; i <= n - m; ++i) {
        if (p_hash == t_hash) {
            int j = 0;
            while (j < m && pattern[j] == text[i + j]) {
                ++j;
            }
            if (j == m) {
                printf("Pattern occurs at index %d\n", i);
            }
        }
        if (i < n - m) {
            t_hash = (ALPHABET * (t_hash - text[i] * h) + text[i + m]) % PRIME;
            if (t_hash < 0) {
                t_hash += PRIME;
            }
        }
    }
}

static void trim_newline(char *s) {
    size_t len = strlen(s);
    if (len > 0 && s[len - 1] == '\n') {
        s[len - 1] = '\0';
    }
}

int main(void) {
    char pattern[MAX_LEN];
    char text[MAX_LEN];

    if (!fgets(pattern, sizeof(pattern), stdin)) {
        return 0;
    }
    if (!fgets(text, sizeof(text), stdin)) {
        return 0;
    }

    trim_newline(pattern);
    trim_newline(text);
    rabin_karp(text, pattern);
    return 0;
}
