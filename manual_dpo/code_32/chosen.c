#include <stdio.h>
#include <stdlib.h>

// Node structure
struct Node {
    int data;
    struct Node* left;
    struct Node* right;
};

// Function to create a new node
struct Node* newNode(int data) {
    struct Node* node = (struct Node*)malloc(sizeof(struct Node));
    node->data = data;
    node->left = NULL;
    node->right = NULL;
    return(node);
}

// Helper function to print all root - to - leaf paths
void printPath(int path[], int size) {
    for (int i = 0; i < size; i++)
        printf("%d ", path[i]);
    printf("\n");
}

// Helper function to print all root - to - leaf paths
void collectPaths(struct Node* root, int path[], int pathLen) {
    if (root == NULL)
        return;

    path[pathLen] = root->data;
    pathLen++;

    if (root->left == NULL && root->right == NULL) {
        printPath(path, pathLen);
    } else {
        collectPaths(root->left, path, pathLen);
        collectPaths(root->right, path, pathLen);
    }
}

// Function to print all root - to - leaf paths of the binary tree
void printPaths(struct Node* root) {
    int path[1000];
    collectPaths(root, path, 0);
}

// Driver program to test paths
int main() {
    struct Node *root = newNode(1);
    root->left = newNode(2);
    root->right = newNode(3);
    root->left->left = newNode(4);
    root->left->right = newNode(5);
    root->right->left = newNode(6);
    root->right->right = newNode(7);

    printPaths(root);

    return 0;
}

