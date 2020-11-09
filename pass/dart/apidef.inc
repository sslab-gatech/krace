#ifndef _RACER_DART_APIDEF_INC_
#define _RACER_DART_APIDEF_INC_

#include "vardef.h"

/* string macro */
#define __MSTR(s) #s
#define __XSTR(s) __MSTR(s)

/* dart utils */
#define _DART_FUNC_NAME(prefix, major, minor) \
        dart_##prefix ## _##major ## _##minor

/* dart enums */
#define DART_ENUM_DEF(major, minor, ...) _DART_FUNC_NAME(enum, major, minor),
#define DART_ENUM_USE(major, minor, ...) _DART_FUNC_NAME(enum, major, minor)

/* log-side macros */
#ifdef DART_LOGGING
#define _DART_LOG_VARS char *log_buf
#define _DART_LOG_ITEM_ENCODE(T, V) \
        *(T *)(log_buf) = V; \
        log_buf += sizeof(T);

#define _DART_LOG_ENCODE(major, minor, ...) \
        _DART_LOG_ITEM_ENCODE(int, DART_ENUM_USE(major, minor)) \
        _DART_LOG_ITEM_ENCODE(ptid_32_t, ptid) \
        _DART_LOG_ITEM_ENCODE(info_64_t, info) \
        _DART_LOG_ITEM_ENCODE(hval_64_t, hval) \
        VARDEF2(_DART_LOG_ITEM_ENCODE, , __VA_ARGS__)

#define _DART_LOG_ITEM_SIZING(T, V) + sizeof(T)

#define _DART_LOG_SIZING(major, minor, ...) \
        (sizeof(int) + sizeof(ptid_32_t) + \
        sizeof(info_64_t) + sizeof(hval_64_t) \
        VARDEF2(_DART_LOG_ITEM_SIZING, , __VA_ARGS__))

#define _DART_LOG(major, minor, ...) \
        log_buf = dart_ledger_next_entry( \
            g_ledger, _DART_LOG_SIZING(major, minor, __VA_ARGS__) \
        ); \
        if (log_buf) { \
            /* log only when there is enough space */ \
            _DART_LOG_ENCODE(major, minor, __VA_ARGS__); \
        }
#else
#define _DART_LOG_VARS
#define _DART_LOG(major, minor, ...)
#endif

/* lib-side macros */
#define _DART_ARG_DEF(T, V) , T V
#define _DART_ARG_USE(T, V) , V

#define _DART_FUNC_LIB_DEF(prefix, major, minor, ...) \
        void _DART_FUNC_NAME(prefix, major, minor) ( \
            info_64_t info, hval_64_t hval \
            VARDEF2(_DART_ARG_DEF, , __VA_ARGS__) \
        )

#define _DART_FUNC_LIB_USE(prefix, major, minor, ...) \
        _DART_FUNC_NAME(prefix, major, minor)( \
            info, hval \
            VARDEF2(_DART_ARG_USE, , __VA_ARGS__) \
        )

#define DART_FUNC_LIB_DECLARE(major, minor, ...) \
        extern _DART_FUNC_LIB_DEF(impl, major, minor, __VA_ARGS__); \
        extern _DART_FUNC_LIB_DEF(wrap, major, minor, __VA_ARGS__);

#define DART_FUNC_LIB_IMPL(major, minor, ...) \
        _DART_FUNC_LIB_DEF(impl, major, minor, __VA_ARGS__)

#define _DART_IS_POSSIBLE_KTHREAD_INIT(major, minor) \
        ( \
            DART_ENUM_USE(major, minor) == DART_ENUM_USE(exec, func_enter) && \
            in_task_kernel() && \
            dart_switch_acq_meta() \
        )

#define _DART_IS_POSSIBLE_KTHREAD_FINI(major, minor) \
        ( \
            DART_ENUM_USE(major, minor) == DART_ENUM_USE(exec, func_exit) && \
            in_task_kernel() && \
            cb->stack_depth == 0 \
        )

#ifdef DART_COMPLETE
#define _DART_SHOW_UNTRACED(token, ptid, major, minor, ...) \
        if (DART_ENUM_USE(major, minor) == DART_ENUM_USE(exec, func_enter)) { \
            dart_pr_info("[%u] %c>| %ps", \
                         ptid, token VARDEF2(_DART_ARG_USE, , __VA_ARGS__)); \
        } \
        if (DART_ENUM_USE(major, minor) == DART_ENUM_USE(exec, func_exit)) { \
            dart_pr_info("[%u] |<%c %ps", \
                         ptid, token VARDEF2(_DART_ARG_USE, , __VA_ARGS__)); \
        }
#else
#define _DART_SHOW_UNTRACED(token, major, minor, ...)
#endif

#define DART_FUNC_LIB_DEFINE(major, minor, ...) \
        _DART_FUNC_LIB_DEF(wrap, major, minor, __VA_ARGS__) { \
            /* declare variables up front */ \
            ptid_32_t ptid; \
            struct dart_cb *cb; \
            _DART_LOG_VARS; \
            \
            /* do not hook if dart 1) is not started yet, or 2) is closed) */ \
            if (!dart_switch_acq_data()) { \
                return; \
            } \
            \
            /* derive the ptid */ \
            ptid = dart_ptid(); \
            /* lookup the control block */ \
            cb = dart_cb_find(ptid); \
            \
            if (!cb) { \
                /* TODO account for unhandled events */ \
                atomic_inc(&g_dart_ignored_events); \
                \
                _DART_SHOW_UNTRACED('=', ptid, major, minor, __VA_ARGS__); \
                goto out; \
            } \
            \
            /* return immediately if the context is not tracing */ \
            if (!cb->tracing) { \
                _DART_SHOW_UNTRACED('-', ptid, major, minor,  __VA_ARGS__); \
                goto out; \
            } \
            \
            /* handle pause/resume early */ \
            if (DART_ENUM_USE(major, minor) == DART_ENUM_USE(exec, pause)) { \
                cb->paused++; \
                if (cb->paused == 1) { \
                    _DART_LOG(major, minor, __VA_ARGS__); \
                } \
                goto out; \
            } \
            if (DART_ENUM_USE(major, minor) == DART_ENUM_USE(exec, resume)) { \
                cb->paused--; \
                if (cb->paused == 0) { \
                    _DART_LOG(major, minor, __VA_ARGS__); \
                } \
                goto out; \
            } \
            /* handle background/foreground early */ \
            if (DART_ENUM_USE(major, minor) == DART_ENUM_USE(exec, background)) { \
                if (exec_to_background(cb, hval)) { \
                    _DART_LOG(major, minor, __VA_ARGS__); \
                } \
                goto out; \
            } \
            if (DART_ENUM_USE(major, minor) == DART_ENUM_USE(exec, foreground)) { \
                if (exec_to_foreground(cb, hval)) { \
                    _DART_LOG(major, minor, __VA_ARGS__); \
                } \
                goto out; \
            } \
            \
            /* ignore the rest if paused */ \
            if (cb->paused) { \
                _DART_SHOW_UNTRACED('+', ptid, major, minor,  __VA_ARGS__); \
                goto out; \
            } \
            \
            /* log the api call */ \
            _DART_LOG(major, minor, __VA_ARGS__); \
            \
            /* abuse the info argument to pass the cb pointer */ \
            cb->info = info; \
            info = (info_64_t) cb; \
            \
            /* call the implementation */ \
            _DART_FUNC_LIB_USE(impl, major, minor, __VA_ARGS__); \
            \
        out: \
            /* release the data switch */ \
            dart_switch_rel_data(); \
        } \
        EXPORT_SYMBOL(_DART_FUNC_NAME(wrap, major, minor));

#define DART_FUNC_LIB_CALL_IMPL(major, minor, ...) \
        _DART_FUNC_NAME(impl, major, minor)(__VA_ARGS__)

#define DART_FUNC_LIB_CALL_WRAP(major, minor, ...) \
        _DART_FUNC_NAME(wrap, major, minor)(__VA_ARGS__)

/* api-side macros */
#define _DART_ARG_TYPE(T, V) , T
#define _DART_ARG_VALUE_WRAP(T, V) , Value *V

#define DART_FUNC_API_DECLARE(major, minor, ...) \
        Function *_DART_FUNC_NAME(func, major, minor);

#define DART_FUNC_API_CONSTRUCT(major, minor, ...) \
        _DART_FUNC_NAME(func, major, minor)( \
            Function::Create( \
                FunctionType::get( \
                    void_t, \
                    { \
                        info_64_t, hval_64_t \
                        VARDEF2(_DART_ARG_TYPE, , __VA_ARGS__) \
                    }, \
                    false \
                ), \
                GlobalValue::LinkageTypes::ExternalLinkage, \
                __XSTR(_DART_FUNC_NAME(wrap, major, minor)), \
                &module \
            ) \
        ),

#define DART_FUNC_API_HOOK(major, minor, ...) \
        void _DART_FUNC_NAME(hook, major, minor)( \
            IRBuilder<> &builder, \
            flag_t flag, const hash_code &hval \
            VARDEF2(_DART_ARG_VALUE_WRAP, ,__VA_ARGS__) \
        ) { \
            builder.CreateCall( \
                _DART_FUNC_NAME(func, major, minor), \
                prepDartArgs( \
                    builder, flag, hval, \
                    { nullptr VARDEF2(_DART_ARG_USE, , __VA_ARGS__) } \
                ) \
            ); \
        }

/* flag utils */
#define _DART_FLAG_CODE_BOOL(cond, nbit)      (((cond) ? 1ul : 0ul) << (nbit))
#define _DART_FLAG_TEST_BOOL(flag, nbit)      ((flag) & (1ul << (nbit)))

/* flags */
#define DART_FLAG_NONE                          0ul

#define _DART_FLAG_CTRL(v) ((v) << 32u)
#define DART_FLAG_CTRL_CTXT_CHANGE              _DART_FLAG_CTRL(0x1ul)

#define _DART_FLAG_SYNC(is_rw, is_try, is_succ) \
        ( \
            _DART_FLAG_CODE_BOOL(is_rw, 2u) | \
            _DART_FLAG_CODE_BOOL(is_try, 1u) | \
            _DART_FLAG_CODE_BOOL(is_succ, 0u) \
        )

#define _DART_FLAG_SYNC_TEST_IS_RW(flag)        _DART_FLAG_TEST_BOOL(flag, 2u)
#define _DART_FLAG_SYNC_TEST_IS_TRY(flag)       _DART_FLAG_TEST_BOOL(flag, 1u)
#define _DART_FLAG_SYNC_TEST_IS_SUCC(flag)      _DART_FLAG_TEST_BOOL(flag, 0u)

/* special lock values */
#define DART_LOCK_ID_RCU                        1ul

#endif /* _RACER_DART_APIDEF_INC_ */

/* used for selective inclusion */
#ifdef DART_FUNC

/* SYS */
DART_FUNC(sys, launch)
DART_FUNC(sys, finish)

/* MARK */
DART_FUNC(mark, v0)
DART_FUNC(mark, v1, data_64_t, mark1)
DART_FUNC(mark, v2, data_64_t, mark1, data_64_t, mark2)
DART_FUNC(mark, v3, data_64_t, mark1, data_64_t, mark2, data_64_t, mark3)

/* CTXT */
DART_FUNC(ctxt, syscall_enter)
DART_FUNC(ctxt, syscall_exit)

DART_FUNC(ctxt, rcu_enter, data_64_t, func)
DART_FUNC(ctxt, rcu_exit, data_64_t, func)

DART_FUNC(ctxt, work_enter, data_64_t, func)
DART_FUNC(ctxt, work_exit, data_64_t, func)

DART_FUNC(ctxt, task_enter, data_64_t, func)
DART_FUNC(ctxt, task_exit, data_64_t, func)

DART_FUNC(ctxt, timer_enter, data_64_t, func)
DART_FUNC(ctxt, timer_exit, data_64_t, func)

DART_FUNC(ctxt, krun_enter, data_64_t, func)
DART_FUNC(ctxt, krun_exit, data_64_t, func)

DART_FUNC(ctxt, block_enter, data_64_t, func)
DART_FUNC(ctxt, block_exit, data_64_t, func)

DART_FUNC(ctxt, ipi_enter, data_64_t, func)
DART_FUNC(ctxt, ipi_exit, data_64_t, func)

DART_FUNC(ctxt, custom_enter, data_64_t, func)
DART_FUNC(ctxt, custom_exit, data_64_t, func)

/* EXEC */
DART_FUNC(exec, pause)
DART_FUNC(exec, resume)

DART_FUNC(exec, background)
DART_FUNC(exec, foreground)

DART_FUNC(exec, func_enter, data_64_t, addr)
DART_FUNC(exec, func_exit, data_64_t, addr)

/* ASYNC */
DART_FUNC(async, rcu_register, data_64_t, func)

DART_FUNC(async, work_register, data_64_t, func)
DART_FUNC(async, work_cancel, data_64_t, func)
DART_FUNC(async, work_attach, data_64_t, func)

DART_FUNC(async, task_register, data_64_t, func)
DART_FUNC(async, task_cancel, data_64_t, func)

DART_FUNC(async, timer_register, data_64_t, func)
DART_FUNC(async, timer_cancel, data_64_t, func)
DART_FUNC(async, timer_attach, data_64_t, func)

DART_FUNC(async, krun_register, data_64_t, func)

DART_FUNC(async, block_register, data_64_t, func)

DART_FUNC(async, ipi_register, data_64_t, func)

DART_FUNC(async, custom_register, data_64_t, func)
DART_FUNC(async, custom_attach, data_64_t, func)

/* EVENT */
DART_FUNC(event, queue_arrive)
DART_FUNC(event, queue_notify)

DART_FUNC(event, wait_arrive, data_64_t, func, data_64_t, head)
DART_FUNC(event, wait_notify_enter, data_64_t, func)
DART_FUNC(event, wait_notify_exit, data_64_t, func)
DART_FUNC(event, wait_pass, data_64_t, func)

DART_FUNC(event, sema_arrive, data_64_t, func, data_64_t, head)
DART_FUNC(event, sema_notify_enter, data_64_t, func)
DART_FUNC(event, sema_notify_exit, data_64_t, func)
DART_FUNC(event, sema_pass, data_64_t, func)

/* COV */
DART_FUNC(cov, cfg)

/* MEM */
DART_FUNC(mem, stack_push, data_64_t, addr, data_64_t, size)
DART_FUNC(mem, stack_pop, data_64_t, addr, data_64_t, size)

DART_FUNC(mem, heap_alloc, data_64_t, addr, data_64_t, size)
DART_FUNC(mem, heap_free, data_64_t, addr)

DART_FUNC(mem, percpu_alloc, data_64_t, addr, data_64_t, size)
DART_FUNC(mem, percpu_free, data_64_t, addr)

DART_FUNC(mem, read, data_64_t, addr, data_64_t, size)
DART_FUNC(mem, write, data_64_t, addr, data_64_t, size)

/* SYNC */
DART_FUNC(sync, gen_lock, data_64_t, lock)
DART_FUNC(sync, gen_unlock, data_64_t, lock)

DART_FUNC(sync, seq_lock, data_64_t, lock)
DART_FUNC(sync, seq_unlock, data_64_t, lock)

DART_FUNC(sync, rcu_lock, data_64_t, lock)
DART_FUNC(sync, rcu_unlock, data_64_t, lock)

/* ORDER */
DART_FUNC(order, ps_publish, data_64_t, addr)
DART_FUNC(order, ps_subscribe, data_64_t, addr)

DART_FUNC(order, obj_deposit, data_64_t, addr, data_64_t, objv)
DART_FUNC(order, obj_consume, data_64_t, addr)

#endif
