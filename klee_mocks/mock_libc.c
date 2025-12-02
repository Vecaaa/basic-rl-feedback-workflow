/* minimal libc replacements used for linking with KLEE (no external headers) */
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <klee/klee.h>

/* Simple, portable implementations (kept minimal and safe) */

size_t strlen(const char *s) {
    if (!s) return 0;
    size_t i = 0;
    while (s[i]) ++i;
    return i;
}

char *strcpy(char *dst, const char *src) {
    size_t i = 0;
    if (!dst) return dst;
    if (!src) { dst[0] = '\0'; return dst; }
    while ((dst[i] = src[i]) != '\0') ++i;
    return dst;
}

void *memcpy(void *dst, const void *src, size_t n) {
    if (!dst || !src) return dst;
    unsigned char *d = (unsigned char*)dst;
    const unsigned char *s = (const unsigned char*)src;
    for (size_t i = 0; i < n; ++i) d[i] = s[i];
    return dst;
}

void *memset(void *s, int c, size_t n) {
    if (!s) return s;
    unsigned char *p = (unsigned char*)s;
    for (size_t i = 0; i < n; ++i) p[i] = (unsigned char)c;
    return s;
}

/* Minimal printf stub: we don't format, just return a small positive count.
   (Used only to satisfy linkage and avoid large runtime dependency.) */
int printf(const char *fmt, ...) {
    (void)fmt;
    return 0;
}

/* abort/_Exit: ensure they don't return (use _Exit if available) */
void _Exit(int status) {
    (void)status;
    klee_silent_exit(status);
}

void abort(void) {
    klee_silent_exit(1);
}
