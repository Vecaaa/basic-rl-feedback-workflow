#include <stdio.h>

#define MAX_SIZE 16

typedef struct {
    int data[MAX_SIZE];
    int size;
} IntArray;

int search(const IntArray *arr, int x) {
    for (int i = 0; i < arr->size; ++i) {
        if (arr->data[i] == x) {
            return i;
        }
    }
    return -1;
}

int insert(IntArray *arr, int x, int pos) {
    if (arr->size >= MAX_SIZE || pos < 0 || pos > arr->size) {
        return 0;
    }
    for (int i = arr->size; i > pos; --i) {
        arr->data[i] = arr->data[i - 1];
    }
    arr->data[pos] = x;
    arr->size++;
    return 1;
}

int delete_value(IntArray *arr, int x) {
    int pos = search(arr, x);
    if (pos == -1) {
        return 0;
    }
    for (int i = pos; i < arr->size - 1; ++i) {
        arr->data[i] = arr->data[i + 1];
    }
    arr->data[arr->size - 1] = 0;
    arr->size--;
    return 1;
}

int main(void) {
    IntArray arr = {.data = {1, 2, 3, 4, 5}, .size = 5};
    int x = 3;
    int pos = 2;

    printf("Search result: %d\n", search(&arr, x));

    if (insert(&arr, x, pos)) {
        printf("After insertion: ");
        for (int i = 0; i < arr.size; ++i) {
            printf("%d ", arr.data[i]);
        }
        printf("\n");
    }

    if (delete_value(&arr, x)) {
        printf("After deletion: ");
        for (int i = 0; i < arr.size; ++i) {
            printf("%d ", arr.data[i]);
        }
        printf("\n");
    }

    return 0;
}
