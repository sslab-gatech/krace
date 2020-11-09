#ifndef _RACER_LTP_SAFE_OP_FILE_H_
#define _RACER_LTP_SAFE_OP_FILE_H_

#include "ltp_common.h"

LTP_OP_SAFE_SYS_DEF(
        access,
        ({
            syscall(SYS_faccessat, AT_FDCWD, file, mode);
        }),
        ({
            if (ret < 0) {
                ltp_ret(LTP_RV_MERGE(TBROK, ret),
                        "access(%s, 0%o) failed",
                        file, mode);
            }
            return (int) ret;
        }),
        int,
        const char *, file, int, mode
)

LTP_OP_SAFE_SYS_DEF(
        open,
        ({
            syscall(SYS_openat, AT_FDCWD, path, flag, mode);
        }),
        ({
            if (ret < 0) {
                ltp_ret(LTP_RV_MERGE(TBROK, ret),
                        "open(%s, 0x%x, 0%o) failed",
                        path, flag, mode);
            }
            return (unsigned int) ret;
        }),
        unsigned int,
        const char *, path, int, flag, int, mode
)

LTP_OP_SAFE_SYS_DEF(
        creat,
        ({
            syscall(SYS_openat, AT_FDCWD, path,
                    O_CREAT | O_WRONLY | O_TRUNC, mode);
        }),
        ({
            if (ret < 0) {
                ltp_ret(LTP_RV_MERGE(TBROK, ret),
                        "creat(%s, 0%o) failed",
                        path, mode);
            }
            return (unsigned int) ret;
        }),
        unsigned int,
        const char *, path, int, mode
)

LTP_OP_SAFE_SYS_DEF(
        close,
        ({
            syscall(SYS_close, fd);
        }),
        ({
            if (ret) {
                ltp_ret(LTP_RV_MERGE(TBROK, ret),
                        "close(%u) failed",
                        fd);
            }
        }),
        void,
        unsigned int, fd
)

LTP_OP_SAFE_SYS_DEF(
        chmod,
        ({
            syscall(SYS_fchmodat, AT_FDCWD, path, mode);
        }),
        ({
            if (ret) {
                ltp_ret(LTP_RV_MERGE(TBROK, ret),
                        "chmod(%s, 0%o) failed",
                        path, mode);
            }
        }),
        void,
        const char *, path, mode_t, mode
)

LTP_OP_SAFE_SYS_DEF(
        chown,
        ({
            syscall(SYS_fchownat, AT_FDCWD, path, uid, gid);
        }),
        ({
            if (ret) {
                ltp_ret(LTP_RV_MERGE(TBROK, ret),
                        "chown(%s, %d, %d) failed",
                        path, uid, gid);
            }
        }),
        void,
        const char *, path, uid_t, uid, gid_t, gid
)

LTP_OP_SAFE_SYS_DEF(
        utimensat,
        ({
            syscall(SYS_utimensat, dfd, path, times, flags);
        }),
        ({
            if (ret) {
                ltp_ret(LTP_RV_MERGE(TBROK, ret),
                        "utimensat(%d, %s, %p, 0x%x) failed",
                        dfd, path, times, flags);
            }
        }),
        void,
        int, dfd, const char *, path, struct timespec *, times, int, flags
)

LTP_OP_SAFE_SYS_DEF(
        mkdir,
        ({
            syscall(SYS_mkdirat, AT_FDCWD, path, mode);
        }),
        ({
            if (ret) {
                ltp_ret(LTP_RV_MERGE(TBROK, ret),
                        "mkdir(%p, 0%o) failed",
                        path, mode);
            }
        }),
        void,
        const char *, path, mode_t, mode
)

LTP_OP_SAFE_SYS_DEF(
        symlink,
        ({
            syscall(SYS_symlinkat, existing, AT_FDCWD, new);
        }),
        ({
            if (ret) {
                ltp_ret(LTP_RV_MERGE(TBROK, ret),
                        "symlink(%s, %s) failed",
                        existing, new);
            }
        }),
        void,
        const char *, existing, const char *, new
)

LTP_OP_SAFE_SYS_DEF(
        unlink,
        ({
            syscall(SYS_unlinkat, AT_FDCWD, path, 0);
        }),
        ({
            if (ret) {
                ltp_ret(LTP_RV_MERGE(TBROK, ret),
                        "unlink(%s) failed",
                        path);
            }
        }),
        void,
        const char *, path
)

LTP_OP_SAFE_SYS_DEF(
        write,
        ({
            syscall(SYS_write, fd, buf, count);
        }),
        ({
            if ((size_t) ret != count) {
                ltp_ret(LTP_RV_MERGE(TBROK, ret),
                        "write(%d, %s, %l) failed",
                        fd, buf, count);
            }
        }),
        void,
        unsigned int, fd, const char *, buf, size_t, count
)

LTP_OP_SAFE_SYS_DEF(
        stat,
        ({
            syscall(SYS_newfstatat, AT_FDCWD, path, buf, 0);
        }),
        ({
            if (ret) {
                ltp_ret(LTP_RV_MERGE(TBROK, ret),
                        "stat(%s, %p) failed",
                        path, buf);
            }
        }),
        void,
        const char *, path, struct stat *, buf
)

LTP_OP_SAFE_SYS_DEF(
        chdir,
        ({
            syscall(SYS_chdir, path);
        }),
        ({
            if (ret) {
                ltp_ret(LTP_RV_MERGE(TBROK, ret),
                        "chdir(%s) failed",
                        path);
            }
        }),
        void,
        const char *, path
)

/*
 * Safe function to touch a file
 *
 * If the file (path) does not exist, it will be created with
 * the specified permission (mode) and the access/modification times (times).
 *
 * If mode is 0 then the file is created with (0666 & ~umask)
 * permission or (if the file exists) the permission is not changed.
 *
 * times is a timespec[2] (as for utimensat(2)). If times is NULL then
 * the access/modification times of the file is set to the current time.
 */
LTP_OP_SAFE_LIB_DEC(
        touch,
        void,
        const char *, path, mode_t, mode, struct timespec *, times
);

/*
 * Safe function to printf to a file
 *
 * If the file (path) does not exist, it will be created first with mode
 * (0666 & ~umask)
 */
LTP_OP_SAFE_LIB_DEC_VA(
        file_printf,
        void,
        const char *, path, const char *, fmt
);

/*
 * Safe function to opendir
 */
LTP_OP_SAFE_LIB_DEC(
        opendir,
        struct dirent *,
        const char *, name
);

/*
 * Safe function to readdir
 */
LTP_OP_SAFE_LIB_DEC(
        readdir,
        struct dirent *,
        struct dirent *, dirp
);

/*
 * Safe function to closedir
 */
LTP_OP_SAFE_LIB_DEC(
        closedir,
        void,
        struct dirent *, dirp
);

#endif /* _RACER_LTP_SAFE_OP_FILE_H_ */
