#include <stdio.h>
#include <stdlib.h>

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
    if (!root) {
        return newNode(data);
    }
    if (data < root->data) {
        root->left = insert(root->left, data);
    } else if (data > root->data) {
        root->right = insert(root->right, data);
    }
    return root;
}

static struct Node *lca(struct Node *root, int n1, int n2) {
    while (root) {
        if (root->data > n1 && root->data > n2) {
            root = root->left;
        } else if (root->data < n1 && root->data < n2) {
            root = root->right;
        } else {
            return root;
        }
    }
    return NULL;
}

int main(void) {
    struct Node *root = NULL;
    int values[] = {20, 8, 22, 4, 12, 10, 14};
    for (size_t i = 0; i < sizeof(values) / sizeof(values[0]); ++i) {
        root = insert(root, values[i]);
    }

    int n1 = 10, n2 = 14;
    struct Node *node = lca(root, n1, n2);
    if (node) {
        printf("LCA of %d and %d is %d\n", n1, n2, node->data);
    }
    return 0;
}
