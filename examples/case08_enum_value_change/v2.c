/* YELLOW inserted at 1 — shifts GREEN and BLUE */
typedef enum { RED=0, YELLOW=1, GREEN=2, BLUE=3 } Color;
Color get_color(void) { return RED; }
/* get_signal still returns "GREEN" — but GREEN is now value 2 */
Color get_signal(void) { return GREEN; }
