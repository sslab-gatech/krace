#include "common.h"

#include <sys/uio.h>

#define LOG_PREFIX "[racer]: "

static void showmsgv(va_list ap,
                     const char *before,
                     const char *after1, const char *after2) {

    /* Don't use stdio functions, because we link statically
     * and they bloat the binary. */

    const int fd = 2;  /* write to stderr */
    const unsigned extra_arg_count = (const unsigned int) (
            (after1 != NULL) + (after2 != NULL)
    );

    int argc = 1;
    struct iovec iov[32];

    const char *arg;

    if (before) {
        iov[1].iov_base = (char *) before;
        iov[1].iov_len = strlen(before);
        argc++;
    }

    while ((arg = va_arg(ap, const char *))) {
        iov[argc].iov_base = (char *) arg;
        iov[argc].iov_len = strlen(arg);
        argc++;

        /* We only support a fixed number of arguments. */
        if (argc + 1 + extra_arg_count > 32)
            break;
    }

    if (after1) {
        iov[argc].iov_base = (char *) after1;
        iov[argc].iov_len = strlen(after1);
        argc++;
    }

    if (after2) {
        iov[argc].iov_base = (char *) after2;
        iov[argc].iov_len = strlen(after2);
        argc++;
    }

    if (argc == 1)
        return;

    iov[argc].iov_base = (char *) "\n";
    iov[argc].iov_len = 1;

    iov[0].iov_base = (char *) LOG_PREFIX;
    iov[0].iov_len = sizeof(LOG_PREFIX) - 1;

    writev(fd, iov, argc + 1);
}

void panic(int err, ...) {
    va_list ap;
    va_start(ap, err);

    if (err)
        showmsgv(ap, NULL, ": ", strerror(err));
    else
        showmsgv(ap, NULL, NULL, NULL);

    va_end(ap);

    /* We want the user to see the message before we cause a kernel panic,
     * because a kernel panic obscures the message. But we need to cause
     * a kernel panic (by PID 1 exiting), because if the user tells the
     * kernel to reboot on panic, we want to make sure this happens. */
    warn("Will cause kernel panic...", NULL);
    _exit(1);
}

void warn(const char *str1, ...) {
    va_list ap;
    va_start(ap, str1);

    showmsgv(ap, str1, NULL, NULL);

    va_end(ap);
}
