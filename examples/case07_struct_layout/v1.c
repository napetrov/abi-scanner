struct Point { int x; int y; };
int get_x(struct Point *p) { return p->x; }
/* init_point fills all fields of the v1 layout */
void init_point(struct Point *p) { p->x = 1; p->y = 2; }
