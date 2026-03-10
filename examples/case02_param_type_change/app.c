#include <stdio.h>

/* v1 signature: process(int, int) → double */
extern double process(int a, int b);

int main(void) {
    double r = process(3, 4);
    printf("Expected: 7.000000\n");
    printf("Got:      %f\n", r);
    if (r != 7.0)
        fprintf(stderr, "WRONG RESULT — ABI mismatch (int vs double argument passing)\n");
    return 0;
}
