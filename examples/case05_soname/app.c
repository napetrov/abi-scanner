#include <stdio.h>

/* foo() exists in both good.so and bad.so — runtime works either way */
extern int foo(void);

int main(void) {
    int r = foo();
    printf("foo() = %d\n", r);
    printf("Runtime: OK — SONAME issue is a packaging/install problem, not a crash\n");
    return 0;
}
