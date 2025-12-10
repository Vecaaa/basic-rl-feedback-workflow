#include <stdio.h>

void printSequencesRecur(int arr[], int start, int end, int k) {
    if (k == 0) {
        for (int i = 0; i < end; i++) {
            printf("%d ", arr[i]);
        }
        printf("\n");
        return;
    }

    for (int i = start; i <= end; i++) {
        if (i <= end - k + 1) {
            if (end - k + 1 >= 0 && end - k + 1 < k) {
                arr[end - k + 1] = i;
            }
            printSequencesRecur(arr, i + 1, end, k - 1);
        }
    }
}

void printSequences(int n, int k) {
    int arr[k];
    printSequencesRecur(arr, 1, n, k);
}

int main() {
    int n = 3, k = 2;
    printSequences(n, k);
    return 0;
}
