#include "vardef.h"

#ifndef _RACER_FUZZ_H_STRACE_H_
#define _RACER_FUZZ_H_STRACE_H_

#define STRACE_SYSCALL_NUM_MAX          1024

#define STRACE_HANDLE_DECLARE(n, ...) \
        typedef void (*t_strace_##n)(const char *, long, ##__VA_ARGS__); \
        extern t_strace_##n STRACE_HANDLES_##n[STRACE_SYSCALL_NUM_MAX]

#define STRACE_HANDLE_DEFINE(n) \
        t_strace_##n STRACE_HANDLES_##n[STRACE_SYSCALL_NUM_MAX] = {0}

STRACE_HANDLE_DECLARE(0);
STRACE_HANDLE_DECLARE(1, long);
STRACE_HANDLE_DECLARE(2, long, long);
STRACE_HANDLE_DECLARE(3, long, long, long);
STRACE_HANDLE_DECLARE(4, long, long, long, long);
STRACE_HANDLE_DECLARE(5, long, long, long, long, long);
STRACE_HANDLE_DECLARE(6, long, long, long, long, long, long);

// apis
void strace_init(void);

#endif /* _RACER_FUZZ_H_STRACE_H_ */
