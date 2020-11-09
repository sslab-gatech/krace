/* generics */
static inline void ctxt_generic_enter(struct dart_cb *cb, hval_64_t ctxt) {
    cb->ctxt = ctxt;
    cb->tracing = true;
}

static inline void ctxt_generic_exit(struct dart_cb *cb, hval_64_t ctxt) {
    /* the context, when existing, must match with the context when entering */
#ifdef DART_ASSERT
    if (unlikely(!cb->tracing)) {
        dart_pr_err("CTXT exits while not tracing: [%d]", cb->ptid);
        DART_BUG();
    }
    if (unlikely(cb->ctxt != ctxt)) {
        dart_pr_err("CTXT exits with wrong context: [%d] %d - %d",
                    cb->ptid, cb->ctxt, ctxt);
        DART_BUG();
    }
    if (unlikely(cb->stack_depth)) {
        dart_pr_err("CTXT exits with stack dangling: [%d] %d",
                    cb->ptid, cb->stack_depth);
        DART_BUG();
    }
    if (unlikely(cb->paused)) {
        dart_pr_err("CTXT exits with pause dangling: [%d] %d",
                    cb->ptid, cb->paused);
        DART_BUG();
    }
#endif

    cb->ctxt = 0;
    cb->tracing = false;
}

/* direct context */
#define CTXT_DIRECT_ENTER(name, acct, kint) \
        DART_FUNC(ctxt, name##_enter) { \
            ptid_32_t ptid; \
            struct dart_cb *cb; \
            _DART_LOG_VARS; \
            \
            ptid = _ptid_in_##acct(); \
            \
            /* record */ \
            _DART_LOG(ctxt, name##_enter); \
            \
            BUG_ON(!in_##kint()); \
            \
            /* get control block */ \
            cb = dart_cb_create(ptid); \
            ctxt_generic_enter(cb, hval); \
        }

#define CTXT_DIRECT_EXIT(name, acct, kint) \
        DART_FUNC(ctxt, name##_exit) { \
            ptid_32_t ptid; \
            struct dart_cb *cb; \
            _DART_LOG_VARS; \
            \
            ptid = _ptid_in_##acct(); \
            \
            /* record */ \
            _DART_LOG(ctxt, name##_exit); \
            \
            BUG_ON(!in_##kint()); \
            \
            /* get control block */ \
            cb = dart_cb_find(ptid); \
            BUG_ON(!cb); \
            ctxt_generic_exit(cb, hval); \
        }

CTXT_DIRECT_ENTER(syscall, task_user, task_user)

CTXT_DIRECT_EXIT(syscall, task_user, task_user)

/* indirect context */
#define CTXT_INDIRECT_ENTER(name, acct, kint) \
        DART_FUNC(ctxt, name##_enter, data_64_t, func) { \
            struct dart_async *slot; \
            ptid_32_t ptid; \
            struct dart_cb *cb; \
            _DART_LOG_VARS; \
            \
            /* check if this is a registered callback */ \
            slot = ht_dart_async_has_slot(g_dart_async_ht, hval); \
            if (!slot || !slot->func) { \
                return; \
            } \
            \
            ptid = _ptid_in_##acct(); \
            \
            /* record (must be in the front) */ \
            _DART_LOG(ctxt, name##_enter, data_64_t, func); \
            \
            /* checks */ \
            if (unlikely(slot->func != func)) { \
                dart_pr_err(#name " enter: %ps | %ps", slot->func, func); \
                DART_BUG(); \
            } \
            \
            /* mark that we have started serving the callback */ \
            slot->func = 0; \
            slot->serving = func; \
            \
            /* now we know that the callback is registered */ \
            BUG_ON(!in_##kint()); \
            \
            /* check if we steal this context from someone */ \
            if (unlikely(slot->info)) { \
                dart_pr_err( \
                    #name " enter: nested context: %d [%ps]", \
                    ptid, slot->func \
                ); \
                DART_BUG(); \
            } \
            \
            cb = dart_cb_find(ptid); \
            if (!cb) { \
                cb = dart_cb_create(ptid); \
                slot->info = 0; \
            } else if (!cb->tracing) { \
                dart_cb_init(cb); \
                slot->info = 0; \
            } else { \
                memcpy(&slot->host, cb, sizeof(struct dart_cb)); \
                dart_cb_init(cb); \
                slot->info = 1; \
            } \
            \
            /* get control block */ \
            ctxt_generic_enter(cb, hval); \
        } \
        EXPORT_SYMBOL(_DART_FUNC_NAME(impl, ctxt, name##_enter));

#define CTXT_INDIRECT_EXIT(name, acct, kint) \
        DART_FUNC(ctxt, name##_exit, data_64_t, func) { \
            struct dart_async *slot; \
            ptid_32_t ptid; \
            struct dart_cb *cb; \
            _DART_LOG_VARS; \
            \
            /* check if this is an unregistered callback */ \
            slot = ht_dart_async_has_slot(g_dart_async_ht, hval); \
            if (!slot || !slot->serving) { \
                return; \
            } \
            \
            ptid = _ptid_in_##acct(); \
            \
            /* checks */ \
            if (unlikely(slot->serving != func)) { \
                dart_pr_err(#name " exit: %ps | %ps", slot->serving, func); \
                DART_BUG(); \
            } \
            \
            /* now we know that the callback is registered */ \
            BUG_ON(!in_##kint()); \
            \
            /* get control block */ \
            cb = dart_cb_find(ptid); \
            BUG_ON(!cb); \
            ctxt_generic_exit(cb, hval); \
            \
            /* now it is time to restore the callback to host */ \
            if (slot->info) { \
                memcpy(cb, &slot->host, sizeof(struct dart_cb)); \
                slot->info = 0; \
            } \
            \
            /* mark that we have finished serving the callback */ \
            slot->serving = 0; \
            \
            /* record (must be in the end) */ \
            _DART_LOG(ctxt, name##_exit, data_64_t, func); \
        } \
        EXPORT_SYMBOL(_DART_FUNC_NAME(impl, ctxt, name##_exit));

CTXT_INDIRECT_ENTER(rcu, softirq, serving_softirq)

CTXT_INDIRECT_EXIT(rcu, softirq, serving_softirq)

CTXT_INDIRECT_ENTER(work, task_kernel, task_kernel)

CTXT_INDIRECT_EXIT(work, task_kernel, task_kernel)

CTXT_INDIRECT_ENTER(task, task_user, task_user)

CTXT_INDIRECT_EXIT(task, task_user, task_user)

CTXT_INDIRECT_ENTER(timer, softirq, serving_softirq)

CTXT_INDIRECT_EXIT(timer, softirq, serving_softirq)

CTXT_INDIRECT_ENTER(krun, task_kernel, task_kernel)

CTXT_INDIRECT_EXIT(krun, task_kernel, task_kernel)

CTXT_INDIRECT_ENTER(block, softirq, serving_softirq)

CTXT_INDIRECT_EXIT(block, softirq, serving_softirq)

CTXT_INDIRECT_ENTER(ipi, hardirq, irq)

CTXT_INDIRECT_EXIT(ipi, hardirq, irq)

CTXT_INDIRECT_ENTER(custom, task_kernel, task_kernel)

CTXT_INDIRECT_EXIT(custom, task_kernel, task_kernel)