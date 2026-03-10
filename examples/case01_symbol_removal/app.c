#include <stdio.h>

extern int compute(int x);
extern int helper(int x);

int main(void) {
    printf("compute(5) = %d\n", compute(5));
    printf("helper(5)  = %d\n", helper(5));
    return 0;
}
