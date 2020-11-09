#ifndef _DART_LOG_H_
#define _DART_LOG_H_

#include "dart_common.h"

/* ledger */
#define LEDGER_SIZE _MB(256)
#define LEDGER_NAME "/host/ledger"
#define RESERVE_LEDGER_SIZE (IVSHMEM_OFFSET_INSTANCES - IVSHMEM_OFFSET_RESERVED)

/* structs */
struct dart_ledger {
    atomic64_t count;     /* number of entries in the ledger */
    atomic64_t cursor;    /* current offset into the buffer */
    char buffer[0];     /* buffer of unlimited size */
};

struct dart_reserve_ledger {
    atomic64_t cursor;
    char buffer[0];
};

/* globals */
extern struct dart_ledger *g_ledger;
extern struct dart_reserve_ledger *g_reserve_ledger;

/* ledger manipulations */
static inline char *
dart_ledger_next_entry(struct dart_ledger *ledger, size_t size) {
    size_t offset;

    atomic64_inc(&ledger->count);
    offset = atomic64_fetch_add((int) size, &ledger->cursor);

    /* check if ledger may overflow */
    if (offset + size >= LEDGER_SIZE) {
        return NULL;
    }

    return ledger->buffer + offset;
}

static inline void dart_ledger_transfer_ro_reserve(
        struct dart_ledger *ledger, struct dart_reserve_ledger *reserve
) {
    size_t length, chunks, offset;
    char *cursor;

    /* find the cursor */
    length = atomic64_read(&ledger->cursor);
    chunks = length + 8 + sizeof(struct dart_ledger);
    offset = atomic64_fetch_add(chunks, &reserve->cursor);

    if (offset + chunks >= RESERVE_LEDGER_SIZE) {
        return;
    }
    cursor = reserve->buffer + offset;

    /* put the instance id there first */
    (*(long *) cursor) = dart_iseq;
    cursor += sizeof(long);

    /* put the dart_ledger header there */
    memcpy(cursor, ledger, sizeof(struct dart_ledger));
    cursor += sizeof(struct dart_ledger);

    /* copy the content */
    memcpy(cursor, ledger->buffer, length);
}

#endif /* _DART_LOG_H_ */
