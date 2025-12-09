#include <stdio.h>
#include <stdlib.h>

// A binary tree node has data , pointer to left child and a pointer to right child
struct Node
{
    int data;
    struct Node* left;
    struct Node* right;
};

// Helper function that allocates a new node with the given data and NULL left and right pointers 
struct Node* newNode(int data)
{
    struct Node* node = (struct Node*)malloc(sizeof(struct Node));
    node->data = data;
    node->left = NULL;
    node->right = NULL;

    return(node);
}

// Helper function to print Inorder traversal 
void printInorder(struct Node* node)
{
    if (node == NULL)
        return;

    printInorder(node->left);
    printf("%d ", node->data);
    printInorder(node->right);
}

// Helper function to convert a binary tree to its mirror
void mirror(struct Node* node)
{
    if (node == NULL)
        return;

    struct Node* temp = node->left;
    node->left = node->right;
    node->right = temp;

    mirror(node->left);
    mirror(node->right);
}

// Driver program to test mirror()
int main()
{
    struct Node *root = newNode(1);
    root->left = newNode(2);
    root->right = newNode(3);
    root->left->left = newNode(4);
    root->left->right = newNode(5);

    printf("Inorder traversal before conversion to mirror\n");
    printInorder(root);

    // Convert tree to its mirror
    mirror(root);

    printf("\nInorder traversal after conversion to mirror\n");
    printInorder(root);

    return 0;
}

