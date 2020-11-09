#define ASYNC_REGISTER(name) \
        DART_FUNC(async, name##_register, data_64_t, func) { \
            struct dart_async *slot; \
            \
            slot = ht_dart_async_get_slot(g_dart_async_ht, hval); \
            BUG_ON(!slot); \
            \
            /* checks */ \
            if (unlikely(slot->func)) { \
                dart_pr_err( \
                    #name " register [%ps]: dangling - %ps", func, slot->func \
                ); \
                DART_BUG(); \
            } \
            \
            slot->func = func; \
        }

#define ASYNC_CANCEL(name) \
        DART_FUNC(async, name##_cancel, data_64_t, func) { \
            struct dart_async *slot; \
            \
            slot = ht_dart_async_has_slot(g_dart_async_ht, hval); \
            if (unlikely(!slot)) { \
                dart_pr_err( \
                    #name " cancel without registration: %lu [%ps]", \
                    hval, func \
                ); \
                DART_BUG(); \
            } \
            \
            slot->func = 0; \
        }

#define ASYNC_ATTACH(name) \
        DART_FUNC(async, name##_attach, data_64_t, func) { \
            struct dart_async *slot; \
            \
            slot = ht_dart_async_has_slot(g_dart_async_ht, hval); \
            if (unlikely(!slot)) { \
                dart_pr_err( \
                    #name " attach without registration: %lu [%ps]", \
                    hval, func \
                ); \
                DART_BUG(); \
            } \
            \
            if (unlikely(slot->func != func)) { \
                if (unlikely(slot->func)) { \
                    dart_pr_err( \
                        #name " attach (func mismatch): %ps | %ps", \
                        slot->func, func \
                    ); \
                    DART_BUG(); \
                } \
                if (unlikely(slot->serving != func)) { \
                    dart_pr_err( \
                        #name " attach (serving mismatch): %ps | %ps", \
                        slot->serving, func \
                    ); \
                    DART_BUG(); \
                } \
            } \
        }

ASYNC_REGISTER(rcu)

ASYNC_REGISTER(work)

ASYNC_CANCEL(work)

ASYNC_ATTACH(work)

ASYNC_REGISTER(task)

ASYNC_CANCEL(task)

ASYNC_REGISTER(timer)

ASYNC_CANCEL(timer)

ASYNC_ATTACH(timer)

ASYNC_REGISTER(krun)

ASYNC_REGISTER(block)

ASYNC_REGISTER(ipi)

ASYNC_REGISTER(custom)

ASYNC_ATTACH(custom)