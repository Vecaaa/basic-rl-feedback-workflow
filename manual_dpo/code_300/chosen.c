#include <stdio.h>
#include <stdlib.h>

typedef struct Node {
    int key;
    int height;
    struct Node *left;
    struct Node *right;
} Node;

static Node *new_node(int key) {
    Node *node = (Node *)malloc(sizeof(Node));
    if (!node) {
        perror("malloc");
        exit(EXIT_FAILURE);
    }
    node->key = key;
    node->height = 1;
    node->left = node->right = NULL;
    return node;
}

static int max(int a, int b) { return (a > b) ? a : b; }
static int height(Node *n) { return n ? n->height : 0; }

static Node *insert(Node *root, int key) {
    if (!root) return new_node(key);
    if (key < root->key) root->left = insert(root->left, key);
    else if (key > root->key) root->right = insert(root->right, key);
    else return root;
    root->height = max(height(root->left), height(root->right)) + 1;
    return root;
}

static void inorder(Node *root) {
    if (!root) return;
    inorder(root->left);
    printf("%d ", root->key);
    inorder(root->right);
}

int main(void) {
    Node *root = NULL;
    int values[] = {5, 3, 8, 1, 4};
    for (size_t i = 0; i < sizeof(values)/sizeof(values[0]); ++i) {
        root = insert(root, values[i]);
    }
    inorder(root);
    printf("\n");
    return 0;
}
