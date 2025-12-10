#include <stdio.h>
#include <stdlib.h>

#define MAX_N 1000

int* createArray(int n) {
    if(n > MAX_N) {
        printf("Error: n is too large\n");
        exit(1);
    }

    int* arr = (int*)malloc(n * sizeof(int));
    for(int i = 0; i < n; i++) {
        arr[i] = 0;
    }
    return arr;
}

void fillUtil(int* arr, int n, int pos, int* count) {
    if(*count > 1) {
        return;
    }
    if(pos == n) {
        if(*count == 1) {
            for(int i = 0; i < n; i++) {
                printf("%d ", arr[i]);
            }
            printf("\n");
        }
        (*count)++;
        return;
    }
    for(int i = 1; i <= n; i++) {
        if(arr[i] == 0) {
            arr[i] = 1;
            fillUtil(arr, n, pos + 1, count);
            arr[i] = 0;
        }
    }
}

void fill(int n) {
    int* arr = createArray(n);
    int count = 0;
    fillUtil(arr, MAX_N, 0, &count);
    free(arr);
}

int main() {
    int n;
    scanf("%d", &n);
    if(n > MAX_N) {
        printf("Error: n is too large\n");
        return 1;
    }
    fill(n);
    return 0;
}
