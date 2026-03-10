#include <stdio.h>

/* App compiled against v1: lib_version is int (4 bytes) */
extern int lib_version;

int main(void) {
    printf("lib_version = %d\n", lib_version);
    /* With v1.so: lib_version=1 → prints 1 (correct)
       With v2.so: lib_version is long 5000000000, reading 4 bytes gives
       705032704 (0x29A00000) on little-endian — wrong! */
    if (lib_version == 1)
        printf("OK — v1 baseline\n");
    else
        printf("WRONG READ: v2 lib_version=5000000000L, int reads low 32 bits → %d\n",
               lib_version);
    return 0;
}
