#include <stdio.h>
#include <stdbool.h>
#include <string.h>
#include <unistd.h>

#include <sys/uio.h>

#include <pthread.h>
#include <semaphore.h>

#include "common.h"
#include "strace.h"

struct console {
    unsigned long count;
    char buffer[0];
};

static struct console *console;

static char *ledger;
static pthread_spinlock_t ledger_lock;

// missing declarations
struct linux_dirent {
    unsigned long d_ino;
    unsigned long d_off;
    unsigned short d_reclen;
    char d_name[];
};

struct linux_dirent64 {
    unsigned long d_ino;
    unsigned long d_off;
    unsigned short d_reclen;
    unsigned char d_type;
    char d_name[];
};

// printing primitives
static inline int _util_print_nullptr_check(char *buf, long val) {
    if (val == 0) {
        return sprintf(buf, "<null>");
    }
    return 0;
}

static inline int _print_ptr_hex(char *buf, long val) {
    return sprintf(buf, "[0x%lx]", val);
}

static inline int _print_int_hex(char *buf, long val) {
    return sprintf(buf, "0x%lx", val);
}

static inline int _print_int_oct(char *buf, long val) {
    return sprintf(buf, "0%lo", val);
}

static inline int _print_int_signed(char *buf, long val) {
    return sprintf(buf, "%ld", val);
}

static inline int _print_int_unsigned(char *buf, long val) {
    return sprintf(buf, "%lu", val);
}

static inline int _print_ref_int_signed(char *buf, long val) {
    int len = _util_print_nullptr_check(buf, val);
    if (len) {
        return len;
    }

    return _print_int_signed(buf, *(long *) val);
}

static inline int _print_ref_int_unsigned(char *buf, long val) {
    int len = _util_print_nullptr_check(buf, val);
    if (len) {
        return len;
    }

    return _print_int_unsigned(buf, *(long *) val);
}

static inline int _print_fd(char *buf, long val) {
    return sprintf(buf, "<fd: %d>", (int) val);
}

static inline int _print_str(char *buf, long val) {
    int len = _util_print_nullptr_check(buf, val);
    if (len) {
        return len;
    }

    return sprintf(buf, "%.64s", (char *) val);
}

static inline int _print_buf(char *buf, long val) {
    int len = _util_print_nullptr_check(buf, val);
    if (len) {
        return len;
    }

    return sprintf(buf, "[...buf...]");
}

static inline int _print_struct_stat(char *buf, long val) {
    int len = _util_print_nullptr_check(buf, val);
    if (len) {
        return len;
    }

    struct stat *statbuf = (struct stat *) val;
    return sprintf(buf, "{ino=%ld, size=%ld, nlink=%ld, ...}",
                   statbuf->st_ino, statbuf->st_size, statbuf->st_nlink);
}

static inline int _print_struct_linux_dirent(char *buf, long val) {
    int len = _util_print_nullptr_check(buf, val);
    if (len) {
        return len;
    }

    struct linux_dirent *dirent = (struct linux_dirent *) val;
    return sprintf(buf, "{d_ino=%ld, d_off=%ld, ...}",
                   dirent->d_ino, dirent->d_off);
}

static inline int _print_struct_linux_dirent64(char *buf, long val) {
    int len = _util_print_nullptr_check(buf, val);
    if (len) {
        return len;
    }

    struct linux_dirent64 *dirent = (struct linux_dirent64 *) val;
    return sprintf(buf, "{d_ino=%ld, d_off=%ld, ...}",
                   dirent->d_ino, dirent->d_off);
}

static inline int _print_vector_struct_iovec(char *buf, long val) {
    int len = _util_print_nullptr_check(buf, val);
    if (len) {
        return len;
    }

    struct iovec *iov = (struct iovec *) val;
    return sprintf(buf, "[{iov_base=0x%p, iov_len=%ld}, ,..]",
                   iov->iov_base, iov->iov_len);
}

// auto-generated print functions
static inline int gettid(void) {
    return syscall(__NR_gettid);
}

#define _STRACE_ARG_DEF(A, P) , long A
#define _STRACE_ARG_USE(A, P) \
        buf += _print_##P(buf, A); \
        buf += sprintf(buf, ", ");

#define STRACE(name, pret, ...) \
        static void strace_##name( \
                const char *tokn, long retv \
                VARDEF2(_STRACE_ARG_DEF, , ##__VA_ARGS__) \
        ) { \
            char msg[1024]; \
            char *buf = msg; \
            buf += sprintf(buf, "[strace:%4d] %s " #name "(", gettid(), tokn); \
            VARDEF2(_STRACE_ARG_USE, , ##__VA_ARGS__) \
            buf += sprintf(buf, ") = <ret: "); \
            buf += _print_##pret(buf, retv); \
            buf += sprintf(buf, ">\n"); \
            size_t len = buf - msg; \
            if (len >= sizeof(msg)) { \
                panic(0, "strace entry exceeds size limit", NULL); \
            } \
            char *entry; \
            pthread_spin_lock(&ledger_lock); \
            entry = ledger; \
            ledger += len; \
            console->count += len; \
            pthread_spin_unlock(&ledger_lock); \
            memcpy(entry, msg, len); \
        }

// default strace functions
STRACE(unknown_0, int_hex)
STRACE(unknown_1, int_hex,
       arg0, int_hex)
STRACE(unknown_2, int_hex,
       arg0, int_hex,
       arg1, int_hex)
STRACE(unknown_3, int_hex,
       arg0, int_hex,
       arg1, int_hex,
       arg2, int_hex)
STRACE(unknown_4, int_hex,
       arg0, int_hex,
       arg1, int_hex,
       arg2, int_hex,
       arg3, int_hex)
STRACE(unknown_5, int_hex,
       arg0, int_hex,
       arg1, int_hex,
       arg2, int_hex,
       arg3, int_hex,
       arg4, int_hex)
STRACE(unknown_6, int_hex,
       arg0, int_hex,
       arg1, int_hex,
       arg2, int_hex,
       arg3, int_hex,
       arg4, int_hex,
       arg5, int_hex)

// holder of code pointers
STRACE_HANDLE_DEFINE(0);
STRACE_HANDLE_DEFINE(1);
STRACE_HANDLE_DEFINE(2);
STRACE_HANDLE_DEFINE(3);
STRACE_HANDLE_DEFINE(4);
STRACE_HANDLE_DEFINE(5);
STRACE_HANDLE_DEFINE(6);

STRACE(open, int_signed,
       path, str,
       flags, int_hex,
       modes, int_oct)

STRACE(openat, int_signed,
       dirfd, fd,
       path, str,
       flags, int_hex,
       modes, int_oct)

STRACE(creat, int_signed,
       path, str,
       modes, int_oct)

STRACE(close, int_signed,
       fd, fd)

STRACE(mkdir, int_signed,
       path, str,
       modes, int_oct)

STRACE(mkdirat, int_signed,
       dirfd, fd,
       path, str,
       modes, int_oct)

STRACE(mknod, int_signed,
       path, str,
       modes, int_oct,
       dev, int_hex)

STRACE(read, int_signed,
       fd, fd,
       buffer, buf,
       count, int_signed)

STRACE(readv, int_signed,
       fd, fd,
       iov, vector_struct_iovec,
       iovcnt, int_signed)

STRACE(pread64, int_signed,
       fd, fd,
       buffer, buf,
       count, int_signed,
       offset, int_signed)

STRACE(write, int_signed,
       fd, fd,
       buffer, buf,
       count, int_signed)

STRACE(writev, int_signed,
       fd, fd,
       iov, vector_struct_iovec,
       iovcnt, int_signed)

STRACE(pwrite64, int_signed,
       fd, fd,
       buffer, buf,
       count, int_signed,
       offset, int_signed)

STRACE(lseek, int_signed,
       fd, fd,
       offset, int_signed,
       whence, int_signed)

STRACE(truncate, int_signed,
       path, str,
       offset, int_signed)

STRACE(ftruncate, int_signed,
       fd, fd,
       offset, int_signed)

STRACE(fallocate, int_signed,
       fd, fd,
       mode, int_hex,
       offset, int_signed,
       count, int_signed)

STRACE(getdents, int_signed,
       fd, fd,
       dirent, struct_linux_dirent,
       count, int_signed)

STRACE(getdents64, int_signed,
       fd, fd,
       dirent, struct_linux_dirent64,
       count, int_signed)

STRACE(readlink, int_signed,
       path, str,
       link, str,
       count, int_signed)

STRACE(readlinkat, int_signed,
       dirfd, fd,
       path, str,
       link, str,
       count, int_signed)

STRACE(access, int_signed,
       path, str,
       modes, int_oct)

STRACE(faccessat, int_signed,
       dirfd, fd,
       path, str,
       modes, int_oct,
       flags, int_hex)

STRACE(stat, int_signed,
       path, str,
       statbuf, struct_stat)

STRACE(lstat, int_signed,
       path, str,
       statbuf, struct_stat)

STRACE(fstat, int_signed,
       fd, fd,
       statbuf, struct_stat)

STRACE(newfstatat, int_signed,
       dirfd, fd,
       path, str,
       statbuf, struct_stat,
       flags, int_hex)

STRACE(chmod, int_signed,
       path, str,
       mode, int_oct)

STRACE(fchmod, int_signed,
       fd, fd,
       modes, int_oct)

STRACE(fchmodat, int_signed,
       dirfd, fd,
       path, str,
       modes, int_oct,
       flags, int_hex)

STRACE(link, int_signed,
       oldpath, str,
       newpath, str)

STRACE(linkat, int_signed,
       olddirfd, fd,
       oldpath, str,
       newdirfd, fd,
       newpath, str,
       flags, int_hex)

STRACE(symlink, int_signed,
       oldpath, str,
       newpath, str)

STRACE(symlinkat, int_signed,
       oldpath, str,
       newdirfd, fd,
       newpath, str)

STRACE(unlink, int_signed,
       path, str)

STRACE(unlinkat, int_signed,
       dirfd, fd,
       path, str,
       flags, int_hex)

STRACE(rmdir, int_signed,
       path, str)

STRACE(rename, int_signed,
       oldpath, str,
       newpath, str)

STRACE(renameat2, int_signed,
       olddirfd, fd,
       oldpath, str,
       newdirfd, fd,
       newpath, str,
       flags, int_hex)

STRACE(dup, int_signed,
       oldfd, fd)

STRACE(dup2, int_signed,
       oldfd, fd,
       newfd, fd)

STRACE(dup3, int_signed,
       oldfd, fd,
       newfd, fd,
       flags, int_hex)

STRACE(splice, int_signed,
       fdin, fd,
       offin, ref_int_signed,
       fdout, fd,
       offout, ref_int_signed,
       flags, int_hex)

STRACE(sendfile, int_signed,
       fdout, fd,
       fdin, fd,
       offset, ref_int_signed,
       count, int_signed)

STRACE(fsync, int_signed,
       fd, fd)

STRACE(fdatasync, int_signed,
       fd, fd)

STRACE(syncfs, int_signed,
       fd, fd)

STRACE(sync_file_range, int_signed,
       fd, fd,
       offset, int_signed,
       count, int_signed,
       flags, int_hex)

STRACE(fadvise64, int_signed,
       fd, fd,
       offset, int_signed,
       count, int_signed,
       advice, int_hex)

STRACE(readahead, int_signed,
       fd, fd,
       offset, int_signed,
       count, int_signed)

// init
void strace_init(void) {
    // find the location of the ledger
    console = (struct console *) ((char *) g_shmem + IVSHMEM_OFFSET_STRACE);

    // reset the count
    console->count = 0;
    ledger = console->buffer;

    // initialize the spin lock
    pthread_spin_init(&ledger_lock, 0);

    // assign strace with default pointers
    for (int i = 0; i < STRACE_SYSCALL_NUM_MAX; i++) {
#define STRACE_HANDLE_DEFAULT(n) STRACE_HANDLES_##n[i] = strace_unknown_##n

        STRACE_HANDLE_DEFAULT(0);
        STRACE_HANDLE_DEFAULT(1);
        STRACE_HANDLE_DEFAULT(2);
        STRACE_HANDLE_DEFAULT(3);
        STRACE_HANDLE_DEFAULT(4);
        STRACE_HANDLE_DEFAULT(5);
        STRACE_HANDLE_DEFAULT(6);
    }

    // add hand-written handlers
#define STRACE_HANDLE_ASSIGN(name, n) \
        STRACE_HANDLES_##n[__NR_##name] = strace_##name

    STRACE_HANDLE_ASSIGN(open, 3);
    STRACE_HANDLE_ASSIGN(openat, 4);
    STRACE_HANDLE_ASSIGN(creat, 2);
    STRACE_HANDLE_ASSIGN(close, 1);

    STRACE_HANDLE_ASSIGN(mkdir, 2);
    STRACE_HANDLE_ASSIGN(mkdirat, 3);
    STRACE_HANDLE_ASSIGN(mknod, 3);

    STRACE_HANDLE_ASSIGN(read, 3);
    STRACE_HANDLE_ASSIGN(readv, 3);
    STRACE_HANDLE_ASSIGN(pread64, 4);

    STRACE_HANDLE_ASSIGN(write, 3);
    STRACE_HANDLE_ASSIGN(writev, 3);
    STRACE_HANDLE_ASSIGN(pwrite64, 4);

    STRACE_HANDLE_ASSIGN(lseek, 3);
    STRACE_HANDLE_ASSIGN(truncate, 2);
    STRACE_HANDLE_ASSIGN(ftruncate, 2);
    STRACE_HANDLE_ASSIGN(fallocate, 4);

    STRACE_HANDLE_ASSIGN(getdents, 3);
    STRACE_HANDLE_ASSIGN(getdents64, 3);

    STRACE_HANDLE_ASSIGN(readlink, 3);
    STRACE_HANDLE_ASSIGN(readlinkat, 4);

    STRACE_HANDLE_ASSIGN(access, 2);
    STRACE_HANDLE_ASSIGN(faccessat, 4);

    STRACE_HANDLE_ASSIGN(stat, 2);
    STRACE_HANDLE_ASSIGN(lstat, 2);
    STRACE_HANDLE_ASSIGN(fstat, 2);
    STRACE_HANDLE_ASSIGN(newfstatat, 4);

    STRACE_HANDLE_ASSIGN(chmod, 2);
    STRACE_HANDLE_ASSIGN(fchmod, 2);
    STRACE_HANDLE_ASSIGN(fchmodat, 4);

    STRACE_HANDLE_ASSIGN(link, 2);
    STRACE_HANDLE_ASSIGN(linkat, 5);
    STRACE_HANDLE_ASSIGN(symlink, 2);
    STRACE_HANDLE_ASSIGN(symlinkat, 3);

    STRACE_HANDLE_ASSIGN(unlink, 1);
    STRACE_HANDLE_ASSIGN(unlinkat, 3);
    STRACE_HANDLE_ASSIGN(rmdir, 1);

    STRACE_HANDLE_ASSIGN(rename, 2);
    STRACE_HANDLE_ASSIGN(renameat2, 5);

    STRACE_HANDLE_ASSIGN(dup, 1);
    STRACE_HANDLE_ASSIGN(dup2, 2);
    STRACE_HANDLE_ASSIGN(dup3, 3);

    STRACE_HANDLE_ASSIGN(splice, 5);
    STRACE_HANDLE_ASSIGN(sendfile, 4);

    STRACE_HANDLE_ASSIGN(fsync, 1);
    STRACE_HANDLE_ASSIGN(fdatasync, 1);
    STRACE_HANDLE_ASSIGN(syncfs, 1);
    STRACE_HANDLE_ASSIGN(sync_file_range, 4);

    STRACE_HANDLE_ASSIGN(fadvise64, 4);
    STRACE_HANDLE_ASSIGN(readahead, 3);
}