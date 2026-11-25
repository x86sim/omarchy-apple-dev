/* libSystem functions of macOS that glibc lacks, for the iOS SDK's MSBuild tasks (the rest comes from libc, which
   this library links: dlsym on its handle finds libc's functions too) */
#include <errno.h>
#include <stddef.h>

/* sysctlbyname("sysctl.proc_translated") asks whether Rosetta runs the process: no such name here */
int sysctlbyname(const char *name, void *oldp, size_t *oldlenp, void *newp, size_t newlen) {
	(void)name; (void)oldp; (void)oldlenp; (void)newp; (void)newlen;
	errno = ENOENT;
	return -1;
}

/* stat$INODE64 / lstat$INODE64 / fstat$INODE64: macOS's struct stat (64-bit inodes, 144 bytes) filled from Linux's */
#include <string.h>
#include <stdint.h>
#include <sys/stat.h>

struct darwin_timespec { int64_t tv_sec; int64_t tv_nsec; };
struct darwin_stat {
	int32_t st_dev;
	uint16_t st_mode;
	uint16_t st_nlink;
	uint64_t st_ino;
	uint32_t st_uid;
	uint32_t st_gid;
	int32_t st_rdev;
	int32_t pad;
	struct darwin_timespec st_atimespec, st_mtimespec, st_ctimespec, st_birthtimespec;
	int64_t st_size;
	int64_t st_blocks;
	int32_t st_blksize;
	uint32_t st_flags;
	uint32_t st_gen;
	int32_t st_lspare;
	int64_t st_qspare[2];
};
_Static_assert(sizeof(struct darwin_stat) == 144, "darwin struct stat is 144 bytes");

static void to_darwin(const struct stat *s, struct darwin_stat *d) {
	memset(d, 0, sizeof *d);
	d->st_dev = (int32_t)s->st_dev;
	d->st_mode = (uint16_t)s->st_mode; /* S_IFMT and permission bits have the same values */
	d->st_nlink = (uint16_t)s->st_nlink;
	d->st_ino = s->st_ino;
	d->st_uid = s->st_uid;
	d->st_gid = s->st_gid;
	d->st_rdev = (int32_t)s->st_rdev;
	d->st_atimespec = (struct darwin_timespec){s->st_atim.tv_sec, s->st_atim.tv_nsec};
	d->st_mtimespec = (struct darwin_timespec){s->st_mtim.tv_sec, s->st_mtim.tv_nsec};
	d->st_ctimespec = (struct darwin_timespec){s->st_ctim.tv_sec, s->st_ctim.tv_nsec};
	d->st_birthtimespec = d->st_ctimespec;
	d->st_size = s->st_size;
	d->st_blocks = s->st_blocks;
	d->st_blksize = (int32_t)s->st_blksize;
}

#define SYMNAME_darwin_stat64 "stat$INODE64"
#define SYMNAME_darwin_lstat64 "lstat$INODE64"
#define SYMNAME_darwin_fstat64 "fstat$INODE64"
#define DARWIN_STAT(sym, call, arg_t) \
	int sym(arg_t a, struct darwin_stat *d) __asm__(SYMNAME_##sym); \
	int sym(arg_t a, struct darwin_stat *d) { struct stat s; int r = call(a, &s); if (r == 0) to_darwin(&s, d); return r; }
DARWIN_STAT(darwin_stat64, stat, const char *)
DARWIN_STAT(darwin_lstat64, lstat, const char *)
DARWIN_STAT(darwin_fstat64, fstat, int)
