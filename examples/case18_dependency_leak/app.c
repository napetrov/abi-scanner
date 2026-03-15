#include <stdio.h>
#include "foo_v1.h"  /* v1 ThirdPartyHandle: { int x } — 4 bytes */

/* App compiled against v1 headers: ThirdPartyHandle has only x */

int main(void) {
    ThirdPartyHandle h = {42};  /* allocates 4 bytes: {x=42} */

    printf("Sending h={x=%d} (4 bytes) to process()\n", h.x);
    process(&h);

    int val = get_value(&h);
    printf("get_value() = %d (expected 42)\n", val);

    if (val != 42)
        printf("WRONG: v2 library read h.y from uninitialized memory past the struct!\n");
    else
        printf("OK — v1 baseline\n");

    return 0;
}
