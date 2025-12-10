#include <stdio.h>

int min_chocolates(int n, int arr[n]) {
    int i, j, k, l, m, sum, max, peak, total_sum;
    int decreasing_count = 0;
    int *decreasing_sequence;
    int increasing_count = 0;
    int *increasing_sequence;

    decreasing_sequence = (int *)calloc(n, sizeof(int));
    if(decreasing_sequence == NULL) {
        printf("Memory allocation failed\n");
        exit(0);
    }

    increasing_sequence = (int *)calloc(n, sizeof(int));
    if(increasing_sequence == NULL) {
        printf("Memory allocation failed\n");
        exit(0);
    }

    decreasing_sequence[0] = arr[0];
    decreasing_count = 1;
    increasing_sequence[0] = arr[n-1];
    increasing_count = 1;

    for(i = 1; i < n; i++) {
        if(arr[i] > arr[i-1]) {
            if(decreasing_count < n) {
                decreasing_sequence[decreasing_count] = arr[i];
                decreasing_count++;
            } else {
                printf("Array access out of bounds\n");
                exit(0);
            }
        }
        if(arr[n-i-1] > arr[n-i]) {
            if(increasing_count < n) {
                increasing_sequence[increasing_count] = arr[n-i-1];
                increasing_count++;
            } else {
                printf("Array access out of bounds\n");
                exit(0);
            }
        }
    }

    max = decreasing_sequence[0];
    for(i = 1; i < decreasing_count; i++) {
        if(decreasing_sequence[i] > max) {
            max = decreasing_sequence[i];
        }
    }

    sum = 0;
    for(i = 0; i < decreasing_count; i++) {
        sum += decreasing_sequence[i];
    }

    peak = sum - max;

    total_sum = (n * (n + 1)) / 2;

    return total_sum - peak;
}

int main() {
    int n, arr[100], i;

    scanf("%d", &n);

    if (n > 0) {
        for(i = 0; i < n; i++) {
            scanf("%d", &arr[i]);
        }
    }

    printf("%d\n", min_chocolates(n, arr));

    return 0;
}
