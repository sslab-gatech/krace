#ifndef _RACER_INITRAMFS_COMMON_H_
#define _RACER_INITRAMFS_COMMON_H_

#include <stdlib.h>
#include <stdarg.h>
#include <stdbool.h>
#include <unistd.h>
#include <string.h>
#include <fcntl.h>
#include <errno.h>

#include <sys/types.h>
#include <sys/syscall.h>

#include <vardef.h>

// Not all alternative libc implementations support these constants yet.
#ifndef O_CLOEXEC
#define O_CLOEXEC 02000000
#endif

// structs
struct shmem_hdr {
    char command;
    char desc[7];
    unsigned long status;
};

// constants that may be used by anyone
#define FSSHARE_MNT                 "/host"
#define FS_DISK_IMG                 FSSHARE_MNT "/disk.img"
#define FS_DISK_MNT                 "/work"

#define _MB(i)                      ((i) * (1 << 20))

#define IVSHMEM_OFFSET_METADATA     0
#define IVSHMEM_OFFSET_BYTECODE     IVSHMEM_OFFSET_METADATA + _MB(2)
#define IVSHMEM_OFFSET_STRACE       IVSHMEM_OFFSET_BYTECODE + _MB(48)
#define IVSHMEM_SIZE                IVSHMEM_OFFSET_STRACE + _MB(12)

// init.c
extern void *g_shmem;

// util.c
void set_buf(char *buf, size_t size, ...);
void app_buf(char *buf, size_t size, ...);

// log.c
void warn(const char *str1, ...);
void panic(int err, ...) __attribute__((noreturn));

// dart.c
void dart_launch(void);
void dart_finish(void);
void dart_ctxt_syscall_enter(unsigned long sysno);
void dart_ctxt_syscall_exit(unsigned long sysno);

// racer functions
void racer_test(void);
void racer_prep(void);
void racer_cont(void);
void racer_fuzz(void);

// utils
static inline void load_module(const char *path) {
    int fd = open(path, O_RDONLY | O_CLOEXEC);
    if (fd < 0) {
        panic(errno, "No module found.", NULL);
    }

    int rv = (int) syscall(SYS_finit_module, fd, "", 0);
    if (rv != 0) {
        panic(errno, "Failed to load module", NULL);
    }

    close(fd);
}

static inline void unload_module(const char *name) {
    int rv = (int) syscall(SYS_delete_module, name);
    if (rv != 0) {
        panic(errno, "Failed to unload module", NULL);
    }
}

// racer configs
#define RACER_THREAD_MAX 64

#endif /* _RACER_INITRAMFS_COMMON_H_ */
