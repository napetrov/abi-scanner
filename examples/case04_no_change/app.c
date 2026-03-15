#include <stdio.h>

extern int stable_api(int x);

int main(void) {
    int result = stable_api(42);
    printf("stable_api(42) = %d (expected 42)\n", result);
    if (result == 42)
        printf("OK — baseline: works correctly\n");
    else
        printf("UNEXPECTED result: %d\n", result);
    return 0;
}
