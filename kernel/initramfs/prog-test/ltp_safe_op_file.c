#include "ltp.h"

// lib: touch
LTP_OP_SAFE_LIB_DEC(
        touch,
        void,
        const char *, path, mode_t, mode, struct timespec *, times
) {

    // open_close
    unsigned int fd = _safe_sys(
            open,
            path,
            O_CREAT | O_WRONLY | O_TRUNC,
            S_IRUSR | S_IWUSR | S_IRGRP | S_IWGRP | S_IROTH | S_IWOTH
    );
    _safe_sys(close, fd);

    // chmod if needed
    if (mode) {
        _safe_sys(chmod, path, mode);
    }

    // utimensat if needed
    if (times) {
        _safe_sys(utimensat, AT_FDCWD, path, times, 0);
    }
}

// lib: file_printf
LTP_OP_SAFE_LIB_DEC_VA(
        file_printf,
        void,
        const char *, path, const char *, fmt
) {
    long ret;

    // prepare buffer
    char *buf;

    va_list ap;
    va_start(ap, fmt);

    ret = vasprintf(&buf, fmt, ap);
    if (ret == -1) {
        ltp_ret(LTP_RV_MERGE(TBROK, -errno),
                "vasprintf(%s, ...) failed",
                fmt);
    }

    va_end(ap);

    // open
    unsigned int fd = safe_sys_(
            open, path,
            O_CREAT | O_WRONLY | O_TRUNC,
            S_IRUSR | S_IWUSR | S_IRGRP | S_IWGRP | S_IROTH | S_IWOTH
    );

    // write
    _safe_sys(write, fd, buf, (size_t) ret);

    // close
    _safe_sys(close, fd);

    // clean up resources
    free(buf);
}

// lib: opendir
LTP_OP_SAFE_LIB_DEC(
        opendir,
        struct dirent *,
        const char *, name
) {
    struct dirent *ret;

    errno = 0;
    ret = (struct dirent *) opendir(name);
    if (errno) {
        ltp_ret(LTP_RV_MERGE(TBROK, -errno),
                "opendir(%s) failed",
                name);
    }

    return ret;
}

// lib: readdir
LTP_OP_SAFE_LIB_DEC(
        readdir,
        struct dirent *,
        struct dirent *, dirp
) {
    struct dirent *ret;

    errno = 0;
    ret = (struct dirent *) readdir((DIR *) dirp);
    if (errno) {
        ltp_ret(LTP_RV_MERGE(TBROK, -errno),
                "readdir(%p) failed",
                dirp);
    }

    return ret;
}

// lib: closedir
LTP_OP_SAFE_LIB_DEC(
        closedir,
        void,
        struct dirent *, dirp
) {
    errno = 0;
    closedir((DIR *) dirp);
    if (errno) {
        ltp_ret(LTP_RV_MERGE(TBROK, -errno),
                "closedir(%p) failed",
                dirp);
    }
}