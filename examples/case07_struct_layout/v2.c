/* added field 'z' — layout change, callers pass wrong-sized structs */
struct Point { int x; int y; int z; };
int get_x(struct Point *p) { return p->x; }
/* v2 init_point writes z=3 beyond the v1-sized allocation */
void init_point(struct Point *p) { p->x = 1; p->y = 2; p->z = 3; }
