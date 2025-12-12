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

static Node *right_rotate(Node *y) {
    Node *x = y->left;
    Node *t2 = x->right;
    x->right = y;
    y->left = t2;
    y->height = max(height(y->left), height(y->right)) + 1;
    x->height = max(height(x->left), height(x->right)) + 1;
    return x;
}

static Node *left_rotate(Node *x) {
    Node *y = x->right;
    Node *t2 = y->left;
    y->left = x;
    x->right = t2;
    x->height = max(height(x->left), height(x->right)) + 1;
    y->height = max(height(y->left), height(y->right)) + 1;
    return y;
}

static int get_balance(Node *node) {
    if (!node) return 0;
    return height(node->left) - height(node->right);
}

static Node *insert(Node *node, int key) {
    if (!node) return new_node(key);
    if (key < node->key) node->left = insert(node->left, key);
    else if (key > node->key) node->right = insert(node->right, key);
    else return node;

    node->height = max(height(node->left), height(node->right)) + 1;
    int balance = get_balance(node);

    if (balance > 1 && key < node->left->key) return right_rotate(node);
    if (balance < -1 && key > node->right->key) return left_rotate(node);
    if (balance > 1 && key > node->left->key) {
        node->left = left_rotate(node->left);
        return right_rotate(node);
    }
    if (balance < -1 && key < node->right->key) {
        node->right = right_rotate(node->right);
        return left_rotate(node);
    }
    return node;
}

static void inorder(Node *root) {
    if (!root) return;
    inorder(root->left);
    printf("%d ", root->key);
    inorder(root->right);
}

int main(void) {
    Node *root = NULL;
    int keys[] = {10, 20, 30, 40, 50, 25};
    for (size_t i = 0; i < sizeof(keys) / sizeof(keys[0]); ++i) {
        root = insert(root, keys[i]);
    }
    inorder(root);
    printf("\n");
    return 0;
}
