#include <stdio.h>
  2: #include <stdlib.h>
  3: #include <limits.h>
  4: #include <math.h>
  5: #define MIN_INT (INT_MIN)
  6: #define MAX_INT (INT_MAX)
  7: 
  8: struct Node {
  9:     int data;
 10:     struct Node* left;
 11:     struct Node* right;
 12: };
 13: 
 14: struct Node* newNode(int data) {
 15:     if(data < MIN_INT || data > MAX_INT || data >= INT_MAX) {
 16:         printf("Invalid data value: %d\n", data);
 17:         exit(0);
 18:     }
 19:     if(sizeof(int) * CHAR_BIT <= data) {
 20:         printf("Invalid data value: %d\n", data);
 21:         exit(0);
 22:     }
 23:     struct Node* temp = malloc(sizeof(struct Node));
 24:     if(temp == NULL) {
 25:         printf("Memory allocation failed.\n");
 26:         exit(0);
 27:     }
 28:     struct Node* node = temp;
 29:     node->data = data;
 30:     node->left = NULL;
 31:     node->right = NULL;
 32:     return node;
 33: }
 34: 
 35: void insert(struct Node** root_ref, int data) {
 36:     if(*root_ref == NULL) {
 37:         *root_ref = newNode(data);
 38:         return;
 39:     }
 40:     struct Node* current = *root_ref;
 41:     while (1) {
 42:         if (data < current->data) {
 43:             if (current->left == NULL) {
 44:                 current->left = newNode(data);
 45:                 break;
 46:             }
 47:             else
 48:                 current = current->left;
 49:         }
 50:         else if (data > current->data) {
 51:             if (current->right == NULL) {
 52:                 current->right = newNode(data);
 53:                 break;
 54:             }
 55:             else
 56:                 current = current->right;
 57:         }
 58:         else
 59:             break;
 60:     }
 61: }
 62: 
 63: struct Node* LCA(struct Node* node, int n1, int n2) {
 64:     if (node == NULL)
 65:         return NULL;
 66:     if (node->data > n1 && node->data > n2)
 67:         return LCA(node->left, n1, n2);
 68:     if (node->data < n1 && node->data < n2)
 69:         return LCA(node->right, n1, n2);
 70:     return node;
 71: }
