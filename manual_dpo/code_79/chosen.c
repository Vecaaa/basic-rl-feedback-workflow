#include <stdio.h>
#include <stdlib.h>

static void guard_index(int idx, int size) {
    if (idx < 0 || idx >= size) {
        fprintf(stderr, "Index %d out of range for size %d\n", idx, size);
        exit(EXIT_FAILURE);
    }
}

int min_chocolates(int n, const int arr[]) {
    if (n <= 0) {
        return 0;
    }

    int *decreasing_sequence = calloc((size_t)n, sizeof(int));
    int *increasing_sequence = calloc((size_t)n, sizeof(int));
    if (!decreasing_sequence || !increasing_sequence) {
        perror("calloc");
        free(decreasing_sequence);
        free(increasing_sequence);
        exit(EXIT_FAILURE);
    }

    decreasing_sequence[0] = arr[0];
    increasing_sequence[0] = arr[n - 1];
    int decreasing_count = 1;
    int increasing_count = 1;

    for (int i = 1; i < n; ++i) {
        guard_index(i, n);
        if (arr[i] > arr[i - 1]) {
            decreasing_sequence[decreasing_count++] = arr[i];
        }

        int left = n - i - 1;
        int right = n - i;
        if (right < n) {
            guard_index(left, n);
            guard_index(right, n);
            if (arr[left] > arr[right]) {
                increasing_sequence[increasing_count++] = arr[left];
            }
        }
    }

    int max = decreasing_sequence[0];
    int sum = 0;
    for (int i = 0; i < decreasing_count; ++i) {
        if (decreasing_sequence[i] > max) {
            max = decreasing_sequence[i];
        }
        sum += decreasing_sequence[i];
    }

    int peak = sum - max;
    int total_sum = (n * (n + 1)) / 2;

    free(decreasing_sequence);
    free(increasing_sequence);

    return total_sum - peak;
}

int main(void) {
    int n;
    if (scanf("%d", &n) != 1 || n < 0 || n > 100) {
        return 1;
    }
    int arr[100];
    for (int i = 0; i < n; ++i) {
        scanf("%d", &arr[i]);
    }
    printf("%d\n", min_chocolates(n, arr));
    return 0;
}
