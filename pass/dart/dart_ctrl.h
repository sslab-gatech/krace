#ifndef _DART_CTRL_H_
#define _DART_CTRL_H_

#include "dart_common.h"

/*
 * global switches
 *  - meta switch controls whether a context is allowed to be entered or not
 *  - data switch controls whether the recording and processing should happen
 */
extern atomic_t dart_switch_meta;
extern atomic_t dart_switch_data;

#define dart_switch(name) \
        /* a switch can be turned on only when it is at value 0 */ \
        static inline void dart_switch_on_##name(void) { \
            BUG_ON(atomic_cmpxchg(&dart_switch_##name, 0, 1) != 0); \
        } \
        /* a switch can be turned off only when it is at value 1 */ \
        static inline void dart_switch_off_##name(void) { \
            while(atomic_cmpxchg(&dart_switch_##name, 1, 0) != 1) { \
                cond_resched(); \
            } \
        } \
        /* a switch can be acquired only when it has value >= 1 */ \
        static inline bool dart_switch_acq_##name(void) { \
            return atomic_inc_not_zero(&dart_switch_##name); \
        } \
        /* a switch an be released only when it has value >1 */ \
        static inline void dart_switch_rel_##name(void) { \
            BUG_ON(atomic_dec_return(&dart_switch_##name) <= 0); \
        } \


dart_switch(meta)

dart_switch(data)

/* control block */
struct dart_cb {
    /* key */
    ptid_32_t ptid;

    /* tracing switch */
    bool tracing;
    int paused;

    /* context */
    hval_64_t ctxt;

    /* stack depth count */
    int stack_depth;

    /* for COV (cfg_edge) */
    hval_64_t last_blk;

    /* execution information */
    info_64_t info;
};

DART_HMAP_DEFINE(dart_cb, 16, 32);
extern struct __ht_dart_cb *g_dart_cb_ht;

/* control block api */
static inline void dart_cb_init(struct dart_cb *cb) {
    /* start without tracing */
    cb->tracing = false;

    /* start without pausing */
    cb->paused = 0;

    /* no context assigned on start */
    cb->ctxt = 0;

    /* stack depth is zero on start */
    cb->stack_depth = 0;

    /* no basic block visited on start */
    cb->last_blk = 0;
}

static inline struct dart_cb *dart_cb_create(ptid_32_t ptid) {
    struct dart_cb *cb;

    /* find the control block */
    cb = ht_dart_cb_get_slot(g_dart_cb_ht, ptid);
    BUG_ON(!cb);

#ifdef DART_ASSERT
    if (unlikely(cb->tracing)) {
        dart_pr_err("CTXT created while tracing: %d", cb->ptid);
        DART_BUG();
    }
#endif

    /* initialize cb */
    cb->ptid = ptid;
    dart_cb_init(cb);

    return cb;
}

static inline struct dart_cb *dart_cb_find(ptid_32_t ptid) {
    return ht_dart_cb_has_slot(g_dart_cb_ht, ptid);
}

static inline void __dart_cb_tracing_count(
        ptid_32_t key, struct dart_cb *val, void *arg
) {
    unsigned int *count;
    count = (unsigned int *) arg;
    if (val->tracing) {
        *count += 1;
    }
}

static inline unsigned int dart_cb_tracing_count(
        struct __ht_dart_cb *ht
) {
    unsigned int count;

    count = 0;
    ht_dart_cb_for_each(ht, __dart_cb_tracing_count, &count);
    return count;
}

#ifdef DART_ASSERT

static inline void __dart_cb_check(
        ptid_32_t key, struct dart_cb *val, void *arg
) {
    BUG_ON(val->stack_depth != 0);
}

static inline void dart_cb_check(
        struct __ht_dart_cb *ht
) {
    ht_dart_cb_for_each(ht, __dart_cb_check, NULL);
}

#endif

static inline bool dart_in_action(void) {
    ptid_32_t ptid;
    struct dart_cb *cb;

    /* if data switch is off, exit */
    if (!dart_switch_acq_data()) {
        return false;
    }

    /* lookup the control block */
    ptid = dart_ptid();
    cb = dart_cb_find(ptid);
    if (!cb) {
        return false;
    }

    /* return immediately if the context is not tracing */
    return cb->tracing;
}

/* callback mapping */
struct dart_async {
    data_64_t func;
    data_64_t serving;

    /* stolen context */
    info_64_t info;
    struct dart_cb host;
};

DART_HMAP_DEFINE(dart_async, 16, 64);
extern struct __ht_dart_async *g_dart_async_ht;

static inline void __dart_async_pending_count(
        data_64_t key, struct dart_async *val, void *arg
) {
    unsigned int *count;
    count = (unsigned int *) arg;
    if (val->func || val->serving) {
        *count += 1;
    }
}

static inline unsigned int dart_async_pending_count(
        struct __ht_dart_async *ht
) {
    unsigned int count;

    count = 0;
    ht_dart_async_for_each(ht, __dart_async_pending_count, &count);
    return count;
}

/* event mapping */
struct dart_event {
    data_64_t func;
    data_64_t serving;

    ptid_32_t waiter;
    ptid_32_t notifier;

    /* stolen context */
    info_64_t info;
    struct dart_cb host;
};

DART_HMAP_DEFINE(dart_event, 16, 64);
extern struct __ht_dart_event *g_dart_event_ht;

static inline void __dart_event_pending_count(
        data_64_t key, struct dart_event *val, void *arg
) {
    unsigned int *count;
    count = (unsigned int *) arg;
    if (val->func || val->serving) {
        *count += 1;
    }
}

static inline unsigned int dart_event_pending_count(
        struct __ht_dart_event *ht
) {
    unsigned int count;

    count = 0;
    ht_dart_event_for_each(ht, __dart_event_pending_count, &count);
    return count;
}

/* memory cell */
struct dart_mc {
    /* last access info */
    ptid_32_t ptid;
    hval_64_t ctxt;
    hval_64_t inst;
};

DART_HMAP_DEFINE(dart_mc, 24, 64);
extern struct __ht_dart_mc *g_dart_mc_reader_ht;
extern struct __ht_dart_mc *g_dart_mc_writer_ht;

/* ignored events TODO (for debug purpose only, removed later) */
extern atomic_t g_dart_ignored_events;

#endif /* _DART_CTRL_H_ */
