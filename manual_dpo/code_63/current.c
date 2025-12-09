#include<stdio.h>

int equilibriumIndex(int arr[], int n) {
    int sum = 0;
    int leftsum = 0;

    for (int i = 0; i < n; i++) {
        sum += arr[i];
    }

    for (int i = 0; i < n; i++) {
        sum -= arr[i];

        if (leftsum == sum) {
            return i;
        }

        leftsum += arr[i];
    }

    return -1;
}

int main() {
    int arr[] = {1, 2, 3, 4, 5, 6};
    int n = sizeof(arr) / sizeof(arr[0]);

    int equilibriumIndex = equilibriumIndex(arr, n);

    if (equilibriumIndex != -1) {
        printf("Equilibrium index is %d", equilibriumIndex);
    } else {
        printf("No equilibrium index found");
    }

    return 0;
}

