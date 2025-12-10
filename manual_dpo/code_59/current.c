#include <stdio.h>

// Function to implement search operation
int search(int arr[], int n, int x) {
    for (int i = 0; i < n; i++) {
        if (arr[i] == x) {
            return i;
        }
    }
    return -1;
}

// Function to insert an element
void insert(int arr[], int n, int x, int pos) {
    for (int i = n-1; i >= pos; i--) {
        arr[i+1] = arr[i];
    }
    arr[pos] = x;
    n++;
}

// Function to delete an element
void delete (int arr[], int n, int x) {
    int pos = search(arr, n, x);
    if (pos == -1) {
        printf("Element not found");
    } else {
        for (int i = pos; i < n-1; i++) {
            arr[i] = arr[i+1];
        }
        n--;
    }
}

// Driver code
int main() {
    int arr[] = {1, 2, 3, 4, 5};
    int n = sizeof(arr)/sizeof(arr[0]);
    int x = 3;
    int pos = 2;

    printf("Search result: %d\n", search(arr, n, x));
    insert(arr, n, x, pos);
    n++;
    printf("After insertion: ");
    for (int i = 0; i < n; i++) {
        printf("%d ", arr[i]);
    }
    printf("\n");
    delete(arr, n, pos);
    printf("After deletion: ");
    for (int i = 0; i < n; i++) {
        printf("%d ", arr[i]);
    }
    printf("\n");

    return 0;
}
