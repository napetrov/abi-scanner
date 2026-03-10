# Case 05: Missing SONAME

**Risk:** 🟡 BAD PRACTICE | **Category:** ELF/Linker | **Verdict:** 🟡 INFORMATIONAL

## What breaks
Without a SONAME, the dynamic linker records the bare filename (`libfoo.so`) in
`DT_NEEDED` entries of every consumer. If you later ship `libfoo.so.1`, existing
binaries won't find it. SONAME is how Linux implements library versioning.

## Why the check catches it
`readelf -d` on a well-built library shows `(SONAME) Library soname: [libfoo.so.1]`.
Its absence means the library was linked without `-Wl,-soname`.

## Build comparison

| good.c (with SONAME) | bad.c (without) |
|---|---|
| `gcc -shared -fPIC good.c -o libfoo.so -Wl,-soname,libfoo.so.1` | `gcc -shared -fPIC bad.c -o libfoo.so` |
| `readelf -d` → `(SONAME) libfoo.so.1` | `readelf -d` → *(no SONAME entry)* |

## Reproduce manually
```bash
gcc -shared -fPIC good.c -o libgood.so -Wl,-soname,libfoo.so.1
gcc -shared -fPIC bad.c  -o libbad.so
readelf -d libgood.so | grep SONAME   # → present
readelf -d libbad.so  | grep SONAME   # → empty
```

## Real Failure Demo

**Severity: BAD PRACTICE**

**Scenario:** build `app` against `bad.so` (no SONAME) vs `good.so` (with SONAME); observe the packaging/linker difference.

```bash
# Build both libraries
gcc -shared -fPIC -g good.c -o libgood.so -Wl,-soname,libfoo.so.1
gcc -shared -fPIC -g bad.c  -o libbad.so

# Check SONAME presence
readelf -d libgood.so | grep SONAME
# Output: 0x000000000000000e (SONAME)  Library soname: [libfoo.so.1]
readelf -d libbad.so  | grep SONAME
# Output: (nothing)

# Build app against bad.so — runtime works fine...
gcc -shared -fPIC -g bad.c -o libfoo.so
gcc -g app.c -L. -lfoo -Wl,-rpath,. -o app
./app
# Output:
# foo() = 0
# Runtime: OK — SONAME issue is a packaging/install problem, not a crash

# The failure is in ldconfig: without SONAME, ldconfig won't create the
# libfoo.so.1 → libfoo.so symlink. Any binary that links against -lfoo
# looking for libfoo.so.1 will fail at runtime even though the .so exists.
ldconfig -p | grep libfoo   # libgood.so appears with soname; libbad.so does not
```

**Why:** Missing SONAME means `ldconfig` cannot create versioned symlinks (`libfoo.so.1`), so system package managers and `ld.so` cannot find the library by its versioned name — this breaks system-level library management without crashing the app directly.

## How to fix
Always pass `-Wl,-soname,libname.so.MAJOR` when building a shared library intended
for system installation.

## Real-world example
Many in-tree/vendored libraries built with simple `Makefile`s omit SONAME. Debian
packaging policy enforces SONAME presence and will reject packages without it.
