// v2: reset() loses noexcept AND now actually throws — causes std::terminate
//     when called from noexcept context compiled against v1
#include <stdexcept>

class Buffer {
public:
    Buffer();
    ~Buffer();
    void reset();  /* noexcept REMOVED — now throws */
private:
    int* data_;
    int  size_;
};

Buffer::Buffer() : data_(new int[64]), size_(64) {}
Buffer::~Buffer() { delete[] data_; }

void Buffer::reset() {
    throw std::runtime_error("reset failed");  /* triggers std::terminate in noexcept callers */
}

extern "C" Buffer* make_buffer() { return new Buffer(); }
extern "C" void reset_buffer(Buffer* b) { b->reset(); }
