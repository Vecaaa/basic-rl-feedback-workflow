#include <stdio.h>

#define MAX_N 1000

static void print_solution(const int *arr, int n) {
    for (int i = 0; i < n; ++i) {
        printf("%d ", arr[i]);
    }
    printf("\n");
}

static void fillUtil(int *arr, int n, int pos, int *count) {
    if (*count > 1) {
        return;
    }
    if (pos == n) {
        if (*count == 1) {
            print_solution(arr, n);
        }
        (*count)++;
        return;
    }

    for (int i = 0; i < n; ++i) {
        if (arr[i] == 0) {
            arr[i] = 1;
            fillUtil(arr, n, pos + 1, count);
            arr[i] = 0;
        }
    }
}

void fill(int n) {
    int arr[MAX_N] = {0};
    int count = 0;
    fillUtil(arr, n, 0, &count);
}

int main(void) {
    int n;
    if (scanf("%d", &n) != 1) {
        return 1;
    }
    if (n <= 0 || n > MAX_N) {
        printf("Error: n is too large\n");
        return 1;
    }
    fill(n);
    return 0;
}
