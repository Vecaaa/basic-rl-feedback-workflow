#include<stdio.h>

int min(int a, int b) {
    return (a < b)? a: b;
}

int minTime(int n, int t1, int t2, int *T1, int *T2) {
    if(n == 0) {
        return 0;
    }
    if(T1[n-1] != -1) {
        return T1[n-1];
    }
    int time1 = t1 + minTime(n-1, t2, t1, T2, n-1);
    int time2 = t2 + minTime(n-1, t1, t2, T1, n-1);
    T1[n-1] = min(time1, time2);
    return T1[n-1];
}

int main() {
    int n = 5;
    int t1 = 2, t2 = 3;
    int T1[n], T2[n];
    for(int i = 0; i < n; i++) {
        T1[i] = -1;
        T2[i] = -1;
    }
    int *minTime = T1;
    int minTimeValue = minTime(n, t1, t2, minTime, T2);
    printf("Minimum time: %d\n", minTimeValue);
    return 0;
}
