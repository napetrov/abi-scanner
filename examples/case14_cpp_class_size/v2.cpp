/* data[128] — sizeof(Buffer) doubles, heap allocs undersize the object */
class Buffer {
public:
    virtual int size() { return 128; }
private:
    char data[128];
};
extern "C" Buffer* make_buffer() { return new Buffer(); }
extern "C" int   buffer_size(void* buf) { return static_cast<Buffer*>(buf)->size(); }
extern "C" void  free_buffer(void* buf) { delete static_cast<Buffer*>(buf); }
