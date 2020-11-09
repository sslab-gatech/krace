#ifndef _DART_KERNEL_H_
#define _DART_KERNEL_H_

#define DART_DEBUG
#define DART_ASSERT

#ifdef CONFIG_DART_DEVEL
#define DART_LOGGING
#endif

/* types */
typedef u64 info_64_t;
typedef u64 hval_64_t;
typedef u64 data_64_t;
typedef u32 ptid_32_t;

#include "apidef.inc"

/* utils */
#define _CANTOR_PAIR(n, m)          ((n) + (m)) * ((n) + (m) + 1) / 2 + (m)

/* declare the wraps */
#define DART_FUNC DART_FUNC_LIB_DECLARE
#include "apidef.inc"
#undef DART_FUNC

/* declare the enums */
#define DART_FUNC DART_ENUM_DEF
enum DART_API_ENUM {
    DART_API_BEGIN_OF_ENUM = 0,
#include "apidef.inc"
    DART_API_END_OF_ENUM
};
#undef DART_FUNC

/* shortcuts */
#define dart_mark(mval) DART_FUNC_LIB_CALL_WRAP(mark, v0, DART_FLAG_NONE, mval)

/* configs */
#define DART_TIMER_LIMIT_IN_SECONDS         10

/* export info from kernel to dart */
extern data_64_t _dart_info_bio_slabs_addr;
extern data_64_t _dart_info_bio_slabs_size;

#endif /* _DART_KERNEL_H_ */
