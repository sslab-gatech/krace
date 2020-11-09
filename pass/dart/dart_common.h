#ifndef _DART_COMMON_H_
#define _DART_COMMON_H_

#include <linux/kernel.h>
#include <linux/syscalls.h>

#include <linux/bug.h>
#include <linux/types.h>
#include <linux/slab.h>

#include <linux/hash.h>
#include <linux/hashtable.h>

#include <linux/preempt.h>
#include <linux/spinlock.h>

#include <linux/fs.h>
#include <linux/file.h>
#include <linux/fdtable.h>

#include <linux/delay.h>

#include "dart_kernel.h"

extern long dart_iseq;
extern char *dart_shared;
extern char *dart_private;
extern char *dart_reserved;

/* ivshmem-mapped memory
 *
 * |  4 MB | -> header
 * |  4 MB | -> cov_cfg_edge
 * |  4 MB | -> cov_dfg_edge
 * |  4 MB | -> cov_alias_inst
 * |240 MB | -> (reserved)
 *
 * --------- (256 MB) header
 *
 * |  2 MB | -> metadata (userspace: mount options, etc)
 * | 48 MB | -> bytecode (userspace: program to interpret)
 * | 12 MB | -> strace   (userspace: syscall logs)
 * |  2 MB | -> rtinfo   (kernel   : runtime info)
 * | 64 MB | -> rtrace   (kernel   : racing access logs)
 *
 * --------- (128 MB) instance
 */

#define _MB(i) (i * (1ul << 20))

#define INSTMEM_OFFSET_USER             0
#define INSTMEM_OFFSET_METADATA         0
#define INSTMEM_OFFSET_BYTECODE         (INSTMEM_OFFSET_METADATA + _MB(2))
#define INSTMEM_OFFSET_STRACE           (INSTMEM_OFFSET_BYTECODE + _MB(48))
#define INSTMEM_SIZE_USER               (INSTMEM_OFFSET_STRACE + _MB(12))

#define INSTMEM_OFFSET_KERN             (INSTMEM_OFFSET_USER + INSTMEM_SIZE_USER)
#define INSTMEM_OFFSET_RTINFO           0
#define INSTMEM_OFFSET_RTRACE           (INSTMEM_OFFSET_RTINFO + _MB(2))
#define INSTMEM_SIZE_KERN               (INSTMEM_OFFSET_RTRACE + _MB(64))

#define INSTMEM_SIZE                    (INSTMEM_SIZE_USER + INSTMEM_SIZE_KERN)

#define IVSHMEM_OFFSET_HEADER           0
#define IVSHMEM_OFFSET_COV_CFG_EDGE     (IVSHMEM_OFFSET_HEADER + _MB(4))
#define IVSHMEM_OFFSET_COV_DFG_EDGE     (IVSHMEM_OFFSET_COV_CFG_EDGE + _MB(4))
#define IVSHMEM_OFFSET_COV_ALIAS_INST   (IVSHMEM_OFFSET_COV_DFG_EDGE + _MB(4))
#define IVSHMEM_OFFSET_RESERVED         (IVSHMEM_OFFSET_COV_ALIAS_INST + _MB(4))
#define IVSHMEM_OFFSET_INSTANCES        (IVSHMEM_OFFSET_RESERVED + _MB(240))

#define INSTMEM_OFFSET(i)               (IVSHMEM_OFFSET_INSTANCES + INSTMEM_SIZE * (i))
#define IVSHMEM_SHARED                  IVSHMEM_OFFSET_RESERVED

/* specify the dart syscall */
#define CMD_DART_LAUNCH                 1
#define CMD_DART_FINISH                 2
#define CMD_DART_CTXT_SYSCALL_START     3
#define CMD_DART_CTXT_SYSCALL_EXIT      4

/* printing */
#define _dart_pr(level, fmt, ...) \
        printk(level "[DART] " fmt "\n", ##__VA_ARGS__)

#define dart_pr_debug(fmt, ...)     _dart_pr(KERN_INFO, fmt, ##__VA_ARGS__)
#define dart_pr_info(fmt, ...)      _dart_pr(KERN_NOTICE, fmt, ##__VA_ARGS__)
#define dart_pr_warn(fmt, ...)      _dart_pr(KERN_WARNING, fmt, ##__VA_ARGS__)
#define dart_pr_err(fmt, ...)       _dart_pr(KERN_ERR, fmt, ##__VA_ARGS__)

/* bugging */
#ifdef DART_LOGGING
#define DART_BUG() \
        do { \
            dart_ledger_transfer_ro_reserve(g_ledger, g_reserve_ledger); \
            BUG(); \
        } while (0)
#define DART_BUG_ON(condition) \
        do { \
            if (unlikely(condition)) \
                dart_ledger_transfer_ro_reserve(g_ledger, g_reserve_ledger); \
                BUG(); \
            \
        } while (0)
#else
#define DART_BUG                    BUG
#define DART_BUG_ON                 BUG_ON
#endif

/* memory shadowing */
#define SHADOW_SIZE                 8
#define ADDR_TO_SHADOW(addr)        ((addr) & ~(0x7ul))
#define ADDR_TO_OFFSET(addr)        ((addr) & 0x7ul)

#endif /* _DART_COMMON_H_ */
