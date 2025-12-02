/* klee_mocks/mock_scanf.c
   Safe, conservative scanf mock for KLEE (typed writes, avoid memcpy/strcpy OOB)
*/
#include <stdarg.h>
#include <stddef.h>
#include <string.h>
#include <stdint.h>
#include <klee/klee.h>

/* small helpers */
static int is_flag(char c){ return c=='-'||c=='+'||c==' '||c=='#'||c=='0'; }
static int is_digit(char c){ return c>='0' && c<='9'; }

/* vscanf-like mock: write back through typed pointers rather than memcpy */
static int vscanf_mock(const char *fmt, va_list ap_in) {
    va_list ap;
    va_copy(ap, ap_in);
    int assigned = 0;

    for (const char* p = fmt; *p; ++p) {
        if (*p != '%') continue;
        ++p;
        if (*p == '%') continue; /* literal % */

        /* skip flags, width, precision (we don't fully honor them here) */
        while (is_flag(*p)) ++p;
        while (is_digit(*p)) ++p;
        if (*p == '.') { ++p; while (is_digit(*p)) ++p; }

        /* length modifier */
        enum {LEN_NONE, LEN_H, LEN_HH, LEN_L, LEN_LL, LEN_LCAP} len = LEN_NONE;
        if (*p=='h'){ if (*(p+1)=='h'){ len=LEN_HH; ++p; } else len=LEN_H; }
        else if (*p=='l'){ if (*(p+1)=='l'){ len=LEN_LL; ++p; } else len=LEN_L; }
        else if (*p=='L'){ len=LEN_LCAP; }

        char conv = *p;
        switch (conv) {
            /* integer-like conversions */
            case 'd': case 'i': case 'u': case 'x': case 'o': {
                if (len == LEN_HH) {
                    signed char *dst = va_arg(ap, signed char*);
                    signed char tmp = 0;
                    klee_make_symbolic(&tmp, sizeof(tmp), "scanf_int8");
                    *dst = tmp;
                } else if (len == LEN_H) {
                    short *dst = va_arg(ap, short*);
                    short tmp = 0;
                    klee_make_symbolic(&tmp, sizeof(tmp), "scanf_int16");
                    *dst = tmp;
                } else if (len == LEN_L) {
                    long *dst = va_arg(ap, long*);
                    long tmp = 0;
                    klee_make_symbolic(&tmp, sizeof(tmp), "scanf_long");
                    *dst = tmp;
                } else if (len == LEN_LL) {
                    long long *dst = va_arg(ap, long long*);
                    long long tmp = 0;
                    klee_make_symbolic(&tmp, sizeof(tmp), "scanf_longlong");
                    *dst = tmp;
                } else { /* LEN_NONE */
                    int *dst = va_arg(ap, int*);
                    int tmp = 0;
                    klee_make_symbolic(&tmp, sizeof(tmp), "scanf_int32");
                    *dst = tmp;
                }
                assigned++;
                break;
            }

            /* char */
            case 'c': {
                char *dst = va_arg(ap, char*);
                char tmp = 0;
                klee_make_symbolic(&tmp, sizeof(tmp), "scanf_char");
                /* write single char */
                *dst = tmp;
                assigned++;
                break;
            }

            /* string - conservative: write one char + NUL to avoid OOB */
            case 's': {
                char *dst = va_arg(ap, char*);
                char tmp[16];
                klee_make_symbolic(tmp, sizeof(tmp), "scanf_str");
                tmp[15] = '\0';
                /* safest: write only 1 char + NUL back (avoids unknown small buffers) */
                dst[0] = tmp[0];
                dst[1] = '\0';
                assigned++;
                break;
            }

            /* pointer conversion: scanf "%p" expects void** (address of pointer) */
            case 'p': {
                void **dst = va_arg(ap, void**);
                void *tmp = NULL;
                klee_make_symbolic(&tmp, sizeof(tmp), "scanf_ptr");
                *dst = tmp;
                assigned++;
                break;
            }

            /* floating point (conservative: write a double to pointer) */
            case 'f': case 'g': case 'e': case 'a': {
                if (len == LEN_LCAP) {
                    long double *dst = va_arg(ap, long double*);
                    long double tmp = 0.0L;
                    /* if KLEE doesn't support long double nicely, we fall back to double-sized write */
                    klee_make_symbolic(&tmp, sizeof(tmp), "scanf_longdouble");
                    *dst = tmp;
                } else {
                    double *dst = va_arg(ap, double*);
                    double tmp = 0.0;
                    klee_make_symbolic(&tmp, sizeof(tmp), "scanf_double");
                    *dst = tmp;
                }
                assigned++;
                break;
            }

            default:
                /* unknown conversion: skip */
                break;
        }
    }

    va_end(ap);
    return assigned;
}

/* public wrappers */
int scanf(const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    int r = vscanf_mock(fmt, ap);
    va_end(ap);
    return r;
}

int __isoc99_scanf(const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    int r = vscanf_mock(fmt, ap);
    va_end(ap);
    return r;
}

/* optional: simple getchar symbolic */
int getchar(void) {
    int c = 0;
    klee_make_symbolic(&c, sizeof(c), "getchar");
    return c;
}
