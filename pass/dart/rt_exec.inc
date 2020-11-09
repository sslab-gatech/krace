DART_FUNC (exec, func_enter, data_64_t, addr) {
    struct dart_cb *cb = (struct dart_cb *) info;
    cb->stack_depth++;
}

DART_FUNC (exec, func_exit, data_64_t, addr) {
    struct dart_cb *cb = (struct dart_cb *) info;
    cb->stack_depth--;

#ifdef DART_ASSERT
    if (unlikely(cb->stack_depth < 0)) {
        dart_pr_err("Call stack corrupted: %d", cb->ptid);
        DART_BUG();
    }
#endif
}

static inline bool exec_to_background(struct dart_cb *cb, hval_64_t hval) {
    struct dart_async *slot;
    struct dart_cb tmp;

    /* get slot */
    slot = ht_dart_async_has_slot(g_dart_async_ht, hval);
    if (!slot || !slot->serving) {
        /* TODO
         * some unknown callback gets executed...
         * this should not happen, but lets debug later
         */
        return false;
    }

    /* treat as exec_pause if there is no host */
    if (!slot->info) {
        cb->paused++;
        return false;
    }

    /* exchange control block */
    memcpy(&tmp, cb, sizeof(struct dart_cb));
    memcpy(cb, &slot->host, sizeof(struct dart_cb));
    memcpy(&slot->host, &tmp, sizeof(struct dart_cb));

    return true;
}

static inline bool exec_to_foreground(struct dart_cb *cb, hval_64_t hval) {
    struct dart_async *slot;
    struct dart_cb tmp;

    /* get slot */
    slot = ht_dart_async_has_slot(g_dart_async_ht, hval);
    if (!slot || !slot->serving) {
        /* TODO
         * some unknown callback gets executed...
         * this should not happen, but lets debug later
         */
        return false;
    }

    /* treat as exec_resume if there is no host */
    if (!slot->info) {
        cb->paused--;
        return false;
    }

    /* exchange control block */
    memcpy(&tmp, cb, sizeof(struct dart_cb));
    memcpy(cb, &slot->host, sizeof(struct dart_cb));
    memcpy(&slot->host, &tmp, sizeof(struct dart_cb));

    return true;
}
