# Case 14: C++ Class Size Change

**Risk:** 🔴 BREAKING | **Category:** C++ ABI | **Verdict:** 🔴 ABI CHANGE (exit 4)

> **Note on abidiff 2.4.0:** Returns exit **4**. Semantically breaking for any
> code that heap-allocates `Buffer` via operator new or embeds it by value.

## What breaks
Old code allocates `new Buffer()` expecting 64 bytes. v2's `Buffer` needs 128 bytes.
The allocator returns only 64 bytes; writing to `data[64..127]` corrupts heap memory.
Any consumer that inherits from or embeds `Buffer` by value is also broken.

## Why abidiff catches it
Reports `type size changed from 512 to 1024 (in bits)` (64 bytes → 128 bytes).

## Code diff

| v1.cpp | v2.cpp |
|--------|--------|
| `char data[64];` | `char data[128];` |

## Reproduce manually
```bash
g++ -shared -fPIC -g v1.cpp -o libbuf_v1.so
g++ -shared -fPIC -g v2.cpp -o libbuf_v2.so
abidw --out-file v1.xml libbuf_v1.so
abidw --out-file v2.xml libbuf_v2.so
abidiff v1.xml v2.xml
echo "exit: $?"   # → 4
```

## Real Failure Demo

**Severity: CRITICAL**

**Scenario:** compile `app` against v1 (Buffer = 64 bytes), swap in v2 `.so` (Buffer = 128 bytes).

```bash
# Step 1: build with v1
g++ -shared -fPIC -g v1.cpp -o libbuf.so
g++ -g app.cpp -L. -lbuf -Wl,-rpath,. -o app
./app
# Output:
# Buffer::size() from library = 64
# OK — v1 baseline: 64-byte buffer

# Step 2: swap in v2 (no recompile)
g++ -shared -fPIC -g v2.cpp -o libbuf.so
./app
# Output:
# Buffer::size() from library = 128
# ABI MISMATCH: v2 Buffer uses 128 bytes; app assumes 64-byte layout.
# Any stack/embedded Buffer in app code would overflow by 64 bytes.

# Prove heap corruption with ASAN (compile both app and library):
g++ -shared -fPIC -g -fsanitize=address v2.cpp -o libbuf.so
g++ -g -fsanitize=address app.cpp -L. -lbuf -Wl,-rpath,. -o app_asan
# Stack-embedding Buffer with v1 sizeof triggers AddressSanitizer: heap-buffer-overflow
```

**Why:** App code that allocates `Buffer` by value (stack or `new`) uses v1's `sizeof(Buffer)=64+vtable`; v2 writes 128 bytes of `data` — the extra 64 bytes corrupt whatever follows in memory, detected by ASAN as a heap-buffer-overflow.

## How to fix
Use the PIMPL idiom: the public `Buffer` class stores only a pointer to a private
`BufferImpl` struct whose layout can change freely without affecting `sizeof(Buffer)`.

## Real-world example
Qt's "binary compatibility" rule explicitly forbids changing `sizeof` of any public
class. Every Qt class that needs to grow uses a `d_ptr` PIMPL to keep the public
class size constant across minor releases.
