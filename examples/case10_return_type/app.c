#include <stdio.h>

/* App compiled against v1: get_count() returns int */
extern int get_count(void);

int main(void) {
    int n = get_count();
    printf("Expected: 42 (v1) or 3000000000 (v2 demo)\n");
    printf("Got (as int): %d\n", n);
    /* With v2.so: long 3000000000 in rax, read as int = -1294967296 (truncated) */
    if (n != 42)
        printf("TRUNCATION: v2 returned 3000000000L, int reads only low 32 bits → %d\n", n);
    else
        printf("OK — v1 baseline\n");
    return 0;
}
