#include "dart.h"

/* global switch */
atomic_t dart_switch_meta = ATOMIC_INIT(0);
EXPORT_SYMBOL(dart_switch_meta);

atomic_t dart_switch_data = ATOMIC_INIT(0);
EXPORT_SYMBOL(dart_switch_data);

/* control block */
struct __ht_dart_cb *g_dart_cb_ht = NULL;

/* async info */
struct __ht_dart_async *g_dart_async_ht = NULL;
struct __ht_dart_event *g_dart_event_ht = NULL;

/* memory cell */
struct __ht_dart_mc *g_dart_mc_reader_ht = NULL;
struct __ht_dart_mc *g_dart_mc_writer_ht = NULL;

/* ignored events TODO (for debug purpose only, removed later) */
atomic_t g_dart_ignored_events = ATOMIC_INIT(0);