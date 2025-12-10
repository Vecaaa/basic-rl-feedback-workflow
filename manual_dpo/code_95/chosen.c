#include <stdio.h>
#include <stdlib.h>

static void printSequencesRecur(int *arr, int pos, int k, int next, int n) {
    if (pos == k) {
        for (int i = 0; i < k; ++i) {
            printf("%d ", arr[i]);
        }
        printf("\n");
        return;
    }
    for (int i = next; i <= n; ++i) {
        arr[pos] = i;
        printSequencesRecur(arr, pos + 1, k, i + 1, n);
    }
}

void printSequences(int n, int k) {
    if (k <= 0 || k > n) {
        printf("Invalid k\n");
        return;
    }
    int *arr = calloc((size_t)k, sizeof(int));
    if (!arr) {
        perror("calloc");
        exit(EXIT_FAILURE);
    }
    printSequencesRecur(arr, 0, k, 1, n);
    free(arr);
}

int main(void) {
    int n = 3;
    int k = 2;
    printSequences(n, k);
    return 0;
}
