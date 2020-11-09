#include "dart.h"

/* globals */
long dart_iseq = 0;
EXPORT_SYMBOL(dart_iseq);

char *dart_shared = NULL;
EXPORT_SYMBOL(dart_shared);

char *dart_private = NULL;
EXPORT_SYMBOL(dart_private);

char *dart_reserved = NULL;
EXPORT_SYMBOL(dart_reserved);

/* define the implementations */
#define DART_FUNC DART_FUNC_LIB_IMPL
#include "rt_sys.inc"
#include "rt_mark.inc"
#include "rt_ctxt.inc"
#include "rt_exec.inc"
#include "rt_async.inc"
#include "rt_event.inc"
#include "rt_cov.inc"
#include "rt_mem_stack.inc"
#include "rt_mem_heap.inc"
#include "rt_mem_percpu.inc"
#include "rt_mem_access.inc"
#include "rt_sync.inc"
#include "rt_order.inc"
#undef DART_FUNC

/* define the wraps */
#define DART_FUNC DART_FUNC_LIB_DEFINE
#include "apidef.inc"
#undef DART_FUNC

/* export info from kernel to dart */
data_64_t _dart_info_bio_slabs_addr = 0;
data_64_t _dart_info_bio_slabs_size = 0;

/* define the syscall */
SYSCALL_DEFINE2(dart, unsigned long, cmd, unsigned long, arg) {
    switch (cmd) {
        case CMD_DART_LAUNCH:
            DART_FUNC_LIB_CALL_IMPL(sys, launch,
                                    DART_FLAG_NONE, 0);
            break;

        case CMD_DART_FINISH:
            DART_FUNC_LIB_CALL_IMPL(sys, finish,
                                    DART_FLAG_NONE, 0);
            break;

        case CMD_DART_CTXT_SYSCALL_START:
            DART_FUNC_LIB_CALL_IMPL(ctxt, syscall_enter,
                                    DART_FLAG_CTRL_CTXT_CHANGE, arg);
            break;

        case CMD_DART_CTXT_SYSCALL_EXIT:
            DART_FUNC_LIB_CALL_IMPL(ctxt, syscall_exit,
                                    DART_FLAG_CTRL_CTXT_CHANGE, arg);
            break;

        default:
            dart_pr_err("invalid syscall command: %lu", cmd);
            return -1;
    }

    return 0;
}

/* boot parameter */
static __init int dart_instance_cmd(char *str) {
    if (kstrtol(str, 10, &dart_iseq)) {
        return -1;
    }

    return 0;
}

__setup("dart_instance=", dart_instance_cmd);