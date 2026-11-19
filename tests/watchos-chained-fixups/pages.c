#include <stdint.h>

/* Pointers spread over several 16 KiB pages of __DATA: runs 124 bytes apart (the
 * longest link a 32-bit chain can make), runs 128 bytes apart (one start each, so
 * pages with many starts in the overflow list), and pointers on both sides of page
 * boundaries. */
static int t0, t1, t2;

struct near { void *p; uint32_t pad[30]; };   /* 124 bytes between pointers */
struct far { void *p; uint32_t pad[31]; };    /* 128 bytes between pointers */

#define N4(x) x, x, x, x
#define N16(x) N4(x), N4(x), N4(x), N4(x)
#define N64(x) N16(x), N16(x), N16(x), N16(x)
#define N256(x) N64(x), N64(x), N64(x), N64(x)

struct near near_run[256] = { N256({ &t0 }) };
struct far far_run[256] = { N256({ &t1 }) };
uint32_t gap[3000] = { 1 };
void *tail[8] = { &t0, &t1, &t2, &t0, &t1, &t2, &t0, &t1 };

int main(void) {
  return near_run[255].p == far_run[255].p && tail[7] == 0 && gap[0];
}
