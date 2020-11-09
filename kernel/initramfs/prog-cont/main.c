#ifdef RACER_STRACE
#undef RACER_STRACE
#endif
#include "fuzzer.inc"

// main
void racer_cont(void) {
    int rv;

    // get mount info
    struct mount_info *info = (struct mount_info *) (
            (char *) g_shmem + sizeof(struct shmem_hdr)
    );

    // get bytecode info
    char *cur = (char *) g_shmem + IVSHMEM_OFFSET_BYTECODE;

    // parse head segment, locate regions
    struct region_head *head = (struct region_head *) cur;
    if (memcmp(head->magics, "bytecode", 8) != 0) {
        panic(0, "Magic number does not match", NULL);
    }

    char *meta = cur + head->offset_meta;
    char *code = cur + head->offset_code;
    char *heap = cur + head->offset_heap;

    cur += sizeof(struct region_head);
    if (cur != (char *) meta) {
        panic(0, "Region head corrupted", NULL);
    }

    // parse meta_ptr segment, fixup pointers
    struct region_meta_ptr *meta_ptr = (struct region_meta_ptr *) cur;
    for (size_t i = 0; i < meta_ptr->num_ptrs; i++) {
        size_t *offs = (size_t *) (heap + meta_ptr->off_ptrs[i]);
        if (*offs) {
            *offs += (size_t) heap;
        }
    }

    cur += sizeof(struct region_meta_ptr) +
           sizeof(size_t) * meta_ptr->num_ptrs;

    // parse meta_fd segment, the info will be used to close all fds
    struct region_meta_fd *meta_fd = (struct region_meta_fd *) cur;

    cur += sizeof(struct region_meta_fd) +
           sizeof(struct lego_pack) * meta_fd->num_fds;
    if (cur != code) {
        panic(0, "Region meta corrupted", NULL);
    }

    // parse code segment
    struct region_code *code_hdr = (struct region_code *) cur;

    cur += sizeof(struct region_code) + sizeof(size_t) * code_hdr->num_threads;
    if (cur != (code + code_hdr->offset_main)) {
        panic(0, "Region code - header part corrupted", NULL);
    }

    // close stdin, this is causing hangs
    close(0);

    // prepare semaphores, arguments and launch child threads
    pthread_t tptrs[RACER_THREAD_MAX];
    struct thread_args targs[RACER_THREAD_MAX];

    sem_init(&sema_init, 0, 0);
    sem_init(&sema_fini, 0, 0);

    for (size_t i = 0; i < code_hdr->num_threads; i++) {
        targs[i].code = code + code_hdr->offset_subs[i];
        targs[i].heap = heap;

        rv = pthread_create(&tptrs[i], NULL, thread_func, &targs[i]);
        if (rv) {
            panic(rv, "Failed to create threads", NULL);
        }
    }

    // set-up
    mount_image(info->mod_main, info->mod_main_num,
                info->mod_deps, info->mod_deps_num,
                info->fs_type, info->mnt_opts,
                LOOP_DEV,
                FS_DISK_IMG, FS_DISK_MNT);

    // change directory
    dart_ctxt_syscall_enter(SYS_chdir);
    rv = chdir(FS_DISK_MNT);
    dart_ctxt_syscall_exit(SYS_chdir);
    if (rv != 0) {
        panic(errno, "Failed to chdir to disk mount point", NULL);
    }

    // run the precalls first
    interpret(code + code_hdr->offset_main, heap);

    // inform threads that we are ready
    for (size_t i = 0; i < code_hdr->num_threads; i++) {
        rv = sem_post(&sema_init);
        if (rv) {
            panic(rv, "Failed to post for init semaphore");
        }
    }

    // wait for threads to finish
    for (size_t i = 0; i < code_hdr->num_threads; i++) {
        rv = sem_wait(&sema_fini);
        if (rv) {
            panic(rv, "Failed to wait for fini semaphore");
        }
    }

    // close all fd ever appeared
    for (size_t i = 0; i < meta_fd->num_fds; i++) {
        dart_ctxt_syscall_enter(SYS_close);
        close(load_slot(&meta_fd->fds[i], heap));
        dart_ctxt_syscall_exit(SYS_close);
    }

    // change directory
    dart_ctxt_syscall_enter(SYS_chdir);
    rv = chdir("/");
    dart_ctxt_syscall_exit(SYS_chdir);
    if (rv != 0) {
        panic(errno, "Failed to chdir to root directory", NULL);
    }

    // tear-down
    umount_image(info->mod_names, info->mod_names_num,
                 LOOP_DEV, FS_DISK_IMG,
                 FS_DISK_MNT);

    // wait for join all threads
    for (size_t i = 0; i < code_hdr->num_threads; i++) {
        rv = pthread_join(tptrs[i], NULL);
        if (rv) {
            panic(rv, "Failed to join threads", NULL);
        }
    }
}
