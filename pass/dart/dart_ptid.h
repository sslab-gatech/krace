#ifndef _DART_PTID_H_
#define _DART_PTID_H_

#include "dart_common.h"

/* kernel vs user context */
static inline bool in_task_kernel(void) {
    return in_task() && (current->flags & PF_KTHREAD);
}

static inline bool in_task_user(void) {
    return in_task() && !(current->flags & PF_KTHREAD);
}

/*
 * ptid: process or context id
 * (hi 16 bits) ---- : pid       (task) user
 * (hi 16 bits) ---1 : pid       (task) kernel
 * (hi 16 bits) -1XX : cpuid     (softirq)
 * (hi 16 bits) -2XX : cpuid     (hardirq)
 * (hi 16 bits) -4XX : cpuid     (nmi)
 */
static inline ptid_32_t _ptid_in_task_user(void) {
    ptid_32_t ptid = current->pid;
#ifdef DART_ASSERT
    BUG_ON(ptid >= (1 << 16));
#endif
    return ptid;
}

static inline ptid_32_t _ptid_in_task_kernel(void) {
    ptid_32_t ptid = current->pid;
#ifdef DART_ASSERT
    BUG_ON(ptid >= (1 << 16));
#endif
    return (1 << 16) + ptid;
}

static inline ptid_32_t _ptid_in_softirq(void) {
    return ((1 << 8) + smp_processor_id()) << 16;
}

static inline ptid_32_t _ptid_in_hardirq(void) {
    return ((1 << 9) + smp_processor_id()) << 16;
}

static inline ptid_32_t _ptid_in_nmi(void) {
    return ((1 << 10) + smp_processor_id()) << 16;
}

/* get ptid without knowing the context */
static inline ptid_32_t dart_ptid(void) {
    if (in_nmi()) {
        return _ptid_in_nmi();
    }

    if (in_irq()) {
        return _ptid_in_hardirq();
    }

    if (in_serving_softirq()) {
        return _ptid_in_softirq();
    }

    if (in_task_kernel()) {
        return _ptid_in_task_kernel();
    }

#ifdef DART_ASSERT
    BUG_ON(!in_task_user());
#endif
    return _ptid_in_task_user();
}

#endif /* _DART_PTID_H_ */
