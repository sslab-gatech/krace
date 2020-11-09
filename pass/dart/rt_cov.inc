DART_FUNC (cov, cfg) {
    struct dart_cb *cb = (struct dart_cb *) info;
    cov_cfg_add_edge(hash_u64_into_h24_chain(cb->last_blk, hval));
    cb->last_blk = hval;
}