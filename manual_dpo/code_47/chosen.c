#include <stdio.h>

void merge(int m, int n, const int first[], const int second[], int out[]) {
    int i = 0;
    int j = 0;
    int k = 0;

    while (i < m && j < n) {
        if (first[i] <= second[j]) {
            out[k++] = first[i++];
        } else {
            out[k++] = second[j++];
        }
    }

    while (i < m) {
        out[k++] = first[i++];
    }

    while (j < n) {
        out[k++] = second[j++];
    }
}

void printArray(const int *arr, int len) {
    for (int i = 0; i < len; ++i) {
        printf("%d ", arr[i]);
    }
    printf("\n");
}

int main(void) {
    int first[] = {1, 3, 5, 7, 9};
    int second[] = {2, 4, 6};
    const int m = sizeof(first) / sizeof(first[0]);
    const int n = sizeof(second) / sizeof(second[0]);
    int merged[m + n];

    merge(m, n, first, second, merged);

    printf("Merged array: ");
    printArray(merged, m + n);
    return 0;
}
