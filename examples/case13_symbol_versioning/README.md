# Case 13: Symbol Versioning Script

**Category:** ELF/Linker | **Verdict:** 🟡 INFORMATIONAL

## What breaks
Without a version script, symbols have no version tag. If you later need to ship a
`LIBFOO_2.0` variant of a symbol (for ABI fix while keeping backward compat), you
have no mechanism to do so — all consumers already link against the unversioned symbol
and there's no way to differentiate.

## Why the check catches it
`readelf --syms` on the "good" library shows `foo@@LIBFOO_1.0` — the `@@` denotes the
default (current) version. The "bad" library shows bare `foo` with no version suffix.

## Build comparison

| good.c + libfoo.map | bad.c (no map) |
|---|---|
| `gcc ... -Wl,--version-script=libfoo.map` | `gcc -shared -fPIC bad.c -o libbad.so` |
| `readelf --syms` → `foo@@LIBFOO_1.0` | `readelf --syms` → `foo` |

## Reproduce manually
```bash
# good
gcc -shared -fPIC good.c -o libgood.so -Wl,--version-script=libfoo.map
readelf --syms libgood.so | grep foo   # → foo@@LIBFOO_1.0

# bad
gcc -shared -fPIC bad.c -o libbad.so
readelf --syms libbad.so | grep foo    # → foo (no version)
```

`libfoo.map` content:
```
LIBFOO_1.0 {
  global: foo; bar;
  local: *;
};
```

## Real Failure Demo

**Severity: INFORMATIONAL**

**Scenario:** build `app` against versioned `good.so`, then try to run it with unversioned `bad.so`.

```bash
# Step 1: build good.so with version script and link app
gcc -shared -fPIC -g good.c -Wl,--version-script=libfoo.map -o libfoo.so
gcc -g app.c -L. -lfoo -Wl,-rpath,. -o app
./app
# Output:
# foo() = 0
# bar() = 1
# OK — symbol versioning is a deployment/compat tooling concern, not a crash

# Inspect versioned symbols
readelf --syms libfoo.so | grep -E 'foo|bar'
# Output: foo@@LIBFOO_1.0   bar@@LIBFOO_1.0

# Step 2: swap in bad.so (no version script, no recompile)
gcc -shared -fPIC -g bad.c -o libfoo.so
./app 2>&1 || true
# Output:
# ./app: ./libfoo.so: no version information available (required by ./app)
# Inconsistency detected by ld.so: ... Assertion failed!

# Inspect unversioned symbols
readelf --syms libfoo.so | grep -E 'foo|bar'
# Output: foo   bar   (bare, no version tag)
```

**Why:** Without symbol versioning, there is no mechanism to ship a `LIBFOO_2.0` compat fix alongside `LIBFOO_1.0`; apps linked against the versioned library hard-fail when the version information disappears from the `.so`.

## How to fix
Always supply a linker version script for public libraries. This enables future
`LIBFOO_2.0` blocks for compatible evolution and precise control over the public
symbol set.

## Real-world example
glibc uses symbol versioning extensively — `GLIBC_2.5`, `GLIBC_2.17`, etc. — allowing
the same `libc.so.6` to serve binaries built against many different historical versions
simultaneously.
