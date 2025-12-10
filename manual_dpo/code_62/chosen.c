#include <stdio.h>
#include <stdlib.h>
#include <stddef.h>

static void print_array(const int *arr, int size) {
    for (int i = 0; i < size; ++i) {
        printf("%d ", arr[i]);
    }
    printf("\n");
}

int *insert(const int *arr, int size, int element, int *out_size) {
    int *result = malloc((size + 1) * sizeof(int));
    if (!result) {
        perror("malloc");
        exit(EXIT_FAILURE);
    }
    int pos = size;
    for (int i = 0; i < size; ++i) {
        if (arr[i] > element) {
            pos = i;
            break;
        }
    }
    for (int i = 0; i < pos; ++i) {
        result[i] = arr[i];
    }
    result[pos] = element;
    for (int i = pos; i < size; ++i) {
        result[i + 1] = arr[i];
    }
    *out_size = size + 1;
    return result;
}

size_t find_position_to_delete(const int *arr, int size, int element) {
    for (int i = 0; i < size; ++i) {
        if (arr[i] == element) {
            return (size_t)i;
        }
    }
    return (size_t)-1;
}

int *delete_element(const int *arr, int size, int element, int *out_size) {
    size_t pos = find_position_to_delete(arr, size, element);
    if (pos == (size_t)-1) {
        *out_size = size;
        int *copy = malloc(size * sizeof(int));
        if (!copy) {
            perror("malloc");
            exit(EXIT_FAILURE);
        }
        for (int i = 0; i < size; ++i) {
            copy[i] = arr[i];
        }
        return copy;
    }
    int *result = malloc((size - 1) * sizeof(int));
    if (!result) {
        perror("malloc");
        exit(EXIT_FAILURE);
    }
    int idx = 0;
    for (int i = 0; i < size; ++i) {
        if ((size_t)i != pos) {
            result[idx++] = arr[i];
        }
    }
    *out_size = size - 1;
    return result;
}

int main(void) {
    int arr[] = {1, 2, 3, 4, 5};
    int size = sizeof(arr) / sizeof(arr[0]);
    int element = 3;
    int new_size = 0;

    printf("Before insertion: ");
    print_array(arr, size);

    int *result = insert(arr, size, element, &new_size);
    size = new_size;

    printf("After insertion: ");
    print_array(result, size);

    size_t pos = find_position_to_delete(result, size, element);
    if (pos != (size_t)-1) {
        int *new_arr = delete_element(result, size, element, &new_size);
        free(result);
        result = new_arr;
        size = new_size;

        printf("After deletion: ");
        print_array(result, size);
        free(result);
    } else {
        printf("Element not found\n");
        free(result);
    }

    return 0;
}
