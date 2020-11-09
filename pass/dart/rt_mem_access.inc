/* generics */
#define mem_check_alias(rw) \
        static inline void mem_check_alias_##rw( \
                ptid_32_t ptid, hval_64_t inst, data_64_t addr, \
                hval_64_t *s, hval_64_t *p \
        ) { \
            struct dart_mc *cell; \
            \
            cell = ht_dart_mc_has_slot(g_dart_mc_## rw ## _ht, addr); \
            if (!cell) { \
                /* exit if no counterpart cell exists */ \
                *s = 0; \
                *p = 0; \
            } \
            \
            else if (cell->ptid == ptid) { \
                /* found an memdu pair, report it */ \
                *s = cell->inst; \
                *p = 0; \
            } \
            \
            else { \
                /* found an alias pair, report it */ \
                *s = 0; \
                *p = cell->inst; \
            } \
        }

mem_check_alias(reader)

mem_check_alias(writer)

#define ALIAS_CHECK_DECLARE(icur, pcur) \
        u64 icur; \
        hval_64_t pcur; \

#define ALIAS_CHECK_INIT(icur, pcur) \
        icur = 0; \
        pcur = 0; \

#define ALIAS_CHECK_LOOP(hval, addr, i, p, icur, pcur) \
        if (pcur != p) { \
            if (pcur) { \
                cov_alias_add_pair(hash_u64_into_h24_chain(pcur, hval)); \
                rtrace_record(pcur, hval, addr + icur, i - icur + 1); \
            } \
            pcur = p; \
            icur = i; \
        } \

#define ALIAS_CHECK_FINI(hval, addr, size, icur, pcur) \
        if (pcur) { \
            cov_alias_add_pair(hash_u64_into_h24_chain(pcur, hval)); \
            rtrace_record(pcur, hval, addr + icur, size - icur); \
        } \

#define MEMDU_CHECK_DECLARE(scur) \
        hval_64_t scur; \

#define MEMDU_CHECK_INIT(scur) \
        scur = 0; \

#define MEMDU_CHECK_LOOP(hval, i, s, scur) \
        if (scur != s) { \
            if (scur) { \
                cov_dfg_add_edge(hash_u64_into_h24_chain(scur, hval)); \
            } \
            scur = s; \
        } \

#define MEMDU_CHECK_FINI(hval, scur) \
        if (scur) { \
            cov_dfg_add_edge(hash_u64_into_h24_chain(scur, hval)); \
        } \


/* specifics */
DART_FUNC (mem, read, data_64_t, addr, data_64_t, size) {
    struct dart_cb *cb;
    struct dart_mc *cell;
    u64 i;
    hval_64_t p, s;
    ALIAS_CHECK_DECLARE(iw_cur, pw_cur)
    MEMDU_CHECK_DECLARE(sw_cur)

    cb = (struct dart_cb *) info;

    /* init the cursors */
    ALIAS_CHECK_INIT(iw_cur, pw_cur)
    MEMDU_CHECK_INIT(sw_cur)

    for (i = 0; i < size; i++) {
        /* check memory alias pair (w -> r) */
        mem_check_alias_writer(cb->ptid, hval, addr + i, &s, &p);

        /* check if we need to record alias */
        ALIAS_CHECK_LOOP(hval, addr, i, p, iw_cur, pw_cur)

        /* check if we need to report memdu */
        MEMDU_CHECK_LOOP(hval, i, s, sw_cur)

        /* take ownership of the cell */
        cell = ht_dart_mc_get_slot(g_dart_mc_reader_ht, addr + i);

        cell->ptid = cb->ptid;
        cell->ctxt = cb->ctxt;
        cell->inst = hval;
    }

    /* record at the end of trace */
    ALIAS_CHECK_FINI(hval, addr, size, iw_cur, pw_cur)
    MEMDU_CHECK_FINI(hval, sw_cur)
}

DART_FUNC (mem, write, data_64_t, addr, data_64_t, size) {
    struct dart_cb *cb;
    struct dart_mc *cell;
    u64 i;
    hval_64_t p, s;
    ALIAS_CHECK_DECLARE(ir_cur, pr_cur)
    ALIAS_CHECK_DECLARE(iw_cur, pw_cur)
    MEMDU_CHECK_DECLARE(sr_cur)
    MEMDU_CHECK_DECLARE(sw_cur)

    cb = (struct dart_cb *) info;

    /* init the cursors */
    ALIAS_CHECK_INIT(ir_cur, pr_cur)
    ALIAS_CHECK_INIT(iw_cur, pw_cur)
    MEMDU_CHECK_INIT(sr_cur)
    MEMDU_CHECK_INIT(sw_cur)

    for (i = 0; i < size; i++) {
        /* check memory alias pair (r -> w) */
        mem_check_alias_reader(cb->ptid, hval, addr + i, &s, &p);

        /* check if we need to report alias */
        ALIAS_CHECK_LOOP(hval, addr, i, p, ir_cur, pr_cur)

        /* check if we need to report memdu */
        MEMDU_CHECK_LOOP(hval, i, s, sr_cur)

        /* check memory alias pair (w -> w) */
        mem_check_alias_writer(cb->ptid, hval, addr + i, &s, &p);

        /* check if we need to report alias */
        ALIAS_CHECK_LOOP(hval, addr, i, p, iw_cur, pw_cur)

        /* check if we need to report memdu */
        MEMDU_CHECK_LOOP(hval, i, s, sw_cur)

        /* take ownership of the cell */
        cell = ht_dart_mc_get_slot(g_dart_mc_writer_ht, addr + i);

        cell->ptid = cb->ptid;
        cell->ctxt = cb->ctxt;
        cell->inst = hval;
    }

    /* record at the end of trace */
    ALIAS_CHECK_FINI(hval, addr, size, ir_cur, pr_cur)
    ALIAS_CHECK_FINI(hval, addr, size, iw_cur, pw_cur)
    MEMDU_CHECK_FINI(hval, sr_cur)
    MEMDU_CHECK_FINI(hval, sw_cur)
}