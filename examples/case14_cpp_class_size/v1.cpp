class Buffer {
public:
    virtual int size() { return 64; }
private:
    char data[64];
};
extern "C" Buffer* make_buffer() { return new Buffer(); }
extern "C" int   buffer_size(void* buf) { return static_cast<Buffer*>(buf)->size(); }
extern "C" void  free_buffer(void* buf) { delete static_cast<Buffer*>(buf); }
