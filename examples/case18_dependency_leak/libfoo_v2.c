#include "foo_v2.h"
#include <stdio.h>

/* libfoo v2 implementation — compiled with new ThirdPartyHandle (x + y fields).
   process() now reads BOTH x and y; app only allocates for x (4 bytes). */
void process(ThirdPartyHandle* h) {
    printf("process: x=%d y=%d\n", h->x, h->y);  /* h->y reads 4 bytes past app's allocation */
}

int get_value(const ThirdPartyHandle* h) {
    return h->x + h->y;  /* y is garbage from app's stack/heap — wrong result */
}
