#include <stdio.h>

/* App compiled against v1 enum values: RED=0, GREEN=1, BLUE=2 */
typedef enum { RED=0, GREEN=1, BLUE=2 } Color;

extern Color get_color(void);
extern Color get_signal(void);

static const char *color_name(Color c) {
    switch (c) {
        case 0: return "RED";
        case 1: return "GREEN";
        case 2: return "BLUE";
        default: return "UNKNOWN";
    }
}

int main(void) {
    Color c = get_color();
    printf("get_color() = %d → %s\n", (int)c, color_name(c));

    Color sig = get_signal();
    printf("get_signal() = %d → app interprets as: %s\n", (int)sig, color_name(sig));

    /* v1: get_signal()=1 → GREEN ✓
       v2: get_signal()=2 (GREEN in v2 enum) → app reads as BLUE ✗ */
    if (sig == GREEN)
        printf("Signal: GREEN (correct)\n");
    else if (sig == BLUE)
        printf("Signal: BLUE — WRONG! v2 shifted enum values, GREEN(2) looks like BLUE\n");
    else
        printf("Signal: %d — unexpected\n", (int)sig);

    return 0;
}
