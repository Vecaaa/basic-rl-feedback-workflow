#include <stdio.h>
#include <stdlib.h>

typedef struct Node {
    int data;
    struct Node* next;
} Node;

Node* createNode(int data) {
    Node* newNode = (Node*)malloc(sizeof(Node));
    newNode->data = data;
    newNode->next = NULL;
    return newNode;
}

Node* insertNode(Node* head, int data) {
    Node* newNode = createNode(data);
    if(head == NULL) {
        head = newNode;
    } else {
        Node* temp = head;
        while(temp->next != NULL) {
            temp = temp->next;
        }
        temp->next = newNode;
    }
    return head;
}

void printList(Node* head) {
    Node* temp = head;
    while(temp != NULL) {
        printf("%d ", temp->data);
        temp = temp->next;
    }
    printf("\n");
}

Node* generateCantorSet(int n, int start_num, int end_num) {
    if(n == 0) {
        return NULL;
    }

    Node* head = NULL;
    for(int i = start_num; i <= end_num; i++) {
        head = insertNode(head, i);
    }

    int mid = (start_num + end_num) / 2;
    head->next = generateCantorSet(n - 1, start_num, mid);
    if(head->next != NULL) {
        head->next->next = generateCantorSet(n - 1, mid + 1, end_num);
    }

    return head;
}

int main() {
    int n = 3;
    int start_num = 1;
    int end_num = 3;

    Node* head = generateCantorSet(n, start_num, end_num);
    printList(head);

    return 0;
}
