#include <stdio.h>
#include <stdlib.h>

int main() {
    int arr[] = {1, 2, 3, 4, 5};
    int size = sizeof(arr) / sizeof(arr[0]);
    int element = 3;
    int new_size = 0;

    printf("Before insertion: ");
    for (int i = 0; i < size; i++) {
        printf("%d ", arr[i]);
    }
    printf("\n");

    int *result = insert(arr, 10, element, &new_size);
    size = new_size;

    printf("After insertion: ");
    for (int i = 0; i < size; i++) {
        printf("%d ", result[i]);
    }
    printf("\n");

    size_t pos = find_position_to_delete(result, size, element);
    if (pos != -1) {
        int *new_arr = delete (result, size, element, &new_size);
        size = new_size;

        printf("After deletion: ");
        for (int i = 0; i < size; i++) {
            printf("%d ", new_arr[i]);
        }
        printf("\n");

        free(result);
    } else {
        printf("Element not found\n");
    }

    return 0;
}
