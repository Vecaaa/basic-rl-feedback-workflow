#include <stdio.h>
#include <stdlib.h>
#include <limits.h>

struct Node {
    int data;
    struct Node *left;
    struct Node *right;
};

static struct Node *newNode(int data) {
    struct Node *node = (struct Node *)malloc(sizeof(struct Node));
    if (!node) {
        perror("malloc");
        exit(EXIT_FAILURE);
    }
    node->data = data;
    node->left = node->right = NULL;
    return node;
}

static struct Node *insert(struct Node *root, int data) {
    if (root == NULL) {
        return newNode(data);
    }
    if (data <= root->data) {
        root->left = insert(root->left, data);
    } else {
        root->right = insert(root->right, data);
    }
    return root;
}

static int treePathsSumUtil(struct Node *root, int val) {
    if (!root) {
        return 0;
    }
    val = val * 10 + root->data;
    if (!root->left && !root->right) {
        return val;
    }
    return treePathsSumUtil(root->left, val) + treePathsSumUtil(root->right, val);
}

static int treePathsSum(struct Node *root) {
    return treePathsSumUtil(root, 0);
}

int main(void) {
    struct Node *root = NULL;
    int values[] = {2, 3, 1, 4, 5, 6, 7, 8, 9, 10};
    for (size_t i = 0; i < sizeof(values) / sizeof(values[0]); ++i) {
        root = insert(root, values[i]);
    }

    int sum = treePathsSum(root);
    printf("Sum of all root to leaf paths is %d\n", sum);
    return 0;
}
