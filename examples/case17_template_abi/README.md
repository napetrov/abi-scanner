# Case 17 — Template Instantiation ABI Change


**Risk:** 🔴 BREAKING | **Category:** C++ ABI | **Verdict:** 🔴 ABI CHANGE (exit 4, needs DWARF)

## What changes

| Version | `Buffer<int>` layout |
|---------|---------------------|
| v1 | `{ T* data_; size_t size_; }` → sizeof = 16 bytes (64-bit) |
| v2 | `{ T* data_; size_t size_; size_t capacity_; }` → sizeof = 24 bytes |

## What breaks at binary level

C++ template classes with explicit instantiations are compiled into the `.so` like
regular classes. The mangled symbol for `Buffer<int>::Buffer(size_t)` is
`_ZN6BufferIiEC1Em` — identical in both versions.

A caller compiled against v1 headers **allocates** `sizeof(Buffer<int>) = 16` bytes
(e.g. on the stack or in a struct). The v2 `.so` constructor writes **24 bytes** —
overwriting 8 bytes past the allocated region. This is a classic **stack smash / heap
corruption** scenario, extremely hard to debug.

# Case 17 — Template Instantiation ABI Change

## What changes

| Version | `Buffer<int>` layout |
|---------|---------------------|
| v1 | `{ T* data_; size_t size_; }` → sizeof = 16 bytes (64-bit) |
| v2 | `{ T* data_; size_t size_; size_t capacity_; }` → sizeof = 24 bytes |

## What breaks at binary level

C++ template classes with explicit instantiations are compiled into the `.so` like
regular classes. The mangled symbol for `Buffer<int>::Buffer(size_t)` is
`_ZN6BufferIiEC1Em` — identical in both versions.

A caller compiled against v1 headers **allocates** `sizeof(Buffer<int>) = 16` bytes
(e.g. on the stack or in a struct). The v2 `.so` constructor writes **24 bytes** —
overwriting 8 bytes past the allocated region. This is a classic **stack smash / heap
corruption** scenario, extremely hard to debug.

## Real Failure Demo

**Severity: CRITICAL**

**Scenario:** compile `app` against v1.hpp (`Buffer<int>` = 16 bytes), use placement-new with v2 `.so` constructor which writes 24 bytes.

```bash
# Step 1: build with v1
g++ -shared -fPIC -g v1.cpp -I. -o libbuf.so
g++ -g app.cpp -I. -L. -lbuf -Wl,-rpath,. -o app
./app
# Output:
# sizeof(Buffer<int>) per v1.hpp = 16 bytes
# canary before = 0xCAFEBABEDEADBEEF
# buf->size()   = 4
# canary after  = 0xCAFEBABEDEADBEEF
# Canary intact (run with ASAN for definitive detection)

# Step 2: swap in v2 (no recompile) — ASAN catches the overflow
g++ -shared -fPIC -g -fsanitize=address v2.cpp -I. -o libbuf.so
g++ -g -fsanitize=address app.cpp -I. -L. -lbuf -Wl,-rpath,. -o app_asan
./app_asan 2>&1 | head -10
# Output:
# sizeof(Buffer<int>) per v1.hpp = 16 bytes
# ==ERROR: AddressSanitizer: stack-buffer-overflow on address ...
# WRITE of size 8 at ... thread T0
#   #0 Buffer<int>::Buffer(unsigned long) v2.cpp:5
#   #1 main app.cpp:24
# ... 'raw' (line 17) Memory access at offset 48 overflows this variable
```

**Why:** App allocates 16 bytes for `Buffer<int>` (v1 layout); v2's constructor initializes a `capacity_` field at offset 16 — writing 8 bytes beyond the allocation, detected by ASAN as a stack-buffer-overflow.

## Why abidiff catches it (with DWARF)

When compiled with `-g`, DWARF records the type layout for `Buffer<int>`. `abidiff`
compares type offsets and sizes → detects `sizeof` grew from 16 to 24. Without `-g`,
abidiff sees only the symbol table and misses the layout change.

## Why ABICC catches it

ABICC parses the header AST and computes `sizeof` for all template instantiations
referenced in the headers. It sees `capacity_` was added and reports:
> "Size of type 'Buffer<int>' changed from 16 to 24 bytes."

## Real-world example

In **Intel oneDAL (daal)**, `HomogenNumericTable<float>` is a template class with
explicit instantiation in the `.so`. When a private member was added for thread-safety
tracking (2022), downstream Python bindings compiled with old headers wrote past
buffers. The bug was caught by ASAN in integration tests.

## Code diff

```diff
 template<typename T>
 class Buffer {
 private:
     T*          data_;
     std::size_t size_;
+    std::size_t capacity_;  // NEW field
 };
```

## Reproduce steps

```bash
cd examples/case17_template_abi

# Build with debug info
g++ -shared -fPIC -std=c++17 -g v1.cpp -o libv1.so
g++ -shared -fPIC -std=c++17 -g v2.cpp -o libv2.so

# abidiff WITH DWARF catches layout change
abidw --out-file v1.xml libv1.so
abidw --out-file v2.xml libv2.so
abidiff v1.xml v2.xml   # exit 4: reports Buffer<int> size change

# Build WITHOUT debug info (strip DWARF)
g++ -shared -fPIC -std=c++17 v1.cpp -o libv1_nodebug.so
g++ -shared -fPIC -std=c++17 v2.cpp -o libv2_nodebug.so
abidw --out-file v1nd.xml libv1_nodebug.so
abidw --out-file v2nd.xml libv2_nodebug.so
abidiff v1nd.xml v2nd.xml   # exit 0: MISSES the change (no DWARF)

# ABICC catches via header AST regardless of debug info
abi-compliance-checker -lib Buffer -v1 1.0 -v2 2.0 \
  -header v1.hpp -header v2.hpp \
  -gcc-options "-std=c++17"
```
