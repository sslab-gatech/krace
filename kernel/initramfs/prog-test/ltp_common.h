#ifndef _RACER_LTP_COMMON_H_
#define _RACER_LTP_COMMON_H_

// std
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <stdarg.h>
#include <string.h>
#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>

// sys
#include <sys/types.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <sys/syscall.h>

// unix
#include <unistd.h>
#include <fcntl.h>
#include <sched.h>
#include <signal.h>
#include <errno.h>
#include <dirent.h>

// linux
#include <linux/limits.h>

// constants
#define UID_ROOT    0
#define UID_NOBODY  65534
#define GID_ROOT    0
#define GID_NOBODY  65534

// variadic argument expansion
#define __SELECT(T1, V1, T2, V2, T3, V3, T4, V4, T5, V5, T6, V6, N, ...) N
#define __IGNORE(...)

#define __NARGS_0(...) void
#define __NARGS_1(T, V, ...) T V
#define __NARGS_2(T, V, ...) T V, __NARGS_1(__VA_ARGS__)
#define __NARGS_3(T, V, ...) T V, __NARGS_2(__VA_ARGS__)
#define __NARGS_4(T, V, ...) T V, __NARGS_3(__VA_ARGS__)
#define __NARGS_5(T, V, ...) T V, __NARGS_4(__VA_ARGS__)
#define __NARGS_6(T, V, ...) T V, __NARGS_5(__VA_ARGS__)

#define __NARGS_N(...) __SELECT( \
        __VA_ARGS__, \
        __NARGS_6, __IGNORE, \
        __NARGS_5, __IGNORE, \
        __NARGS_4, __IGNORE, \
        __NARGS_3, __IGNORE, \
        __NARGS_2, __IGNORE, \
        __NARGS_1, __IGNORE, \
        __NARGS_0, __IGNORE, \
        )(__VA_ARGS__)

#define __FARGS_0(...)
#define __FARGS_1(T, V, ...) , T V __FARGS_0(__VA_ARGS__)
#define __FARGS_2(T, V, ...) , T V __FARGS_1(__VA_ARGS__)
#define __FARGS_3(T, V, ...) , T V __FARGS_2(__VA_ARGS__)
#define __FARGS_4(T, V, ...) , T V __FARGS_3(__VA_ARGS__)
#define __FARGS_5(T, V, ...) , T V __FARGS_4(__VA_ARGS__)
#define __FARGS_6(T, V, ...) , T V __FARGS_5(__VA_ARGS__)

#define __FARGS_N(...) __SELECT( \
        __VA_ARGS__, \
        __FARGS_6, __IGNORE, \
        __FARGS_5, __IGNORE, \
        __FARGS_4, __IGNORE, \
        __FARGS_3, __IGNORE, \
        __FARGS_2, __IGNORE, \
        __FARGS_1, __IGNORE, \
        __FARGS_0, __IGNORE, \
        )(__VA_ARGS__)

#define __NVALS_0(...)
#define __NVALS_1(T, V, ...) V
#define __NVALS_2(T, V, ...) V, __NVALS_1(__VA_ARGS__)
#define __NVALS_3(T, V, ...) V, __NVALS_2(__VA_ARGS__)
#define __NVALS_4(T, V, ...) V, __NVALS_3(__VA_ARGS__)
#define __NVALS_5(T, V, ...) V, __NVALS_4(__VA_ARGS__)
#define __NVALS_6(T, V, ...) V, __NVALS_5(__VA_ARGS__)

#define __NVALS_N(...) __SELECT( \
        __VA_ARGS__, \
        __NVALS_6, __IGNORE, \
        __NVALS_5, __IGNORE, \
        __NVALS_4, __IGNORE, \
        __NVALS_3, __IGNORE, \
        __NVALS_2, __IGNORE, \
        __NVALS_1, __IGNORE, \
        __NVALS_0, __IGNORE, \
        )(__VA_ARGS__)

#define __FVALS_0(...)
#define __FVALS_1(T, V, ...) , V __FVALS_0(__VA_ARGS__)
#define __FVALS_2(T, V, ...) , V __FVALS_1(__VA_ARGS__)
#define __FVALS_3(T, V, ...) , V __FVALS_2(__VA_ARGS__)
#define __FVALS_4(T, V, ...) , V __FVALS_3(__VA_ARGS__)
#define __FVALS_5(T, V, ...) , V __FVALS_4(__VA_ARGS__)
#define __FVALS_6(T, V, ...) , V __FVALS_5(__VA_ARGS__)

#define __FVALS_N(...) __SELECT( \
        __VA_ARGS__, \
        __FVALS_6, __IGNORE, \
        __FVALS_5, __IGNORE, \
        __FVALS_4, __IGNORE, \
        __FVALS_3, __IGNORE, \
        __FVALS_2, __IGNORE, \
        __FVALS_1, __IGNORE, \
        __FVALS_0, __IGNORE, \
        )(__VA_ARGS__)

// propogate debug information
#define _LTP_OP_ARGS_DEF_ const char *ltp_file, int ltp_line
#define _LTP_OP_ARGS_USE_ ltp_file, ltp_line
#define _LTP_OP_ARGS_CUR_ __FILE__, __LINE__
#define _LTP_OP_ARGS_FMT_ "%s:%d"

// syscall wrapper
#define plat_sys_(name, ...) ltp_sys_##name(__VA_ARGS__)

// ltp safe syscall
#define LTP_OP_SAFE_SYS_DEF(name, sys_expr, ret_expr, ret_type, ...) \
        static inline long ltp_sys_##name( \
                __NARGS_N(__VA_ARGS__) \
        ) { \
            errno = 0; \
            long ret = (sys_expr); \
            return errno ? -errno : ret; \
        } \
        \
        static inline ret_type _safe_sys_##name( \
                _LTP_OP_ARGS_DEF_ __FARGS_N(__VA_ARGS__) \
        ) { \
            long ret = plat_sys_(name, __NVALS_N(__VA_ARGS__)); \
            (ret_expr); \
        }

#define _safe_sys(name, ...) _safe_sys_##name(_LTP_OP_ARGS_USE_, ##__VA_ARGS__)
#define safe_sys_(name, ...) _safe_sys_##name(_LTP_OP_ARGS_CUR_, ##__VA_ARGS__)

// ltp safe libcall
#define LTP_OP_SAFE_LIB_DEC(name, ret_type, ...) \
        ret_type _safe_lib_##name( \
                _LTP_OP_ARGS_DEF_ __FARGS_N(__VA_ARGS__) \
        )

#define LTP_OP_SAFE_LIB_DEC_VA(name, ret_type, ...) \
        ret_type _safe_lib_##name( \
                _LTP_OP_ARGS_DEF_ __FARGS_N(__VA_ARGS__), ... \
        )

#define _safe_lib(name, ...) _safe_lib_##name(_LTP_OP_ARGS_USE_, ##__VA_ARGS__)
#define safe_lib_(name, ...) _safe_lib_##name(_LTP_OP_ARGS_CUR_, ##__VA_ARGS__)

#endif /* _RACER_LTP_COMMON_H_ */
