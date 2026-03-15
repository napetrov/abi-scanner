"""Integration tests for ABI scenarios using real compiled .so fixtures.

See ``examples/README.md`` for the human-readable catalog of all 14 scenarios,
with build instructions, code diffs, and explanations of what each case catches.

Test structure
--------------
* Cases 1-4, 7-8, 10-12 are parametrized through ``test_abi_verdict`` (C sources).
* Cases 9, 14 are parametrized through ``test_abi_verdict_cpp`` (C++ sources).
* Cases 5, 6, 13 are informational ELF/linker checks (@pytest.mark.informational).

abidiff exit-code reference (libabigail 2.4.0)
-----------------------------------------------
  0  — NO_CHANGE
  4  — ABI change detected (type/layout diff or addition); classified by stdout
       as COMPATIBLE (addition only) or INCOMPATIBLE (type/layout/vtable change).
  12 — BREAKING change (symbol removed).
"""
import subprocess
from pathlib import Path

import pytest

from abi_scanner.analyzer import ABIVerdict
from abi_helpers import (
    compile_so,
    compile_so_cpp,
    make_abi_baseline,
    compare_abi,
    classify_abi_change,
    examples_dir,
)


# ── Inline source fixtures ────────────────────────────────────────────────────

SOURCES_C = {
    # Case 1 — symbol removal
    "c1_v1": "int compute(int x) { return x * 2; }\nint helper(int x)  { return x + 1; }\n",
    "c1_v2": "int compute(int x) { return x * 2; }\n",
    # Case 2 — param type change
    "c2_v1": "double process(int a, int b) { return (double)(a + b); }\n",
    "c2_v2": "double process(double a, int b) { return a + b; }\n",
    # Case 3 — compatible addition
    "c3_v1": "int get_version(void) { return 1; }\n",
    "c3_v2": "int get_version(void) { return 1; }\nint get_build(void) { return 42; }\n",
    # Case 4 — no change
    "c4_v1": "int stable_api(int x) { return x; }\n",
    # Case 5 — soname
    "c5":    "int foo(void) { return 0; }\n",
    # Case 6 — visibility
    "c6_good": (
        '__attribute__((visibility("default"))) int public_api(int x) { return x; }\n'
        'int internal_helper(int x) { return x * 2; }\n'  # no static, hidden only by -fvisibility=hidden
    ),
    "c6_bad": (
        "int public_api(int x)      { return x; }\n"
        "int internal_helper(int x) { return x * 2; }\n"
        "int another_impl(int x)    { return x + 3; }\n"
    ),
    # Case 7 — struct layout
    "c7_v1": "struct Point { int x; int y; };\nint get_x(struct Point *p) { return p->x; }\n",
    "c7_v2": "struct Point { int x; int y; int z; };\nint get_x(struct Point *p) { return p->x; }\n",
    # Case 8 — enum value change
    "c8_v1": "typedef enum { RED=0, GREEN=1, BLUE=2 } Color;\nColor get_color(void) { return RED; }\n",
    "c8_v2": "typedef enum { RED=0, YELLOW=1, GREEN=2, BLUE=3 } Color;\nColor get_color(void) { return RED; }\n",
    # Case 10 — return type
    "c10_v1": "int  get_count(void) { return 42; }\n",
    "c10_v2": "long get_count(void) { return 42; }\n",
    # Case 11 — global var type
    "c11_v1": "int  lib_version = 1;\n",
    "c11_v2": "long lib_version = 1;\n",
    # Case 12 — function removed (symbol disappears entirely)
    "c12_v1": "int fast_add(int a, int b) { return a + b; }\n",
    "c12_v2": "int other_func(int x) { return x; }\n",
    # Case 13 — symbol versioning
    "c13": "int foo(void) { return 0; }\nint bar(void) { return 1; }\n",
}

SOURCES_CPP = {
    # Case 9 — vtable change
    "c9_v1": (
        "class Widget {\npublic:\n"
        "    virtual int draw();\n"
        "    virtual int resize();\n"
        "};\n"
        "int Widget::draw()   { return 0; }\n"
        "int Widget::resize() { return 0; }\n"
    ),
    "c9_v2": (
        "class Widget {\npublic:\n"
        "    virtual int draw();\n"
        "    virtual int recolor();\n"
        "    virtual int resize();\n"
        "};\n"
        "int Widget::draw()    { return 0; }\n"
        "int Widget::recolor() { return 0; }\n"
        "int Widget::resize()  { return 0; }\n"
    ),
    # Case 14 — class size change
    "c14_v1": (
        'class Buffer {\npublic:\n    int size() { return 64; }\n'
        'private:\n    char data[64];\n};\n'
        'extern "C" Buffer* make_buffer() { return new Buffer(); }\n'
    ),
    "c14_v2": (
        'class Buffer {\npublic:\n    int size() { return 128; }\n'
        'private:\n    char data[128];\n};\n'
        'extern "C" Buffer* make_buffer() { return new Buffer(); }\n'
    ),
}

VERSION_MAP_CONTENT = "LIBFOO_1.0 {\n  global: foo; bar;\n  local: *;\n};\n"


def _write_c(tmp_path, key):
    p = tmp_path / f"{key}.c"
    p.write_text(SOURCES_C[key])
    return p


def _write_cpp(tmp_path, key):
    p = tmp_path / f"{key}.cpp"
    p.write_text(SOURCES_CPP[key])
    return p


def _run_abi_check(tmp_path, so1, so2):
    xml1, xml2 = tmp_path / "v1.xml", tmp_path / "v2.xml"
    make_abi_baseline(so1, xml1)
    make_abi_baseline(so2, xml2)
    exit_code, stdout = compare_abi(xml1, xml2)
    actual_verdict = classify_abi_change(exit_code, stdout)
    return exit_code, actual_verdict, stdout


# ── Parametrized C verdict tests (cases 1-4, 7-8, 10-12) ─────────────────────
#
# abidiff 2.4.0 exit codes:
#   12 → symbol removed (cases 1, 12)
#    4 → type/layout/addition change (cases 2, 3, 7, 8, 10, 11)
#    0 → no change (case 4)
# classify_abi_change() further splits exit=4 into COMPATIBLE vs INCOMPATIBLE.

C_ABI_CASES = [
    pytest.param("c1_v1",  "c1_v2",  12, ABIVerdict.BREAKING,     id="case01_symbol_removal"),
    pytest.param("c2_v1",  "c2_v2",   4, ABIVerdict.INCOMPATIBLE, id="case02_param_type_change"),
    pytest.param("c3_v1",  "c3_v2",   4, ABIVerdict.COMPATIBLE,   id="case03_compat_addition"),
    pytest.param("c4_v1",  "c4_v1",   0, ABIVerdict.NO_CHANGE,    id="case04_no_change"),
    pytest.param("c7_v1",  "c7_v2",   4, ABIVerdict.INCOMPATIBLE, id="case07_struct_layout"),
    pytest.param("c8_v1",  "c8_v2",   4, ABIVerdict.INCOMPATIBLE, id="case08_enum_value_change"),
    pytest.param("c10_v1", "c10_v2",  4, ABIVerdict.INCOMPATIBLE, id="case10_return_type"),
    pytest.param("c11_v1", "c11_v2",  4, ABIVerdict.INCOMPATIBLE, id="case11_global_var_type"),
    pytest.param("c12_v1", "c12_v2", 12, ABIVerdict.BREAKING,     id="case12_function_removed"),
]


@pytest.mark.parametrize("src_v1,src_v2,expected_exit,expected_verdict", C_ABI_CASES)
def test_abi_verdict(tmp_path, src_v1, src_v2, expected_exit, expected_verdict):
    """Compile v1/v2 C shared libs and verify abidiff exit code and verdict.

    Covers symbol removal (exit 12), type/layout changes classified as
    INCOMPATIBLE (exit 4 + breaking keywords), compatible additions (exit 4,
    no breaking keywords), and no-change baseline (exit 0).
    See examples/README.md for full scenario descriptions.
    """
    so1 = compile_so(_write_c(tmp_path, src_v1), tmp_path / "libv1.so")
    so2 = compile_so(_write_c(tmp_path, src_v2), tmp_path / "libv2.so")
    exit_code, actual_verdict, stdout = _run_abi_check(tmp_path, so1, so2)

    assert exit_code == expected_exit, (
        f"Expected exit {expected_exit}, got {exit_code}.\n{stdout}"
    )
    assert actual_verdict == expected_verdict, (
        f"Expected {expected_verdict}, got {actual_verdict}.\nabidiff stdout:\n{stdout}"
    )


# ── C++ parametrized verdict tests (cases 9, 14) ─────────────────────────────

CPP_ABI_CASES = [
    pytest.param("c9_v1",  "c9_v2",  4, ABIVerdict.INCOMPATIBLE, id="case09_cpp_vtable_change"),
    pytest.param("c14_v1", "c14_v2", 4, ABIVerdict.INCOMPATIBLE, id="case14_cpp_class_size_change"),
]


@pytest.mark.parametrize("src_v1,src_v2,expected_exit,expected_verdict", CPP_ABI_CASES)
def test_abi_verdict_cpp(tmp_path, src_v1, src_v2, expected_exit, expected_verdict):
    """Compile v1/v2 C++ shared libs and verify abidiff exit code and verdict.

    Case 09: vtable reordering — abidiff notes "ABI incompatible change to vtable"
    but returns exit 4 (not 12) in libabigail 2.4.0. classify_abi_change() maps
    this to INCOMPATIBLE via the "vtable" keyword.
    Case 14: class sizeof growth — private array doubles; abidiff detects size
    change and returns exit 4. classify_abi_change() maps to INCOMPATIBLE.
    See examples/case09_cpp_vtable/README.md and examples/case14_cpp_class_size/README.md.
    """
    so1 = compile_so_cpp(_write_cpp(tmp_path, src_v1), tmp_path / "libv1.so")
    so2 = compile_so_cpp(_write_cpp(tmp_path, src_v2), tmp_path / "libv2.so")
    exit_code, actual_verdict, stdout = _run_abi_check(tmp_path, so1, so2)

    assert exit_code == expected_exit, (
        f"Expected exit {expected_exit}, got {exit_code}.\n{stdout}"
    )
    assert actual_verdict == expected_verdict, (
        f"Expected {expected_verdict}, got {actual_verdict}.\nabidiff stdout:\n{stdout}"
    )


# ── Case 05: SONAME ────────────────────────────────────────────────────────────

@pytest.mark.informational
def test_soname_detection(tmp_path):
    """Detect missing SONAME tag in ELF dynamic section (case 05).

    A library shipped without -Wl,-soname cannot be versioned by the dynamic
    linker. readelf -d must show (SONAME) for the good build and nothing for bad.
    See examples/case05_soname/README.md.
    """
    src = _write_c(tmp_path, "c5")
    so_good = compile_so(src, tmp_path / "libgood.so", ["-Wl,-soname,libfoo.so.1"])
    so_bad  = compile_so(src, tmp_path / "libbad.so")

    def has_soname(p):
        r = subprocess.run(["readelf", "-d", str(p)], capture_output=True, text=True)
        return "(SONAME)" in r.stdout

    assert has_soname(so_good),    "Good lib must have SONAME tag"
    assert not has_soname(so_bad), "Bad lib must NOT have SONAME tag"


# ── Case 06: Symbol visibility ────────────────────────────────────────────────

@pytest.mark.informational
def test_symbol_visibility_leak(tmp_path):
    """Detect unintended symbol export when -fvisibility=hidden is absent (case 06).

    Without -fvisibility=hidden every internal helper becomes public ABI.
    The good build exports only public_api; the bad build exports all three symbols.
    internal_helper in the good build has no static keyword — it is hidden solely
    by the -fvisibility=hidden compiler flag, which is the correct approach.
    See examples/case06_visibility/README.md.
    """
    so_good = compile_so(_write_c(tmp_path, "c6_good"), tmp_path / "libgood.so",
                         ["-fvisibility=hidden"])
    so_bad  = compile_so(_write_c(tmp_path, "c6_bad"),  tmp_path / "libbad.so")

    def exported(so):
        r = subprocess.run(["nm", "--dynamic", "--defined-only", str(so)],
                           capture_output=True, text=True)
        return [ln.split()[-1] for ln in r.stdout.splitlines()
                if ln.strip() and not ln.split()[-1].startswith("_")]

    good_syms = exported(so_good)
    bad_syms  = exported(so_bad)

    assert "public_api" in good_syms,          f"Good lib must export public_api; got {good_syms}"
    assert "internal_helper" not in good_syms, "Good lib must NOT export internal_helper"
    assert len(bad_syms) > len(good_syms), (
        f"Bad lib ({len(bad_syms)} syms) should export more than good ({len(good_syms)} syms)"
    )


# ── Case 13: Symbol versioning ────────────────────────────────────────────────

@pytest.mark.informational
def test_symbol_versioning(tmp_path):
    """Verify that a linker version script annotates symbols with @@VERSION (case 13).

    Without a version script future SONAME evolution is harder and symbol
    interposition cannot be controlled precisely.
    See examples/case13_symbol_versioning/README.md.
    """
    src = _write_c(tmp_path, "c13")

    map_file = tmp_path / "libfoo.map"
    map_file.write_text(VERSION_MAP_CONTENT)

    so_good = compile_so(src, tmp_path / "libgood.so",
                         [f"-Wl,--version-script={map_file}"])
    so_bad  = compile_so(src, tmp_path / "libbad.so")

    def versioned_syms(so):
        r = subprocess.run(["readelf", "--syms", str(so)],
                           capture_output=True, text=True)
        return [ln for ln in r.stdout.splitlines() if "@@" in ln]

    assert len(versioned_syms(so_good)) > 0, "Good lib must have @@VERSION symbols"
    assert len(versioned_syms(so_bad))  == 0, "Bad lib must NOT have @@VERSION symbols"


# ── FIX 6: Examples catalog smoke test ───────────────────────────────────────

def test_examples_catalog_complete():
    """Verify examples/ directory contains all 14 scenario subdirs."""
    d = examples_dir()
    dirs = sorted(p.name for p in d.iterdir() if p.is_dir())
    assert len(dirs) >= 14, f"Expected 14 case dirs, found {len(dirs)}: {dirs}"


# ── Case 15: noexcept change ──────────────────────────────────────────────────

def test_noexcept_change_symbol_stable(tmp_path):
    """Case 15: noexcept removal doesn't change symbol names on GCC/Clang.

    abidiff misses this; the symbol is present in both .so files unchanged.
    The ABI breakage is semantic (exception-handling assumptions).
    See examples/case15_noexcept_change/README.md.
    """
    src_v1 = tmp_path / "v1.cpp"
    src_v1.write_text("""
class Buffer {
public:
    Buffer();
    ~Buffer();
    void reset() noexcept;
private:
    int* data_;
    int  size_;
};
Buffer::Buffer() : data_(new int[64]), size_(64) {}
Buffer::~Buffer() { delete[] data_; }
void Buffer::reset() noexcept { for (int i=0; i<size_; ++i) data_[i]=0; }
""")
    src_v2 = tmp_path / "v2.cpp"
    src_v2.write_text("""
class Buffer {
public:
    Buffer();
    ~Buffer();
    void reset();   // noexcept removed
private:
    int* data_;
    int  size_;
};
Buffer::Buffer() : data_(new int[64]), size_(64) {}
Buffer::~Buffer() { delete[] data_; }
void Buffer::reset() { for (int i=0; i<size_; ++i) data_[i]=0; }
""")

    so_v1 = compile_so(src_v1, tmp_path / "libv1.so", extra_flags=["-std=c++17", "-g"])
    so_v2 = compile_so(src_v2, tmp_path / "libv2.so", extra_flags=["-std=c++17", "-g"])

    def has_reset(so):
        r = subprocess.run(["nm", "--dynamic", str(so)],
                           capture_output=True, text=True)
        return any("reset" in ln for ln in r.stdout.splitlines())

    # Symbol exists in both versions (noexcept doesn't change mangled name for members)
    assert has_reset(so_v1), "v1 must export reset()"
    assert has_reset(so_v2), "v2 must export reset()"


# ── Case 16: inline → non-inline ─────────────────────────────────────────────

def test_inline_to_non_inline_symbol_appears(tmp_path):
    """Case 16: inline function moving to .so means v1 has NO symbol, v2 has it.

    This demonstrates the ODR hazard: callers with inlined v1 + linked v2 .so
    may have two definitions.
    See examples/case16_inline_to_non_inline/README.md.
    """
    src_v1 = tmp_path / "v1.cpp"
    src_v1.write_text("// empty: fast_hash is header-only inline\n")

    src_v2 = tmp_path / "v2.cpp"
    src_v2.write_text("""
int fast_hash(int x) {
    return (int)((unsigned)x * 2654435761U);
}
""")

    so_v1 = compile_so(src_v1, tmp_path / "libv1.so", extra_flags=["-std=c++17"])
    so_v2 = compile_so(src_v2, tmp_path / "libv2.so", extra_flags=["-std=c++17"])

    def has_fast_hash(so):
        r = subprocess.run(["nm", "--dynamic", "--defined-only", str(so)],
                           capture_output=True, text=True)
        return any("fast_hash" in ln for ln in r.stdout.splitlines())

    assert not has_fast_hash(so_v1), "v1 .so must NOT export fast_hash (it's inline)"
    assert     has_fast_hash(so_v2), "v2 .so must export fast_hash"


# ── Case 17: template layout change ──────────────────────────────────────────

def test_template_abi_sizeof_change(tmp_path):
    """Case 17: explicit template instantiation size change detected via DWARF.

    With -g, abidiff catches the sizeof change. Without -g it misses it.
    See examples/case17_template_abi/README.md.
    """
    src_v1 = tmp_path / "v1.cpp"
    src_v1.write_text("""
#include <cstddef>
template<typename T>
struct Buffer {
    T*          data_;
    std::size_t size_;
    Buffer(std::size_t n) : data_(new T[n]), size_(n) {}
    ~Buffer() { delete[] data_; }
    T* data() { return data_; }
    std::size_t size() const { return size_; }
};
template struct Buffer<int>;
""")

    src_v2 = tmp_path / "v2.cpp"
    src_v2.write_text("""
#include <cstddef>
template<typename T>
struct Buffer {
    T*          data_;
    std::size_t size_;
    std::size_t capacity_;  // NEW field
    Buffer(std::size_t n) : data_(new T[n]), size_(n), capacity_(n) {}
    ~Buffer() { delete[] data_; }
    T* data() { return data_; }
    std::size_t size() const { return size_; }
    std::size_t capacity() const { return capacity_; }
};
template struct Buffer<int>;
""")

    so_v1 = compile_so_cpp(src_v1, tmp_path / "libv1.so", extra_flags=["-std=c++17", "-g"])
    so_v2 = compile_so_cpp(src_v2, tmp_path / "libv2.so", extra_flags=["-std=c++17", "-g"])

    # Both .so files export Buffer<int> constructor
    def has_buffer_int(so):
        r = subprocess.run(["nm", "-C", "--dynamic", str(so)],
                           capture_output=True, text=True)
        return any("Buffer" in ln and "int" in ln for ln in r.stdout.splitlines())

    assert has_buffer_int(so_v1), "v1 must export Buffer<int>"
    assert has_buffer_int(so_v2), "v2 must export Buffer<int>"

    # abidiff with DWARF should report a change
    exit_code, actual_verdict, _stdout = _run_abi_check(tmp_path, so_v1, so_v2)
    assert exit_code != 0, (
        "abidiff should detect Buffer<int> layout change with DWARF present"
    )


# ── Case 18: dependency ABI leak ──────────────────────────────────────────────

def test_dependency_leak_so_identical(tmp_path):
    """Case 18: libfoo .so is identical in both versions; break is in headers.

    This verifies that naive .so comparison misses the dependency ABI leak.
    See examples/case18_dependency_leak/README.md.
    """
    src_v1 = tmp_path / "v1.c"
    src_v1.write_text("""
typedef struct { int x; } ThirdPartyHandle;
void process(ThirdPartyHandle* h) { (void)h; }
int  get_value(const ThirdPartyHandle* h) { return h->x; }
""")

    src_v2 = tmp_path / "v2.c"
    src_v2.write_text("""
typedef struct { int x; int y; } ThirdPartyHandle;
void process(ThirdPartyHandle* h) { (void)h; }
int  get_value(const ThirdPartyHandle* h) { return h->x; }
""")

    so_v1 = compile_so(src_v1, tmp_path / "libv1.so")
    so_v2 = compile_so(src_v2, tmp_path / "libv2.so")

    # Symbol tables should be identical (same function names, no layout in symtab)
    def exported_syms(so):
        r = subprocess.run(["nm", "--dynamic", "--defined-only", str(so)],
                           capture_output=True, text=True)
        return sorted(ln.split()[-1] for ln in r.stdout.splitlines() if ln.strip())

    assert exported_syms(so_v1) == exported_syms(so_v2), (
        "Symbol tables must be identical — dependency leak is invisible at .so level"
    )


# ── Updated smoke test ────────────────────────────────────────────────────────

def test_examples_catalog_complete_18():
    """Verify examples/ directory contains all 18 scenario subdirs."""
    d = examples_dir()
    dirs = sorted(p.name for p in d.iterdir() if p.is_dir())
    assert len(dirs) >= 18, f"Expected 18 case dirs, found {len(dirs)}: {dirs}"
