#include <stdio.h>
#include <stdlib.h>

struct TreeNode {
    int val;
    struct TreeNode *left;
    struct TreeNode *right;
};

struct TreeNode* newNode(int data) {
    struct TreeNode* node = (struct TreeNode*)malloc(sizeof(struct TreeNode));
    node->val = data;
    node->left = NULL;
    node->right = NULL;
    return(node);
}

int hasPathSum(struct TreeNode* node, int sum) {
    if (node == NULL) {
        return (sum == 0);
    } else {
        bool answer = false;
        int subSum = sum - node->val;
        if (subSum == 0 && node->left == NULL && node->right == NULL) {
            return true;
        } else {
            answer = answer || hasPathSum(node->left, subSum);
            answer = answer || hasPathSum(node->right, subSum);
        }
        return answer;
    }
}

int main() {
    struct TreeNode *root = newNode(10);
    root->left = newNode(8);
    root->right = newNode(2);
    root->left->left = newNode(3);
    root->left->right = newNode(5);
    root->right->left = newNode(2);

    if (hasPathSum(root, 22)) {
        printf("Path exists\n");
    } else {
        printf("Path does not exist\n");
    }

    return 0;
}

