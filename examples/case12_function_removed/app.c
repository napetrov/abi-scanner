#include <stdio.h>

extern int fast_add(int a, int b);
extern int other_func(int x);

int main(void) {
    printf("fast_add(3,4)  = %d\n", fast_add(3, 4));
    printf("other_func(5)  = %d\n", other_func(5));
    return 0;
}
