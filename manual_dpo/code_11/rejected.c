#include <stdio.h>
#include <math.h>

// Function to find the angle between two planes in 3D
double find_angle(double x1, double y1, double z1, double x2, double y2, double z2) {
    double dot_product = x1*x2 + y1*y2 + z1*z2;
    double magnitude1 = sqrt(x1*x1 + y1*y1 + z1*z1);
    double magnitude2 = sqrt(x2*x2 + y2*y2 + z2*z2);
    double cos_theta = dot_product / (magnitude1 * magnitude2);
    double angle = acos(cos_theta);
    return angle;
}

int main() {
    double x1, y1, z1, x2, y2, z2;
    printf("Enter the coordinates of the first plane: ");
    scanf("%lf %lf %lf", &x1, &y1, &z1);
    printf("Enter the coordinates of the second plane: ");
    scanf("%lf %lf %lf", &x2, &y2, &z2);
    double angle = find_angle(x1, y1, z1, x2, y2, z2);
    printf("The angle between the two planes is %.2lf degrees\n", angle * (180.0 / M_PI));
    return 0;
}

