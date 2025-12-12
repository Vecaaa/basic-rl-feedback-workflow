#include <stdio.h>
#include <string.h>
#include <stdlib.h>

#define pattern_size 101
#define text_size 101
#define Q 101
#define d 256

long long h[Q], p[Q], t[Q];

void RabinKarp(char *txt, char *pat, int q)
{
    int M = strlen(pat);
    int N = strlen(txt);
    h[0] = 1;
    for (int i = 1; i < q; i++)
        h[i] = (h[i - 1] * d) % q;
    t[N - 1] = (txt[N - 1] - 'a' + 1) % q;
    for (int i = N - 2; i >= 0; i--)
        t[i] = ((d * t[i + 1]) - (txt[i] * h[M - 1]) + q) % q;
    for (int i = 0; i <= N - M; i++)
    {
        if (t[i] == 1)
        {
            int j;
            for (j = 0; j < M; j++)
                if (pat[j] != txt[i + j])
                    break;
            if (j == M)
                printf("Pattern occurs at index %d\n", i);
        }
        if (i < N - M)
        {
            t[i + M] = (((d * t[i + M]) - ((txt[i] * h[M]) + q) + txt[i + M]) % q + q) % q;
        }
    }
}

int main()
{
    char pattern[pattern_size], text[text_size];
    fgets(pattern, pattern_size, stdin);
    fgets(text, text_size, stdin);
    int prime = 101;
    if (strlen(pattern) < prime) { fgets(pattern, pattern_size, stdin); }
    if (strlen(text) < prime) { fgets(text, text_size, stdin); }
    if (prime < 2 || prime % 2 == 0) { prime = 3; }
    if (d < prime) { 
        #define d 256; 
    }
    if (prime < Q) { 
        #define Q prime; 
    }
    if (strlen(text) >= prime && strlen(pattern) >= prime) { RabinKarp(text, pattern, prime); }
    return 0;
}

2. The line 45 should be replaced with a loop that reads the input up to the size of the largest string.
   - Replace line 45 with:

int i;
for (i = 0; i < pattern_size; i++)
{
    fgets(pattern + i, pattern_size - i, stdin);
    if (strlen(pattern[i]) >= pattern_size)
    {
        break;
    }
}
for (i = 0; i < text_size; i++)
{
    fgets(text + i, text_size - i, stdin);
    if (strlen(text[i]) >= text_size)
    {
        break;
    }
}

3. The line 54 should be replaced with a loop that reads the input up to the size of the largest string.
   - Replace line 54 with:

int i;
for (i = 0; i < text_size; i++)
{
    fgets(text + i, text_size - i, stdin);
    if (strlen(text[i]) >= text_size)
    {
        break;
    }
}
