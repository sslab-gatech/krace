#ifndef _DART_WKS_H_
#define _DART_WKS_H_

#include "dart_common.h"
#include "dart_hash.h"

/* shared info */
#define _COV_CFG_EDGE_BITS          (1 << 24)
extern unsigned long *g_cov_cfg_edge;

#define _COV_DFG_EDGE_BITS          (1 << 24)
extern unsigned long *g_cov_dfg_edge;

#define _COV_ALIAS_INST_BITS        (1 << 24)
extern unsigned long *g_cov_alias_inst;

#define _RTRACE_ENTRY_MAX           (14 * (1 << 20) / (4 * sizeof(u64)))

/* private info */
struct dart_rtinfo {
    /* states */
    atomic64_t has_proper_exit;
    atomic64_t has_warning_or_error;

    /* coverage */
    atomic64_t cov_cfg_edge_incr;
    atomic64_t cov_dfg_edge_incr;
    atomic64_t cov_alias_inst_incr;
};

struct dart_rtrace {
    atomic64_t count;       /* number of entries in the rtrace */
    u64 buffer[0];          /* buffer of unlimited size */
};

extern struct dart_rtinfo *g_rtinfo;
extern struct dart_rtrace *g_rtrace;

/* operations */
static inline void cov_cfg_add_edge(hash24_t edge) {
    if (!test_and_set_bit(edge, g_cov_cfg_edge)) {
        atomic64_inc(&g_rtinfo->cov_cfg_edge_incr);
    }
}

static inline void cov_dfg_add_edge(hash24_t edge) {
    if (!test_and_set_bit(edge, g_cov_dfg_edge)) {
        atomic64_inc(&g_rtinfo->cov_dfg_edge_incr);
    }
}

static inline void cov_alias_add_pair(hash24_t pair) {
    if (!test_and_set_bit(pair, g_cov_alias_inst)) {
        atomic64_inc(&g_rtinfo->cov_alias_inst_incr);
    }
}

static inline void rtrace_record(
        hval_64_t from, hval_64_t into, data_64_t addr, u64 size
) {
    unsigned long offset;

    /* calculate the offset */
    offset = atomic64_fetch_inc(&g_rtrace->count);
    if (offset >= _RTRACE_ENTRY_MAX) {
        return;
    }
    offset *= 4;

    /* do the recording */
    g_rtrace->buffer[offset + 0] = from;
    g_rtrace->buffer[offset + 1] = into;
    g_rtrace->buffer[offset + 2] = addr;
    g_rtrace->buffer[offset + 3] = size;
}

#endif /* _DART_WKS_H_ */
