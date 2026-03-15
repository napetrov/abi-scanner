#include <cstdio>

/* Opaque handle — app only knows about the extern "C" interface */
struct Buffer;  /* forward declaration */

extern "C" Buffer* make_buffer();
extern "C" void    reset_buffer(Buffer* b);

/* App compiled against v1: reset_buffer calls reset() noexcept.
   With v2.so: reset() throws std::runtime_error → std::terminate is called
   because the noexcept contract is violated. */

int main() {
    printf("Creating buffer...\n");
    Buffer* b = make_buffer();
    printf("Calling reset_buffer()...\n");
    /* With v1.so: completes normally.
       With v2.so: reset() throws, noexcept violation → std::terminate → abort */
    reset_buffer(b);
    printf("reset_buffer() returned normally\n");
    printf("OK — v1 baseline\n");
    return 0;
}
