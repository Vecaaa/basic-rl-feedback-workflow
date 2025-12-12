#include <stdio.h>
#include <stdlib.h>

struct Node {
    int data;
    struct Node* left;
    struct Node* right;
};

struct Node* newNode(int data) {
    struct Node *node;
    node = malloc(sizeof(struct Node));
    if(node == NULL) {
        printf("Memory not allocated.\n");
        exit(EXIT_FAILURE);
    }
    node->data = data;
    node->left = NULL;
    node->right = NULL;
    return(node);
}

struct Node* insert(struct Node node, int data) {
    if (node.left == NULL)
        return(newNode(data));
    else {
        if (data <= node.data)
            node.left = insert(node.left, data);
        else
            node.right = insert(node.right, data);
        return node;
    }
}

int treePathsSumUtil(struct Node root, int val) {
    int temp_val;
    if (root.left == NULL && root.right == NULL)
        return val;
    temp_val = val;
    val = val > 0 ? val : 0;
    return treePathsSumUtil(root.left, val) + treePathsSumUtil(root.right, temp_val);
}

int treePathsSum(struct Node root) {
    return treePathsSumUtil(root, 0);
}

int main(void) {
    struct Node root;
    root.data = 2;
    insert(root, 3);
    insert(root, 1);
    insert(root, 4);
    insert(root, 5);
    insert(root, 6);
    insert(root, 7);
    insert(root, 8);
    insert(root, 9);
    insert(root, 10);
    int sum = treePathsSum(root);
    if (sum < 0 || sum == INT_MIN) {
        printf("Error: Sum of root to leaf paths should be non-negative. Found %d or INT_MIN\n", sum);
    } else {
        printf("Sum of all root to leaf paths is %d\n", (sum > 0 || sum == INT_MIN) ? sum : 0);
    }
    return 0;
}
