#include <stdio.h>
#include <stdlib.h>

#define MAX(a, b) (((a) > (b)) ? (a) : (b))

struct Node {
    int data;
    struct Node* left;
    struct Node* right;
};

struct Node* newNode(struct Node* parentNode) {
    struct Node* localNode = malloc(sizeof(struct Node));
    if (localNode) {
        localNode->data = 0;
        localNode->left = localNode->right = NULL;
        if (parentNode) {
            localNode->parent = parentNode;
        }
        return localNode;
    } else {
        free(localNode);
        return NULL;
    }
}

int max(int a, int b) {
    return (a > b)? a : b;
}

int largestIndependentSet(struct Node* root, struct Node* parentNode) {
    if (root == NULL)
        return 0;
    else if (root->left == NULL && root->right == NULL)
        return 1;
    else {
        int sizeExcludingRoot = (root->left)? largestIndependentSet(root->left, parentNode) : 0 + (root->right)? largestIndependentSet(root->right, parentNode) : 0;
        int sizeIncludingRoot = 1;
        if (root->left)
            sizeIncludingRoot += (root->left->left && root->left->left->left && root->left->left->right)? largestIndependentSet(root->left->left->left, root) : 0 + (root->left->left && root->left->left->right)? largestIndependentSet(root->left->left->right, root) : 0 + (root->left->right && root->left->right->left && root->left->right->right)? largestIndependentSet(root->left->right->left, root) : 0 + (root->left->right && root->left->right->right)? largestIndependentSet(root->left->right->right, root) : 0;
        if (root->right)
            sizeIncludingRoot += (root->right->left && root->right->left->left && root->right->left->right)? largestIndependentSet(root->right->left->left, root) : 0 + (root->right->left && root->right->left->right)? largestIndependentSet(root->right->left->right, root) : 0 + (root->right->right && root->right->right->left && root->right->right->right)? largestIndependentSet(root->right->right->left, root) : 0 + (root->right->right && root->right->right->right)? largestIndependentSet(root->right->right->right, root) : 0;
        return MAX(sizeExcludingRoot, sizeIncludingRoot);
    }
}

int main(void) {
    struct Node *localRoot = newNode(NULL);
    if (localRoot) {
        localRoot->left = newNode(localRoot);
        localRoot->right = newNode(localRoot);
        localRoot->left->left = newNode(localRoot);
        localRoot->left->right = newNode(localRoot);
        localRoot->right->left = newNode(localRoot);
        localRoot->right->right = newNode(localRoot);
        localRoot->left->left->left = newNode(localRoot);
        localRoot->left->left->right = newNode(localRoot);

        printf("Size of the largest independent set is %d", largestIndependentSet(localRoot, localRoot));
    }
    return 0;
}
