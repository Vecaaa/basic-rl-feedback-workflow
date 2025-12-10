#include <stdio.h>

void merge(int m, int n, int N[], int mPlusN[]) {
    int i, j, k;
    i = j = k = 0;
    
    while (i < m && j < n) {
        if (N[i] < mPlusN[k]) {
            mPlusN[k++] = N[i++];
        } else {
            mPlusN[k++] = N[j++];
        }
    }
    
    while (i < m) {
        mPlusN[k++] = N[i++];
    }
    
    while (j < n) {
        mPlusN[k++] = N[j++];
    }
}

void printArray(int arr[], int n) {
    int i;
    for (i = 0; i < n; i++) {
        printf("%d ", arr[i]);
    }
    printf("\n");
}

int main() {
    int m = 5, n = 3, i;
    int N[] = {1, 2, 3};
    int mPlusN[m + n];
    
    for (i = 0; i < m + n; i++) {
        mPlusN[i] = -1;
    }
    
    merge(m, n, N, mPlusN);
    
    printf("Merged array: ");
    printArray(mPlusN, m + n);
    
    return 0;
}
