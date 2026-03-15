#include <dlfcn.h>
#include <stdio.h>

int main(void) {
    /* Check bad.so — internal_helper accidentally exported */
    void *lib = dlopen("./libbad.so", RTLD_NOW);
    if (!lib) { fprintf(stderr, "dlopen libbad.so: %s\n", dlerror()); return 1; }
    int (*fn)(int) = (int (*)(int))dlsym(lib, "internal_helper");
    if (fn)
        printf("libbad.so:  internal_helper(3) = %d  <-- LEAKED (should be private!)\n", fn(3));
    else
        printf("libbad.so:  internal_helper not accessible (correct)\n");
    dlclose(lib);

    /* Check good.so — internal_helper properly hidden */
    lib = dlopen("./libgood.so", RTLD_NOW);
    if (!lib) { fprintf(stderr, "dlopen libgood.so: %s\n", dlerror()); return 1; }
    fn = (int (*)(int))dlsym(lib, "internal_helper");
    if (fn)
        printf("libgood.so: internal_helper accessible — BUG!\n");
    else
        printf("libgood.so: internal_helper not accessible (correct)\n");
    dlclose(lib);

    return 0;
}
