#include <stdio.h>

/* App compiled against v1 layout — Point has only x and y */
struct Point { int x; int y; };  /* v1: 8 bytes */

extern void init_point(struct Point *p);
extern int  get_x(struct Point *p);

int main(void) {
    struct Point p;
    int canary = (int)0xDEADBEEF;  /* sentinel placed right after p on stack */

    printf("Before init_point: p={?,?} canary=0x%X\n", canary);
    init_point(&p);  /* v2 writes p->z = 3 at offset 8 — past our 8-byte struct */
    printf("After  init_point: p={%d,%d} canary=0x%X\n", p.x, p.y, canary);

    if (canary != (int)0xDEADBEEF)
        printf("CORRUPTION DETECTED: canary overwritten by v2 library (wrote z past struct boundary)!\n");
    else
        printf("Canary intact (stack layout may have padded the gap — run with ASAN to confirm)\n");

    printf("get_x(&p) = %d (expected 1)\n", get_x(&p));
    return 0;
}
