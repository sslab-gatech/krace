DART_FUNC (event, queue_arrive) {
}

DART_FUNC (event, queue_notify) {
}

#define EVENT_ARRIVE(name) \
        DART_FUNC(event, name##_arrive, data_64_t, func, data_64_t, head) { \
            struct dart_cb *cb; \
            struct dart_event *slot; \
            \
            slot = ht_dart_event_get_slot(g_dart_event_ht, hval); \
            BUG_ON(!slot); \
            \
            cb = (struct dart_cb *) info; \
            \
            /* checks */ \
            if (unlikely(slot->func)) { \
                dart_pr_err( \
                    #name " arrival [%ps]: dangling - %ps: (ptid: %d [%d])", \
                    func, slot->func, slot->waiter, cb->ptid \
                ); \
                DART_BUG(); \
            } \
            \
            /* mark arrival by registering func and ptid */ \
            slot->func = func; \
            slot->waiter = cb->ptid; \
        }

#define EVENT_NOTIFY_ENTER(name) \
        DART_FUNC(event, name##_notify_enter, data_64_t, func) { \
            struct dart_event *slot; \
            ptid_32_t ptid; \
            struct dart_cb *cb; \
            _DART_LOG_VARS; \
            \
            /* check if this is a registered event */ \
            slot = ht_dart_event_has_slot(g_dart_event_ht, hval); \
            if (!slot || !slot->func) { \
                return; \
            } \
            \
            ptid = dart_ptid(); \
            \
            /* record (must be in the front) */ \
            _DART_LOG(event, name##_notify_enter, data_64_t, func); \
            \
            /* checks */ \
            if (unlikely(slot->func != func)) { \
                dart_pr_err(#name " enter: %ps | %ps", slot->func, func); \
                DART_BUG(); \
            } \
            if (unlikely(slot->notifier)) { \
                dart_pr_err( \
                    #name " enter [%d]: dangling - %d", \
                    ptid, slot->notifier \
                ); \
                DART_BUG(); \
            } \
            \
            /* mark that we have started serving the event */ \
            slot->serving = func; \
            slot->notifier = ptid; \
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
        }

#define EVENT_NOTIFY_EXIT(name) \
        DART_FUNC(event, name##_notify_exit, data_64_t, func) { \
            struct dart_event *slot; \
            ptid_32_t ptid; \
            struct dart_cb *cb; \
            _DART_LOG_VARS; \
            \
            /* check if this is a registered event */ \
            slot = ht_dart_event_has_slot(g_dart_event_ht, hval); \
            if (!slot || !slot->serving) { \
                return; \
            } \
            \
            ptid = dart_ptid(); \
            \
            /* checks */ \
            if (unlikely(slot->serving != func)) { \
                dart_pr_err(#name " exit: %ps | %ps", slot->func, func); \
                DART_BUG(); \
            } \
            if (unlikely(slot->notifier != ptid)) { \
                dart_pr_err( \
                    #name " exit [%d]: mismatch - %d", \
                    ptid, slot->notifier \
                ); \
                DART_BUG(); \
            } \
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
            /* mark that we have finished serving the event */ \
            slot->notifier = 0; \
            slot->serving = 0; \
            \
            /* record (must be in the end) */ \
            _DART_LOG(event, name##_notify_exit, data_64_t, func); \
        }

#define EVENT_PASS(name) \
        DART_FUNC(event, name##_pass, data_64_t, func) { \
            struct dart_cb *cb; \
            struct dart_event *slot; \
            \
            slot = ht_dart_event_has_slot(g_dart_event_ht, hval); \
            if (unlikely(!slot)) { \
                dart_pr_err( \
                    #name " pass without arrival: %lu [%ps]", \
                    hval, func \
                ); \
                DART_BUG(); \
            } \
            \
            cb = (struct dart_cb *) info; \
            \
            /* checks */ \
            if (unlikely(slot->waiter != cb->ptid && \
                         slot->notifier != cb->ptid)) { \
                dart_pr_err( \
                    #name " pass: ptid mismatch: %d - %d|%d %lu [%ps]", \
                    cb->ptid, slot->waiter, slot->notifier, hval, func \
                ); \
                DART_BUG(); \
            } \
            \
            /* mark passing by clearing ptid */ \
            slot->waiter = 0; \
            slot->func = 0; \
        }

EVENT_ARRIVE(wait)

EVENT_NOTIFY_ENTER(wait)

EVENT_NOTIFY_EXIT(wait)

EVENT_PASS(wait)

EVENT_ARRIVE(sema)

EVENT_NOTIFY_ENTER(sema)

EVENT_NOTIFY_EXIT(sema)

EVENT_PASS(sema)
