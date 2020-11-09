#include "common.h"

#include <pthread.h>
#include <semaphore.h>

#ifdef RACER_STRACE
#include "strace.h"
#endif

#ifndef USE_DART
#define USE_DART
#endif
#include "shared.inc"

// interpret bytecode
struct lego_pack {
    size_t addr;
    size_t size;
};

struct syscall_prep_pack {
    struct lego_pack src;
    struct lego_pack dst;
};

struct region_head {
    char magics[8];
    size_t offset_meta;
    size_t offset_code;
    size_t offset_heap;
};

struct region_meta_ptr {
    size_t num_ptrs;
    size_t off_ptrs[0];
};

struct region_meta_fd {
    size_t num_fds;
    struct lego_pack fds[0];
};

struct region_code {
    size_t num_threads;
    size_t offset_main;
    size_t offset_subs[0];
};

struct region_syscall_prep {
    size_t num_packs;
    struct syscall_prep_pack packs[0];
};

struct region_syscall_exec {
    size_t scno;
    struct lego_pack retv;
    size_t num_args;
    struct lego_pack args[0];
};

static inline void prep_slot(
        struct lego_pack *src,
        struct lego_pack *dst,
        char *heap) {

    void *src_addr = src->addr + heap;
    void *dst_addr = dst->addr + heap;

    switch (dst->size) {
        case 8:
            switch (src->size) {
                case 8:
                    *(__uint64_t *) dst_addr = *(__uint64_t *) src_addr;
                    break;
                case 4:
                    *(__uint64_t *) dst_addr = *(__uint32_t *) src_addr;
                    break;
                case 2:
                    *(__uint64_t *) dst_addr = *(__uint16_t *) src_addr;
                    break;
                case 1:
                    *(__uint64_t *) dst_addr = *(__uint8_t *) src_addr;
                    break;
                default:
                    panic(0, "Unexpected size mismatch in prep", NULL);
                    break;
            }
            break;
        case 4:
            switch (src->size) {
                case 8:
                    *(__uint32_t *) dst_addr = *(__uint64_t *) src_addr;
                    break;
                case 4:
                    *(__uint32_t *) dst_addr = *(__uint32_t *) src_addr;
                    break;
                case 2:
                    *(__uint32_t *) dst_addr = *(__uint16_t *) src_addr;
                    break;
                case 1:
                    *(__uint32_t *) dst_addr = *(__uint8_t *) src_addr;
                    break;
                default:
                    panic(0, "Unexpected size mismatch in prep", NULL);
                    break;
            }
            break;
        case 2:
            switch (src->size) {
                case 8:
                    *(__uint16_t *) dst_addr = *(__uint64_t *) src_addr;
                    break;
                case 4:
                    *(__uint16_t *) dst_addr = *(__uint32_t *) src_addr;
                    break;
                case 2:
                    *(__uint16_t *) dst_addr = *(__uint16_t *) src_addr;
                    break;
                case 1:
                    *(__uint16_t *) dst_addr = *(__uint8_t *) src_addr;
                    break;
                default:
                    panic(0, "Unexpected size mismatch in prep", NULL);
                    break;
            }
            break;
        case 1:
            switch (src->size) {
                case 8:
                    *(__uint8_t *) dst_addr = *(__uint64_t *) src_addr;
                    break;
                case 4:
                    *(__uint8_t *) dst_addr = *(__uint32_t *) src_addr;
                    break;
                case 2:
                    *(__uint8_t *) dst_addr = *(__uint16_t *) src_addr;
                    break;
                case 1:
                    *(__uint8_t *) dst_addr = *(__uint8_t *) src_addr;
                    break;
                default:
                    panic(0, "Unexpected size mismatch in prep", NULL);
                    break;
            }
            break;
        default:
            if (dst->size != src->size) {
                panic(0, "Unexpected size mismatch in prep", NULL);
            }
            memcpy(dst_addr, src_addr, src->size);
            break;
    }
}

static inline long load_slot(struct lego_pack *hole, char *heap) {
    void *addr = hole->addr + heap;
    switch (hole->size) {
        case 8:
            return *(__uint64_t *) addr;
        case 4:
            return *(__uint32_t *) addr;
        case 2:
            return *(__uint16_t *) addr;
        case 1:
            return *(__uint8_t *) addr;
        default:
            panic(0, "Only primitive types are allowed to load", NULL);
            break;
    }
}

static inline void save_slot(struct lego_pack *hole, char *heap, long data) {
    void *addr = hole->addr + heap;
    switch (hole->size) {
        case 8:
            *(__uint64_t *) addr = data;
            break;
        case 4:
            *(__uint32_t *) addr = data;
            break;
        case 2:
            *(__uint16_t *) addr = data;
            break;
        case 1:
            *(__uint8_t *) addr = data;
            break;
        default:
            panic(0, "Only primitive types are allowed to save", NULL);
            break;
    }
}

// generic syscall handler
static inline char *handle_syscall(char *code, char *heap) {
    char *cur = code;

    // do prep
    struct region_syscall_prep *prep = (struct region_syscall_prep *) cur;
    for (size_t i = 0; i < prep->num_packs; i++) {
        prep_slot(&prep->packs[i].src, &prep->packs[i].dst, heap);
    }

    cur += sizeof(struct region_syscall_prep) +
           sizeof(struct syscall_prep_pack) * prep->num_packs;

    // do exec
    struct region_syscall_exec *exec = (struct region_syscall_exec *) cur;

    long ret;
    switch (exec->num_args) {

#define _SYSRUN_ARG_LOAD(I) , load_slot(&exec->args[I], heap)
#define SYSRUN_CASE(n, ...) \
        case n: \
            ret = sysrun_##n(exec->scno \
                VARDEF1(_SYSRUN_ARG_LOAD, , ##__VA_ARGS__) \
            ); \
            break \

        SYSRUN_CASE(0);
        SYSRUN_CASE(1, 0);
        SYSRUN_CASE(2, 0, 1);
        SYSRUN_CASE(3, 0, 1, 2);
        SYSRUN_CASE(4, 0, 1, 2, 3);
        SYSRUN_CASE(5, 0, 1, 2, 3, 4);
        SYSRUN_CASE(6, 0, 1, 2, 3, 4, 5);

        default:
            panic(0, "More than six arguments in a syscall", NULL);
            break;
    }

    save_slot(&exec->retv, heap, ret);

    // return the location of next syscall instructions
    cur += sizeof(struct region_syscall_exec) +
           sizeof(struct lego_pack) * exec->num_args;

    return cur;
}

static inline void interpret(char *code, char *heap) {
    char *cur = code;

    size_t num_syscalls = *(size_t *) (cur);
    cur += sizeof(size_t);

    for (size_t i = 0; i < num_syscalls; i++) {
        cur = handle_syscall(cur, heap);
    }
}

// thread shared globals
sem_t sema_init;
sem_t sema_fini;

// thread function
struct thread_args {
    char *code;
    char *heap;
};

static void *thread_func(void *argv) {
    struct thread_args *args = argv;

    int rv;

    // wait for main thread
    rv = sem_wait(&sema_init);
    if (rv) {
        panic(rv, "Failed to wait for init semaphore");
    }

    // run bytecode
    interpret(args->code, args->heap);

    // post for main thread
    rv = sem_post(&sema_fini);
    if (rv) {
        panic(rv, "Failed to post for post semaphore");
    }

    // finish
    return NULL;
}