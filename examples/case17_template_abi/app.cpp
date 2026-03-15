#include "v1.hpp"
#include <cstdio>
#include <cstddef>
#include <new>

/* App compiled against v1.hpp layout: Buffer<int> = {data_*, size_} = 16 bytes.
   With v2.so: Buffer<int> constructor also initializes capacity_ at offset 16 —
   writing 8 bytes BEYOND what app allocated on stack (if using stack placement)
   or beyond what app thinks the struct holds.

   Concrete demo: use a stack canary after the buffer to detect the overwrite. */

extern template class Buffer<int>;  /* from v1.hpp */

int main() {
    /* Stack layout: [Buffer<int> buf: 16 bytes][canary: 8 bytes] */
    alignas(alignof(Buffer<int>)) char raw[sizeof(Buffer<int>)];  /* v1 size = 16 bytes */
    long canary = (long)0xCAFEBABEDEADBEEFL;

    printf("sizeof(Buffer<int>) per v1.hpp = %zu bytes\n", sizeof(Buffer<int>));
    printf("canary before = 0x%lX\n", canary);

    /* Placement-new: constructor comes from .so — v2 writes capacity_ at offset 16 */
    Buffer<int>* buf = ::new (raw) Buffer<int>(4);

    printf("buf->size()   = %zu\n", buf->size());
    printf("canary after  = 0x%lX\n", canary);

    if (canary != (long)0xCAFEBABEDEADBEEFL)
        printf("CORRUPTION: v2 constructor wrote capacity_ beyond v1 allocation boundary!\n");
    else
        printf("Canary intact (run with ASAN for definitive detection)\n");

    buf->~Buffer<int>();
    return 0;
}
