#include <stdio.h>

// Function to implement search operation
int search(int arr[], int n, int x) {
    for(int i = 0; i < n; i++) {
        if(arr[i] == x) {
            return i;
        }
    }
    return -1;
}

// Function to implement insert operation
void insert(int arr[], int n, int x, int pos) {
    for(int i = n-1; i >= pos; i--) {
        arr[i+1] = arr[i];
    }
    arr[pos] = x;
    n++;
}

// Function to implement delete operation
void delete(int arr[], int n, int pos) {
    for(int i = pos; i < n-1; i++) {
        arr[i] = arr[i+1];
    }
    n--;
}

// Driver Code
int main() {
    int arr[] = {1, 2, 3, 4, 5};
    int n = sizeof(arr)/sizeof(arr[0]);
    int x = 3;
    int pos = 2;

    int result = search(arr, n, x);
    if(result != -1) {
        printf("Element found at position %d\n", result);
    } else {
        printf("Element not found\n");
    }

    insert(arr, n, x, pos);
    n++;

    delete(arr, n, pos);
    n--;

    return 0;
}
