#include <stdio.h>
  2: #include <ctype.h>
  3: #include <limits.h>
  4: 
  5: int my_atoi(char *str) {
  6:     int result = 0;
  7:     int sign = 1;
  8:     if (*str == '\0') {
  9:         return 0;
 10:     }
 11:     if (*str == '+') {
 12:         str++;
 13:     } else if (*str == '-') {
 14:         sign = -1;
 15:         str++;
 16:     }
 17:     while (*str != '\0') {
 18:         if (*str >= '0' && *str <= '9') {
 19:             result = (result * 10) + (*str - '0');
 20:         } else if (*str == ' ') {
 21:             str++;
 22:             continue;
 23:         } else {
 24:             return 0;
 25:         }
 26:         str++;
 27:     }
 28:     if (result > INT_MAX) {
 29:         return 0;
 30:     } else if (result < INT_MIN) {
 31:         return 0;
 32:     }
 33:     return result * sign;
 34: }
 35: 
 36: int main() {
 37:     char str[] = "   -123456";
 38:     printf("%d\n", my_atoi(str));
 39:     return 0;
 40: }
