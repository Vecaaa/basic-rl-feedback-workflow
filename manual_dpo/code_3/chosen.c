#include <stdio.h>
#include <stdlib.h>

typedef struct Node {
    int data;
    struct Node* next;
} Node;

Node* createNode(int data) {
    Node* newNode = (Node*)malloc(sizeof(Node));
    if (!newNode) {
        perror("malloc failed");
        exit(EXIT_FAILURE);
    }
    newNode->data = data;
    newNode->next = NULL;
    return newNode;
}

static Node* append_range(int start_num, int end_num) {
    Node* head = NULL;
    Node* tail = NULL;
    for (int i = start_num; i <= end_num; i++) {
        Node* node = createNode(i);
        if (!head) {
            head = tail = node;
        } else {
            tail->next = node;
            tail = node;
        }
    }
    return head;
}

Node* generateCantorSet(int n, int start_num, int end_num) {
    if (n <= 0 || start_num > end_num) {
        return NULL;
    }

    Node* head = append_range(start_num, end_num);
    Node* tail = head;
    while (tail && tail->next) {
        tail = tail->next;
    }

    int mid = (start_num + end_num) / 2;
    Node* left = generateCantorSet(n - 1, start_num, mid);
    Node* right = generateCantorSet(n - 1, mid + 1, end_num);

    if (tail) {
        if (left) {
            tail->next = left;
            while (tail->next) {
                tail = tail->next;
            }
        }
        if (right) {
            tail->next = right;
        }
    }

    return head;
}

void printList(Node* head) {
    for (Node* temp = head; temp != NULL; temp = temp->next) {
        printf("%d ", temp->data);
    }
    printf("\n");
}

int main() {
    int n = 3;
    int start_num = 1;
    int end_num = 3;

    Node* head = generateCantorSet(n, start_num, end_num);
    printList(head);

    return 0;
}
