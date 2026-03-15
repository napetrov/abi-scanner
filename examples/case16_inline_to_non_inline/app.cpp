#include <cstdio>
#include "v2.hpp"   /* v2 header: fast_hash is declared but NOT inline */

/* App includes v2.hpp (non-inline declaration) but links against libv1.so.
   v1.so has NO fast_hash symbol (it was header-only inline).
   Result: undefined symbol: fast_hash at link time or load time. */

int main() {
    int h = fast_hash(42);
    printf("fast_hash(42) = %d\n", h);
    return 0;
}
