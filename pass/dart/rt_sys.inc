typedef log_buf;;

static inline void force_full_sync(bool wait) {
#ifdef DART_LOGGING
#define DART_FULL_SYNC_LIMIT 256
    unsigned int count = 0;
#endif

    do {
        synchronize_rcu();
        synchronize_rcu_tasks();

        rcu_barrier();
        rcu_barrier_tasks();

        synchronize_rcu();
        synchronize_rcu_tasks();

#ifdef DART_LOGGING
        count += 1;
        if (count == DART_FULL_SYNC_LIMIT) {
            DART_BUG();
        }
#endif
    } while (wait && (
            dart_async_pending_count(g_dart_async_ht) +
            dart_event_pending_count(g_dart_event_ht) != 0
    ));
}

#define __addr_to_pcpu_ptr(addr)                    \
    (void __percpu *)((unsigned long)(addr) -       \
              (unsigned long)pcpu_base_addr +       \
              (unsigned long)__per_cpu_start)

static inline void handle_static_percpu_alloc(void) {
    const size_t size = __per_cpu_end - __per_cpu_start;
    void __percpu *base = __addr_to_pcpu_ptr(pcpu_base_addr);
    unsigned int cpu;
    /* for logging */
    ptid_32_t ptid = 0;
    info_64_t info = 0;
    hval_64_t hval = 0;
    _DART_LOG_VARS;

    for_each_possible_cpu(cpu) {
        /* TODO just log for now */
        _DART_LOG(
                mem, percpu_alloc,
                data_64_t, ((data_64_t) (per_cpu_ptr(base, cpu))),
                data_64_t, size
        );
    }
}

static inline void handle_static_percpu_free(void) {
    void __percpu *base = __addr_to_pcpu_ptr(pcpu_base_addr);
    unsigned int cpu;
    /* for logging */
    ptid_32_t ptid = 0;
    info_64_t info = 0;
    hval_64_t hval = 0;
    _DART_LOG_VARS;

    for_each_possible_cpu(cpu) {
        /* TODO just log for now */
        _DART_LOG(
                mem, percpu_free,
                data_64_t, ((data_64_t) (per_cpu_ptr(base, cpu)))
        );
    }
}

static inline void handle_current_free(void) {
    /* fdt */
    struct files_struct *files = current->files;
    struct fdtable *fdt = rcu_dereference_raw(files->fdt);

    /* ioc */
    struct io_context *ioc = current->io_context;

    /* for logging */
    ptid_32_t ptid = 0;
    info_64_t info = 0;
    hval_64_t hval = 0;
    _DART_LOG_VARS;

    /* TODO just log for now */
    if (fdt != &files->fdtab) {
        _DART_LOG(
                mem, heap_free,
                data_64_t, (data_64_t) fdt->fd
        );
        _DART_LOG(
                mem, heap_free,
                data_64_t, (data_64_t) fdt->open_fds
        );
        _DART_LOG(
                mem, heap_free,
                data_64_t, (data_64_t) fdt
        );
    }

    if (ioc) {
        _DART_LOG(
                mem, heap_free,
                data_64_t, (data_64_t) ioc
        );
    }
}

static inline void handle_block_bio_alloc(void) {
    /* for logging */
    ptid_32_t ptid = 0;
    info_64_t info = 0;
    hval_64_t hval = 0;
    _DART_LOG_VARS;

    BUG_ON(!_dart_info_bio_slabs_addr || !_dart_info_bio_slabs_size);

    /* TODO just log for now */
    _DART_LOG(
            mem, heap_alloc,
            data_64_t, *(data_64_t *) _dart_info_bio_slabs_addr,
            data_64_t, _dart_info_bio_slabs_size
    );
}

static inline void handle_block_bio_free(void) {
    /* for logging */
    ptid_32_t ptid = 0;
    info_64_t info = 0;
    hval_64_t hval = 0;
    _DART_LOG_VARS;

    /* TODO just log for now */
    _DART_LOG(
            mem, heap_free,
            data_64_t, *(data_64_t *) _dart_info_bio_slabs_addr
    );
}

DART_FUNC (sys, launch) {
    ptid_32_t ptid;
    _DART_LOG_VARS;

    /* make sure that ivshmem has passed the info to us */
    BUG_ON(!dart_shared || !dart_private || !dart_reserved);

    /* allocate memory */
    g_dart_cb_ht = vzalloc(sizeof(ht_dart_cb_t));

    g_dart_async_ht = vzalloc(sizeof(ht_dart_async_t));
    g_dart_event_ht = vzalloc(sizeof(ht_dart_event_t));

    g_dart_mc_reader_ht = vzalloc(sizeof(ht_dart_mc_t));
    g_dart_mc_writer_ht = vzalloc(sizeof(ht_dart_mc_t));

    BUG_ON(!g_dart_cb_ht ||
           !g_dart_async_ht ||
           !g_dart_event_ht ||
           !g_dart_mc_reader_ht ||
           !g_dart_mc_writer_ht);

    /* link shared info */
    g_cov_cfg_edge = (unsigned long *)
            (dart_shared + IVSHMEM_OFFSET_COV_CFG_EDGE);
    g_cov_dfg_edge = (unsigned long *)
            (dart_shared + IVSHMEM_OFFSET_COV_DFG_EDGE);
    g_cov_alias_inst = (unsigned long *)
            (dart_shared + IVSHMEM_OFFSET_COV_ALIAS_INST);

    /* link wks */
    g_rtinfo = (struct dart_rtinfo *) (dart_private + INSTMEM_OFFSET_RTINFO);
    atomic64_set(&g_rtinfo->has_proper_exit, 0);
    atomic64_set(&g_rtinfo->has_warning_or_error, 0);
    atomic64_set(&g_rtinfo->cov_cfg_edge_incr, 0);
    atomic64_set(&g_rtinfo->cov_dfg_edge_incr, 0);
    atomic64_set(&g_rtinfo->cov_alias_inst_incr, 0);

    g_rtrace = (struct dart_rtrace *) (dart_private + INSTMEM_OFFSET_RTRACE);
    atomic64_set(&g_rtrace->count, 0);

#ifdef DART_LOGGING
    /* allocate memory */
    g_ledger = vzalloc(LEDGER_SIZE);
    BUG_ON(!g_ledger);

    /* prepare log */
    atomic64_set(&g_ledger->count, 0);
    atomic64_set(&g_ledger->cursor, 0);

    /* link with reserve */
    g_reserve_ledger = (struct dart_reserve_ledger *) dart_reserved;
#endif

    /* record first entry */
    ptid = _ptid_in_task_user();
    _DART_LOG(sys, launch);

    /* record the initializations */
    handle_static_percpu_alloc();
    handle_block_bio_alloc();

    /* flush executions */
    force_full_sync(false);

    /* set wks, mark that we are now accepting contexts */
    dart_switch_on_data();
    dart_switch_on_meta();

#ifdef DART_DEBUG
    dart_pr_debug("launched\n"
                  "shared: 0x%lx - {\n"
                  "\tcov_cfg_edge: 0x%lx\n"
                  "\tcov_dfg_edge: 0x%lx\n"
                  "\tcov_alias_inst: 0x%lx\n"
                  "}\n"
                  "private: 0x%lx - {\n"
                  "\trtinfo: 0x%lx\n"
                  "\trtrace: 0x%lx\n"
                  "}\n"
                  "local - {\n"
                  "\tcb_ht: 0x%lx [0x%lx]\n"
                  "\tasync_ht: 0x%lx [0x%lx]\n"
                  "\tevent_ht: 0x%lx [0x%lx]\n"
                  "\tmc_reader_ht: 0x%lx [0x%lx]\n"
                  "\tmc_writer_ht: 0x%lx [0x%lx]\n"
                  "}\n",
                  dart_shared,
                  g_cov_cfg_edge,
                  g_cov_dfg_edge,
                  g_cov_alias_inst,
                  dart_private,
                  g_rtinfo,
                  g_rtrace,
                  g_dart_cb_ht, sizeof(ht_dart_cb_t),
                  g_dart_async_ht, sizeof(ht_dart_async_t),
                  g_dart_event_ht, sizeof(ht_dart_event_t),
                  g_dart_mc_reader_ht, sizeof(ht_dart_mc_t),
                  g_dart_mc_writer_ht, sizeof(ht_dart_mc_t));
#endif
}

DART_FUNC (sys, finish) {
#ifdef DART_LOGGING
    struct file *fp;
    loff_t off;
    s64 log_cnt, log_len;
#endif
    ptid_32_t ptid;
    _DART_LOG_VARS;

    /* flush executions */
    force_full_sync(true);

    /* reset wks, mark that we are not accepting any new context */
    dart_switch_off_meta();

    /* wait for every context to finish */
    while (dart_cb_tracing_count(g_dart_cb_ht)) {
        cond_resched();
    }

    /* now we are not even processing anything */
    dart_switch_off_data();

#ifdef DART_ASSERT
    /* make sure that all cbs are in proper shape */
    dart_cb_check(g_dart_cb_ht);
#endif

    /* mark that we have exited properly */
    atomic64_set(&g_rtinfo->has_proper_exit, 1);

    /* record the clean ups */
    handle_static_percpu_free();
    handle_current_free();
    handle_block_bio_free();

    /* record last entry */
    ptid = _ptid_in_task_user();
    _DART_LOG(sys, finish);

#ifdef DART_LOGGING
    /* dump the log to shared directory */
    log_cnt = atomic64_read(&g_ledger->count);
    log_len = atomic64_read(&g_ledger->cursor);

    fp = filp_open(LEDGER_NAME, O_WRONLY | O_CREAT, 0777);
    if (!fp) {
        dart_pr_err("unable to create ledger file");
        goto out;
    }

    off = 0;
    if (kernel_write(fp, &log_cnt, sizeof(s64), &off) != sizeof(s64)) {
        dart_pr_err("unable to write log_cnt to ledger file");
        goto out;
    }
    if (kernel_write(fp, &log_len, sizeof(s64), &off) != sizeof(s64)) {
        dart_pr_err("unable to write log_len to ledger file");
        goto out;
    }
    if (kernel_write(fp, g_ledger->buffer, log_len, &off) != log_len) {
        dart_pr_err("unable to write buffers to ledger file");
        goto out;
    }

    /* flush */
    vfs_fsync(fp, 0);

out:
    if (fp) {
        filp_close(fp, NULL);
    }
#endif

#ifdef DART_DEBUG
    dart_pr_debug("finished\n"
                  "ledger - {\n"
                  "\tignored_events: %d\n"
                  "}\n"
                  "rtinfo - {\n"
                  "\tcov_cfg_edge_incr: %d\n"
                  "\tcov_dfg_edge_incr: %d\n"
                  "\tcov_alias_inst_incr: %d\n"
                  "}\n"
                  "rtrace - {\n"
                  "\tcount: %d\n"
                  "}\n",
                  atomic_read(&g_dart_ignored_events),
                  atomic64_read(&g_rtinfo->cov_cfg_edge_incr),
                  atomic64_read(&g_rtinfo->cov_dfg_edge_incr),
                  atomic64_read(&g_rtinfo->cov_alias_inst_incr),
                  atomic64_read(&g_rtrace->count));
#endif

    /* free heap */
    vfree(g_dart_mc_reader_ht);
    vfree(g_dart_mc_writer_ht);

    vfree(g_dart_async_ht);
    vfree(g_dart_event_ht);

    vfree(g_dart_cb_ht);

#ifdef DART_LOGGING
    vfree(g_ledger);
#endif
}