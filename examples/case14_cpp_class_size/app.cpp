#include <cstdio>
#include <cstdlib>

/* App compiled against v1 Buffer layout: sizeof(Buffer) includes 64-byte data array.
   Factory function returns a heap-allocated Buffer from the library.
   With v2.so: make_buffer() allocates 128-byte buffer object — correctly.
   If the app ever allocates its OWN Buffer (e.g., Buffer buf; or new Buffer()),
   it only reserves 64 bytes but v2's constructor / methods write 128 bytes → overflow.

   This demo shows: v2's make_buffer() returns size()=128 while app expects 64.
   A real crash happens when app code does:  char storage[sizeof_v1_Buffer]; new(storage)Buffer;
*/

extern "C" {
    void* make_buffer(void);         /* returns Buffer* — opaque */
    int   buffer_size(void* buf);    /* calls buf->size() via C wrapper */
    void  free_buffer(void* buf);    /* calls delete */
}

int main() {
    void* b = make_buffer();
    int sz = buffer_size(b);
    printf("Buffer::size() from library = %d\n", sz);

    if (sz == 64)
        printf("OK — v1 baseline: 64-byte buffer\n");
    else if (sz == 128)
        printf("ABI MISMATCH: v2 Buffer uses 128 bytes; app assumes 64-byte layout.\n"
               "Any stack/embedded Buffer in app code would overflow by 64 bytes.\n");

    free_buffer(b);
    return 0;
}
