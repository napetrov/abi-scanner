#include <cstdio>

/* App compiled against v1 vtable layout: [draw=slot0, resize=slot1] */
class Widget {
public:
    virtual int draw();
    virtual int resize();
};

extern "C" Widget* make_widget();

int main() {
    Widget* w = make_widget();

    int d = w->draw();
    int r = w->resize();

    printf("draw()   = %d (expected 10)\n", d);
    printf("resize() = %d (expected 20)\n", r);

    if (r != 20) {
        printf("WRONG: resize() returned %d — vtable slot 1 now points to recolor()!\n", r);
        printf("       v2 vtable: [draw=slot0, recolor=slot1, resize=slot2]\n");
        printf("       App called slot1 expecting resize(20), got recolor(%d)\n", r);
    } else {
        printf("OK — resize() correct\n");
    }

    delete w;
    return 0;
}
