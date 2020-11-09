#include <linux/loop.h>

#include <sys/stat.h>
#include <sys/mount.h>

// mount fs image
#define LOOP_DEV                    "/dev/loop0"

// mount fs module
#define MOD_NAME_MAX                64
#define MOD_PATH_MAX                128
#define MOD_MAIN_MAX                8
#define MOD_DEPS_MAX                32
#define MNT_OPTS_MAX                1024

struct mount_info {
    char fs_type[MOD_NAME_MAX];
    char mnt_opts[MNT_OPTS_MAX];
    unsigned long mod_main_num;
    unsigned long mod_deps_num;
    unsigned long mod_names_num;
    char mod_main[MOD_MAIN_MAX][MOD_PATH_MAX];
    char mod_deps[MOD_DEPS_MAX][MOD_PATH_MAX];
    char mod_names[MOD_MAIN_MAX][MOD_PATH_MAX];
};

static inline void loop_touch(const char *loop) {
    int loopfd = open(loop, O_RDWR);
    if (loopfd == -1) {
        panic(errno, "Failed to open loopfd", NULL);
    }

    close(loopfd);
}

static inline void loop_control(
        const char *loop, const char *disk, bool bind
) {
    int rv;

    // create and associate with a loop device
#ifdef USE_DART
    dart_ctxt_syscall_enter(SYS_open);
#endif
    int loopfd = open(loop, O_RDWR);
#ifdef USE_DART
    dart_ctxt_syscall_exit(SYS_open);
#endif
    if (loopfd == -1) {
        panic(errno, "Failed to open loopfd", NULL);
    }

#ifdef USE_DART
    dart_ctxt_syscall_enter(SYS_open);
#endif
    int diskfd = open(disk, O_RDWR);
#ifdef USE_DART
    dart_ctxt_syscall_exit(SYS_open);
#endif
    if (diskfd == -1) {
        panic(errno, "Failed to open diskfd", NULL);
    }

#ifdef USE_DART
    dart_ctxt_syscall_enter(SYS_ioctl);
#endif
    rv = ioctl(loopfd, bind ? LOOP_SET_FD : LOOP_CLR_FD, diskfd);
#ifdef USE_DART
    dart_ctxt_syscall_exit(SYS_ioctl);
#endif
    if (rv) {
        panic(errno, "Failed to associate diskfd and loopfd", NULL);
    }

#ifdef USE_DART
    dart_ctxt_syscall_enter(SYS_close);
#endif
    close(diskfd);
#ifdef USE_DART
    dart_ctxt_syscall_exit(SYS_close);
#endif

#ifdef USE_DART
    dart_ctxt_syscall_enter(SYS_close);
#endif
    close(loopfd);
#ifdef USE_DART
    dart_ctxt_syscall_exit(SYS_close);
#endif
}

static inline void mount_image(
        const char mod_main[MOD_MAIN_MAX][MOD_PATH_MAX],
        unsigned long mod_main_n,
        const char mod_deps[MOD_DEPS_MAX][MOD_PATH_MAX],
        unsigned long mod_deps_n,
        const char *fs_type, const char *fs_opts,
        const char *loop,
        const char *disk, const char *mptr
) {
    int rv;

    // load extra modules
    for (unsigned long i = 0; i < mod_deps_n; i++) {
        load_module(mod_deps[i]);
    }

    // touch the loop device
    loop_touch(loop);

    // prepare the mount point
    rv = mkdir(mptr, 0777);
    if (rv) {
        panic(errno, "Failed to create ", mptr, NULL);
    }

#ifdef USE_DART
    // launch dart right before mount
    dart_launch();
#endif

    // load filesystem module
    for (unsigned long i = 0; i < mod_main_n; i++) {
        load_module(mod_main[i]);
    }

    // bind to a loop device
    loop_control(loop, disk, true);

    // do the actual mount
#ifdef USE_DART
    dart_ctxt_syscall_enter(SYS_mount);
#endif
    rv = mount(loop, mptr, fs_type, 0, fs_opts);
#ifdef USE_DART
    dart_ctxt_syscall_exit(SYS_mount);
#endif
    if (rv) {
        panic(errno, "Failed to mount ", disk, NULL);
    }
}

static inline void umount_image(
        const char mod_names[MOD_MAIN_MAX][MOD_PATH_MAX],
        unsigned long mod_names_n,
        const char *loop,
        const char *disk, const char *mptr
) {
    int rv;

    // do force umount
#ifdef USE_DART
    dart_ctxt_syscall_enter(SYS_umount2);
#endif
    rv = umount2(mptr, 0);
#ifdef USE_DART
    dart_ctxt_syscall_exit(SYS_umount2);
#endif
    if (rv) {
        panic(errno, "Failed to umount ", mptr, NULL);
    }

    // unbind from a loop device
    loop_control(loop, disk, false);

    // unload module
    for (unsigned i = 0; i < mod_names_n; i++) {
        unload_module(mod_names[i]);
    }

#ifdef USE_DART
    // finish dart right after umount
    dart_finish();
#endif
}

// syscall wrapper by arg number
#define _SYSRUN_ARG_DEF(A) , long A
#define _SYSRUN_ARG_USE(A) , A

#ifdef RACER_STRACE
#define call_strace(n, sysno, tokn, ret, ...) \
        STRACE_HANDLES_##n[sysno](tokn, ret VARDEF1(_SYSRUN_ARG_USE, , ##__VA_ARGS__))
#else
#define call_strace(n, sysno, tokn, ret, ...)
#endif

#define SYSRUN_DEF(n, ...) \
        static inline long sysrun_##n( \
                long sysno \
                VARDEF1(_SYSRUN_ARG_DEF, , ##__VA_ARGS__) \
        ) { \
            call_strace(n, sysno, "->", 0x0, ##__VA_ARGS__); \
            dart_ctxt_syscall_enter(sysno); \
            long ret = syscall( \
                sysno \
                VARDEF1(_SYSRUN_ARG_USE, , ##__VA_ARGS__) \
            ); \
            dart_ctxt_syscall_exit(sysno); \
            if (ret == -1) { \
                ret = -errno; \
            } \
            call_strace(n, sysno, "<-", ret, ##__VA_ARGS__); \
            return ret; \
        }

SYSRUN_DEF(0)

SYSRUN_DEF(1, arg0)

SYSRUN_DEF(2, arg0, arg1)

SYSRUN_DEF(3, arg0, arg1, arg2)

SYSRUN_DEF(4, arg0, arg1, arg2, arg3)

SYSRUN_DEF(5, arg0, arg1, arg2, arg3, arg4)

SYSRUN_DEF(6, arg0, arg1, arg2, arg3, arg4, arg5)

#define _SYSRUN_ARG_VAL(A) , (long) (A)

#define SYSRUN_VAL(n, sys, ...) \
        sysrun_##n(sys VARDEF1(_SYSRUN_ARG_VAL, , ##__VA_ARGS__)); \
        warn(#sys, NULL);
