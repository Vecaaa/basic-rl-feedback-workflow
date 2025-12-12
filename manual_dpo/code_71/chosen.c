#include <stdio.h>
#include <stdlib.h>

struct Node {
    int data;
    int memo;
    struct Node *left;
    struct Node *right;
};

struct Node *newNode(int data) {
    struct Node *node = (struct Node *)malloc(sizeof(struct Node));
    if (!node) {
        perror("malloc");
        exit(EXIT_FAILURE);
    }
    node->data = data;
    node->memo = 0;
    node->left = node->right = NULL;
    return node;
}

static int liss(struct Node *root) {
    if (!root) {
        return 0;
    }
    if (!root->left && !root->right) {
        root->memo = 1;
        return 1;
    }
    if (root->memo > 0) {
        return root->memo;
    }

    int excl = liss(root->left) + liss(root->right);

    int incl = 1;
    if (root->left) {
        incl += liss(root->left->left);
        incl += liss(root->left->right);
    }
    if (root->right) {
        incl += liss(root->right->left);
        incl += liss(root->right->right);
    }

    root->memo = (incl > excl) ? incl : excl;
    return root->memo;
}

int largestIndependentSet(struct Node *root) {
    return liss(root);
}

int main(void) {
    struct Node *root = newNode(10);
    root->left = newNode(20);
    root->right = newNode(30);
    root->left->left = newNode(40);
    root->left->right = newNode(50);
    root->right->left = newNode(60);
    root->right->right = newNode(70);

    printf("Size of the largest independent set is %d\n", largestIndependentSet(root));
    return 0;
}
