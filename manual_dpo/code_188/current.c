#include <stdio.h>
#include <stdlib.h>

typedef struct Node_tag {
    struct Node_tag *left;
    struct Node_tag *right;
    int key, height;
}
