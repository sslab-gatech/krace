#ifndef _DART_HASH_H_
#define _DART_HASH_H_

#include "dart_common.h"

/* hash functions */
#define DART_HASH_DEFINE(ilen, bits) \
        typedef uint##ilen ## _t hash##bits ## _t; \
        static inline hash##bits ## _t hash_u64_into_h##bits(uint64_t n) { \
            return (hash##bits ## _t) hash_64(n, bits); \
        } \
        static inline hash##bits ## _t hash_u32_into_h##bits(uint32_t n) { \
            return (hash##bits ## _t) hash_32(n, bits); \
        } \
        static inline hash##bits ## _t hash_u64_into_h##bits ## _chain( \
                uint64_t n, uint64_t m \
        ) { \
            return hash_u64_into_h##bits(_CANTOR_PAIR(n, m)); \
        } \
        static inline hash##bits ## _t hash_u32_into_h##bits ## _chain( \
                uint32_t n, uint32_t m \
        ) { \
            return hash_u32_into_h##bits(_CANTOR_PAIR(n, m)); \
        } \

DART_HASH_DEFINE(32, 24)

DART_HASH_DEFINE(32, 20)

DART_HASH_DEFINE(16, 16)

DART_HASH_DEFINE(16, 12)

/* hash tables */
#define atomic32_t atomic_t
#define atomic32_read atomic_read
#define atomic32_set atomic_set

#define DART_HMAP_DEFINE(name, bits, klen) \
        /* typedef */ \
        typedef struct __ht_##name { \
            DECLARE_BITMAP(bmap, (1 << bits)); \
            struct  __htcell_##name { \
                atomic##klen ## _t key; \
                struct name val; \
            } cell[1 << bits]; \
        } ht_##name ## _t; \
        \
        /* functions */ \
        static inline struct name * \
        ht_##name ## _get_slot( \
                struct __ht_##name *ht, uint##klen ## _t k \
        ) { \
            uint##klen ## _t e; \
            hash##bits ## _t i = hash_u##klen ## _into_h##bits(k); \
            hash##bits ## _t o = 0; \
            \
            while (test_and_set_bit(i, ht->bmap)) { \
                /* in case someone acquired the bit but has not set it yet */ \
                do { \
                    e = atomic##klen ## _read(&(ht->cell[i].key)); \
                } while (!e); \
                \
                /* return an existing slot */ \
                if (e == k) { \
                    return &(ht->cell[i].val); \
                } \
                \
                /* move on */ \
                i = (i + 1) % (1 << bits); \
                BUG_ON((++o) == (1 << bits)); \
            } \
            \
            /* we are the first to set the bit */ \
            atomic##klen ## _set(&(ht->cell[i].key), k); \
            return &(ht->cell[i].val); \
        } \
        \
        static inline struct name * \
        ht_##name ## _has_slot( \
                struct __ht_##name *ht, uint##klen ## _t k \
        ) { \
            uint##klen ## _t e; \
            hash##bits ## _t i = hash_u##klen ## _into_h##bits(k); \
            hash##bits ## _t o = 0; \
            \
            while (test_bit(i, ht->bmap)) { \
                /* in case someone acquired the bit but has not set it yet */ \
                do { \
                    e = atomic##klen ## _read(&(ht->cell[i].key)); \
                } while (!e); \
                \
                /* check existence */ \
                if (e == k) { \
                    return &(ht->cell[i].val); \
                } \
                \
                /* move on */ \
                i = (i + 1) % (1 << bits); \
                BUG_ON((++o) == (1 << bits)); \
            } \
            \
            return NULL; \
        } \
        \
        static inline void \
        ht_##name ## _for_each( \
            struct __ht_##name *ht, \
            void (*func)( \
                uint##klen ## _t key, struct name *val, void *arg \
            ), \
            void *arg \
        ) { \
            hash##bits ## _t t; \
            hash##bits ## _t i = find_first_bit(ht->bmap, 1 << bits); \
            /* break if there is no bit set in the map */ \
            if (unlikely(i == (1 << bits))) { \
                return; \
            } \
            \
            while (true) { \
                t = i; \
                func( \
                    atomic##klen ## _read(&(ht->cell[i].key)), \
                    &ht->cell[i].val, \
                    arg \
                ); \
                i = find_next_bit(ht->bmap, (1 << bits), i + 1); \
                \
                if (i == (1 << bits) || i <= t) { \
                    break; \
                } \
            } \
        } \

#endif /* _DART_HASH_H_ */
