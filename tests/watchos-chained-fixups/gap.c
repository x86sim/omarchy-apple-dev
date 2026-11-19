#include <stdio.h>
#include <stdint.h>

extern int puts(const char *);
static int target_a, target_b, target_c;

/* Two pointers 200 bytes apart, small values in between: dyld can chain through a filler. */
struct small_gap { void *p1; uint32_t pad[50]; void *p2; };
struct small_gap sg = { &target_a, {1, 2, 3}, &target_b };

/* Pointers 200 bytes apart with only large values (floats, all-ones) in between. */
struct big_gap { void *p1; uint32_t pad[50]; void *p2; };
struct big_gap bg = { &target_a,
  { 0x3f800000, 0x3f800000, 0x3f800000, 0x3f800000, 0x3f800000, 0x3f800000, 0x3f800000, 0x3f800000,
    0x3f800000, 0x3f800000, 0x3f800000, 0x3f800000, 0x3f800000, 0x3f800000, 0x3f800000, 0x3f800000,
    0x3f800000, 0x3f800000, 0x3f800000, 0x3f800000, 0x3f800000, 0x3f800000, 0x3f800000, 0x3f800000,
    0x3f800000, 0x3f800000, 0x3f800000, 0x3f800000, 0x3f800000, 0x3f800000, 0x3f800000, 0x3f800000,
    0xffffffff, 0xffffffff, 0xffffffff, 0xffffffff, 0xffffffff, 0xffffffff, 0xffffffff, 0xffffffff,
    0xffffffff, 0xffffffff, 0xffffffff, 0xffffffff, 0xffffffff, 0xffffffff, 0xffffffff, 0xffffffff,
    0xffffffff, 0xffffffff }, &target_c };

/* Imports with addends: inline (<= 63) and larger. */
void *bind_small = (char *)&puts + 8;
void *bind_large = (char *)&puts + 200;
void *bind_neg = (char *)&puts - 4;

int main(void) {
  printf("%p %p %p %p %p\n", sg.p2, bg.p2, bind_small, bind_large, bind_neg);
  return 0;
}
