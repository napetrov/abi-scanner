#include <stdio.h>

extern int get_version(void);

int main(void) {
    int v = get_version();
    printf("version = %d (expected 1)\n", v);
    if (v == 1)
        printf("OK — no breakage, compatible addition\n");
    else
        printf("UNEXPECTED version value: %d\n", v);
    return 0;
}
