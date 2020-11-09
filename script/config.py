import os
import sys
import multiprocessing

from config_option import Option

# system tuning
sys.setrecursionlimit(10000)


# option settings
def OPTION() -> Option:
    return Option()


# project configs
PROJ_PATH = os.path.abspath(os.path.join(__file__, '..', '..'))

# system configs
NCPU = multiprocessing.cpu_count()

if NCPU <= 64:
    FUZZ_INSTANCE_MAX = 62
elif NCPU <= 128:
    FUZZ_INSTANCE_MAX = 126
else:
    FUZZ_INSTANCE_MAX = 254

# docker configs
DOCKER_PATH = os.path.join(PROJ_PATH, 'docker')
DOCKER_REPO = 'racer'
DOCKER_MPTR = '/racer'
DOCKER_MARK = 'IN_RACER_DOCKER'

DOCKER_TMP_SIZE_IN_MB = 128 * (FUZZ_INSTANCE_MAX + 2) + 512
DOCKER_SHM_SIZE_IN_MB = 128 * (FUZZ_INSTANCE_MAX + 2) + 512

DOCKERIZED = DOCKER_MARK in os.environ

# studio configs
STUDIO_PATH = os.path.join(
    PROJ_PATH, 'studio', 'dock' if DOCKERIZED else 'host'
)

STUDIO_BUILD = os.path.join(STUDIO_PATH, 'build')
STUDIO_STORE = os.path.join(STUDIO_PATH, 'store')

STUDIO_MARKS = os.path.join(STUDIO_PATH, 'marks')
STUDIO_WORKS = os.path.join(STUDIO_PATH, 'works')

STUDIO_BATCH = os.path.join(STUDIO_PATH, 'batch')

# asset configs
ASSET_PATH = os.path.join(PROJ_PATH, 'studio', 'asset')
ASSET_SYSCALL = os.path.join(ASSET_PATH, 'syscall')

# script configs
SCRIPT_PATH = os.path.join(PROJ_PATH, 'script')

# pass configs
PASS_PATH = os.path.join(PROJ_PATH, 'pass')

# linux configs
LINUX_VERSION = 'v5.4-rc5'
LINUX_MOD_MAIN_MAX = 8
LINUX_MOD_DEPS_MAX = 32

# virtex machine configs
VIRTEX_SMP = 4
VIRTEX_MEM_SIZE = 16 * (1 << 10)

# virtex execute configs
VIRTEX_SHM_DIR = '/dev/shm'
VIRTEX_TMP_DIR = '/tmp'

# virtex sharing configs
VIRTEX_DISK_IMG_NAME = 'disk.img'
VIRTEX_LEDGER_NAME = 'ledger'

# virtex multi-threading configs
VIRTEX_THREAD_NUM = 4

# timeout
VIRTEX_TIMEOUT = 120


# instmem and ivshmem configs (all unit in MB)

#
# |  4 MB | -> header
# |  4 MB | -> cov_cfg_edge
# |  4 MB | -> cov_dfg_edge
# |  4 MB | -> cov_alias_inst
# |240 MB | -> (reserved)
#
# --------- (256 MB) header
#
# |  2 MB | -> metadata (userspace: mount options, etc)
# | 48 MB | -> bytecode (userspace: program to interpret)
# | 12 MB | -> strace   (userspace: syscall logs)
# |  2 MB | -> rtinfo   (kernel   : runtime info)
# | 64 MB | -> rtrace   (kernel   : racing access logs)
#
# --------- (128 MB) instance-specific workspace
#

def _MB(i: int) -> int:
    return i * (1 << 20)


INSTMEM_OFFSET_METADATA = 0
INSTMEM_OFFSET_BYTECODE = INSTMEM_OFFSET_METADATA + _MB(2)
INSTMEM_OFFSET_STRACE = INSTMEM_OFFSET_BYTECODE + _MB(48)
INSTMEM_OFFSET_RTINFO = INSTMEM_OFFSET_STRACE + _MB(12)
INSTMEM_OFFSET_RTRACE = INSTMEM_OFFSET_RTINFO + _MB(2)
INSTMEM_SIZE = INSTMEM_OFFSET_RTRACE + _MB(64)

IVSHMEM_OFFSET_HEADER = 0
IVSHMEM_OFFSET_COV_CFG_EDGE = IVSHMEM_OFFSET_HEADER + _MB(4)
IVSHMEM_OFFSET_COV_DFG_EDGE = IVSHMEM_OFFSET_COV_CFG_EDGE + _MB(4)
IVSHMEM_OFFSET_COV_ALIAS_INST = IVSHMEM_OFFSET_COV_DFG_EDGE + _MB(4)
IVSHMEM_OFFSET_RESERVED = IVSHMEM_OFFSET_COV_ALIAS_INST + _MB(4)
IVSHMEM_OFFSET_INSTANCES = IVSHMEM_OFFSET_RESERVED + _MB(240)
IVSHMEM_SIZE = IVSHMEM_OFFSET_INSTANCES + INSTMEM_SIZE * FUZZ_INSTANCE_MAX


def INSTMEM_OFFSET(instance: int) -> int:
    return IVSHMEM_OFFSET_INSTANCES + INSTMEM_SIZE * instance


# runtime info
BITMAP_COV_CFG_EDGE_SIZE = (1 << 24) // 8
BITMAP_COV_DFG_EDGE_SIZE = (1 << 24) // 8
BITMAP_COV_ALIAS_INST_SIZE = (1 << 24) // 8

OUTPUT_LEDGER_SIZE = _MB(2048)

# refresh rate
REFRESH_RATE = 20

# iteration limits
TTL_REP_LOOP = 5
TTL_MOD_LOOP = 10
TTL_EXT_LOOP = 10
TTL_MERGE_LOOP = 10
TTL_CHECK_LOOP = 20

# probe configs
PROBE_SLICE_LEN = 1000

# validation configs
VALIDATION_WORKER_PATH = os.path.join(VIRTEX_TMP_DIR, 'racer-validation')
VALIDATION_FAILED_PATH = os.path.join(VIRTEX_TMP_DIR, 'racer-error')

# test configs
TEST_RESULT_PATH = os.path.join(VIRTEX_TMP_DIR, 'racer-test')
