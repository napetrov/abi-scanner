#include <stdio.h>

extern int foo(void);
extern int bar(void);

int main(void) {
    printf("foo() = %d\n", foo());
    printf("bar() = %d\n", bar());
    printf("OK — symbol versioning is a deployment/compat tooling concern, not a crash\n");
    return 0;
}
