from typing import BinaryIO, NamedTuple, List, Dict, Set, Tuple, Optional, Union

import struct
import logging

from enum import Enum, IntEnum, auto
from collections import defaultdict
from dataclasses import dataclass

from pkg_linux import Package_LINUX
from racer_parse_compile_data import CompileDatabase, ValueFunc, ValueInst

from util import read_source_location

import config


# utils
def _tab(stack: List[ValueFunc], mark: str = '  ') -> str:
    return mark * (len(stack) - 1)


# dart constants
DART_LOCK_ID_RCU = 1


class LogType(IntEnum):
    _BEGIN_OF_ENUM = 0

    SYS_LAUNCH = auto()
    SYS_FINISH = auto()

    MARK_V0 = auto()
    MARK_V1 = auto()
    MARK_V2 = auto()
    MARK_V3 = auto()

    CTXT_SYSCALL_ENTER = auto()
    CTXT_SYSCALL_EXIT = auto()

    CTXT_RCU_ENTER = auto()
    CTXT_RCU_EXIT = auto()

    CTXT_WORK_ENTER = auto()
    CTXT_WORK_EXIT = auto()

    CTXT_TASK_ENTER = auto()
    CTXT_TASK_EXIT = auto()

    CTXT_TIMER_ENTER = auto()
    CTXT_TIMER_EXIT = auto()

    CTXT_KRUN_ENTER = auto()
    CTXT_KRUN_EXIT = auto()

    CTXT_BLOCK_ENTER = auto()
    CTXT_BLOCK_EXIT = auto()

    CTXT_IPI_ENTER = auto()
    CTXT_IPI_EXIT = auto()

    CTXT_CUSTOM_ENTER = auto()
    CTXT_CUSTOM_EXIT = auto()

    EXEC_PAUSE = auto()
    EXEC_RESUME = auto()

    EXEC_BACKGROUND = auto()
    EXEC_FOREGROUND = auto()

    EXEC_FUNC_ENTER = auto()
    EXEC_FUNC_EXIT = auto()

    ASYNC_RCU_REGISTER = auto()

    ASYNC_WORK_REGISTER = auto()
    ASYNC_WORK_CANCEL = auto()
    ASYNC_WORK_ATTACH = auto()

    ASYNC_TASK_REGISTER = auto()
    ASYNC_TASK_CANCEL = auto()

    ASYNC_TIMER_REGISTER = auto()
    ASYNC_TIMER_CANCEL = auto()
    ASYNC_TIMER_ATTACH = auto()

    ASYNC_KRUN_REGISTER = auto()

    ASYNC_BLOCK_REGISTER = auto()

    ASYNC_IPI_REGISTER = auto()

    ASYNC_CUSTOM_REGISTER = auto()
    ASYNC_CUSTOM_ATTACH = auto()

    EVENT_QUEUE_ARRIVE = auto()
    EVENT_QUEUE_NOTIFY = auto()

    EVENT_WAIT_ARRIVE = auto()
    EVENT_WAIT_NOTIFY_ENTER = auto()
    EVENT_WAIT_NOTIFY_EXIT = auto()
    EVENT_WAIT_PASS = auto()

    EVENT_SEMA_ARRIVE = auto()
    EVENT_SEMA_NOTIFY_ENTER = auto()
    EVENT_SEMA_NOTIFY_EXIT = auto()
    EVENT_SEMA_PASS = auto()

    COV_CFG = auto()

    MEM_STACK_PUSH = auto()
    MEM_STACK_POP = auto()

    MEM_HEAP_ALLOC = auto()
    MEM_HEAP_FREE = auto()

    MEM_PERCPU_ALLOC = auto()
    MEM_PERCPU_FREE = auto()

    MEM_READ = auto()
    MEM_WRITE = auto()

    SYNC_GEN_LOCK = auto()
    SYNC_GEN_UNLOCK = auto()

    SYNC_SEQ_LOCK = auto()
    SYNC_SEQ_UNLOCK = auto()

    SYNC_RCU_LOCK = auto()
    SYNC_RCU_UNLOCK = auto()

    ORDER_PS_PUBLISH = auto()
    ORDER_PS_SUBSCRIBE = auto()

    ORDER_OBJ_DEPOSIT = auto()
    ORDER_OBJ_CONSUME = auto()

    _END_OF_ENUM = auto()


class CtxtType(Enum):
    TASK = 1
    SOFTIRQ = 2
    HARDIRQ = 3
    NMI = 4

    @classmethod
    def from_ptid(cls, ptid: int) -> 'CtxtType':
        if ptid & ((1 << 8) << 16):
            return CtxtType.SOFTIRQ

        if ptid & ((1 << 9) << 16):
            return CtxtType.HARDIRQ

        if ptid & ((1 << 10) << 16):
            return CtxtType.NMI

        return CtxtType.TASK


class ExecUnitType(Enum):
    ROOT = auto()
    SYSCALL = auto()
    RCU = auto()
    WORK = auto()
    TASK = auto()
    TIMER = auto()
    KRUN = auto()
    BLOCK = auto()
    IPI = auto()
    CUSTOM = auto()
    WAIT_NOTIFY = auto()
    SEMA_NOTIFY = auto()


class MemType(Enum):
    STACK = auto()
    HEAP = auto()
    PERCPU = auto()
    GLOBAL = auto()


class LockType(Enum):
    GEN = auto()
    RCU = auto()
    SEQ = auto()


class QueueType(Enum):
    WQ = auto()


class OrderType(Enum):
    RCU = auto()
    OBJ = auto()


@dataclass
class ExecUnit(object):
    ptid: int
    ctxt: Optional[int]
    base: Optional['ExecUnit']
    seq: int
    clk: int
    deps: Dict[int, 'ExecUnit']

    @classmethod
    def create(cls, ptid: int) -> 'ExecUnit':
        return ExecUnit(
            ptid=ptid,
            ctxt=None,
            base=None,
            seq=0,
            clk=0,
            deps={},
        )

    def clone(self) -> 'ExecUnit':
        return ExecUnit(
            ptid=self.ptid,
            ctxt=self.ctxt,
            base=self.base,
            seq=self.seq,
            clk=self.clk,
            deps={k: v for k, v in self.deps.items()},
        )

    def coordinate(self) -> str:
        return '{}-{}-{}'.format(self.ptid, self.seq, self.clk)

    def _happens_before_in_task(self, unit: 'ExecUnit') -> bool:
        """
        returns whether this --> happens-before --> unit
        """
        if self.seq < unit.seq:
            return True

        if self.seq == unit.seq and self.clk <= unit.clk:
            return True

        return False

    def _happens_before(self, unit: 'ExecUnit', hist: Dict[str, bool]) -> bool:
        """
        returns whether this --> happens-before --> unit
        """
        # return cached results
        cord = unit.coordinate()
        if cord in hist:
            return hist[cord]

        # default to not happens-before if we cannot establish the ordering
        retv = None  # type: Optional[bool]

        # same-task comparison is strictly ordered
        if self.ptid == unit.ptid:
            retv = self._happens_before_in_task(unit)

        # if A --> B's base, then A --> B
        if retv is None:
            if unit.base is not None:
                if self._happens_before(unit.base, hist):
                    retv = True

        # if A --> B's dep, then A --> B
        if retv is None:
            for dep in unit.deps.values():
                if self._happens_before(dep, hist):
                    retv = True
                    break

        # default to false
        if retv is None:
            retv = False

        # cache the result before return it
        hist[cord] = retv
        return retv

    def happens_before(self, unit: 'ExecUnit') -> bool:
        return self._happens_before(unit, {})

    def add_dep(self, dep: 'ExecUnit') -> None:
        if dep.ptid not in self.deps:
            self.deps[dep.ptid] = dep

        elif self.deps[dep.ptid]._happens_before_in_task(dep):
            self.deps[dep.ptid] = dep


class LogMeta(NamedTuple):
    ptid: int
    info: int
    hval: int

    @property
    def ctxt(self) -> CtxtType:
        return CtxtType.from_ptid(self.ptid)


class SyncInfo(NamedTuple):
    info: int

    @property
    def is_rw(self) -> bool:
        return (self.info & (1 << 2)) != 0

    @property
    def is_try(self) -> bool:
        return (self.info & (1 << 1)) != 0

    @property
    def is_succ(self) -> bool:
        return (self.info & (1 << 0)) != 0


class LockSet(NamedTuple):
    locks_r: Set[int]
    locks_w: Set[int]


class _LockMapImpl(object):

    def __init__(self) -> None:
        self.locks = defaultdict(int)  # type: Dict[int, int]

    def add_lock(self, lock: int) -> int:
        """
        return  0: lock does not exist previously
        return >0: lock exists already with depth
        """
        depth = self.locks[lock]
        assert depth >= 0

        self.locks[lock] = depth + 1
        return depth

    def del_lock(self, lock: int) -> int:
        """
        return  0: lock does not exist previously
        return  1: lock exists before but will be removed
        return >1: lock exists before and depth will decrement
        """
        depth = self.locks[lock]
        assert depth >= 0

        if depth <= 1:
            del self.locks[lock]
        else:
            self.locks[lock] = depth - 1

        return depth

    def lockset(self) -> Set[int]:
        return set(self.locks.keys())


class LockMap(object):

    def __init__(self) -> None:
        self.locks_r = _LockMapImpl()
        self.locks_w = _LockMapImpl()

    def add_lock_r(self, lock: int) -> int:
        return self.locks_r.add_lock(lock)

    def del_lock_r(self, lock: int) -> int:
        return self.locks_r.del_lock(lock)

    def add_lock_w(self, lock: int) -> int:
        return self.locks_w.add_lock(lock)

    def del_lock_w(self, lock: int) -> int:
        return self.locks_w.del_lock(lock)

    def lockset_r(self) -> Set[int]:
        return self.locks_r.lockset().union(self.locks_w.lockset())

    def lockset_w(self) -> Set[int]:
        return self.locks_w.lockset()


class _TranInfo(object):

    def __init__(self) -> None:
        self.begin = None  # type: Optional[ExecUnit]
        self.retry = None  # type: Optional[ExecUnit]


class _TranMapImpl(object):

    def __init__(self) -> None:
        self.trans = defaultdict(_TranInfo)  # type: Dict[int, _TranInfo]

    def add_tran(self, tran: int, unit: ExecUnit) -> Optional[ExecUnit]:
        """
        return <None>: first addition
        return <unit>: location of the last transaction retry
        """
        prior = self.trans[tran].retry
        self.trans[tran].begin = unit
        self.trans[tran].retry = None
        return prior

    def del_tran(self, tran: int, unit: ExecUnit) -> Optional[ExecUnit]:
        """
        return <None>: no prior transaction found
        return <unit>: location of the transaction begin
        """
        prior = self.trans[tran].begin
        self.trans[tran].retry = unit
        return prior

    def has_tran(self, tran: int) -> bool:
        return tran in self.trans

    def lockset_candidates(self) -> Set[int]:
        # NOTE: this is just candidate lockset, not actual lockset
        return set(self.trans.keys())

    def pending(self) -> Set[int]:
        return {i for i, v in self.trans.items() if v.retry is None}


class TranMap(object):

    def __init__(self) -> None:
        self.trans_r = _TranMapImpl()
        self.locks_w = _LockMapImpl()

    def add_tran_r(self, tran: int, unit: ExecUnit) -> Optional[ExecUnit]:
        return self.trans_r.add_tran(tran, unit)

    def del_tran_r(self, tran: int, unit: ExecUnit) -> Optional[ExecUnit]:
        return self.trans_r.del_tran(tran, unit)

    def has_tran_r(self, tran: int) -> bool:
        return self.trans_r.has_tran(tran)

    def add_lock_w(self, lock: int) -> int:
        return self.locks_w.add_lock(lock)

    def del_lock_w(self, lock: int) -> int:
        return self.locks_w.del_lock(lock)

    def transet_r(self) -> Set[int]:
        return self.trans_r.lockset_candidates()

    def transet_w(self) -> Set[int]:
        return self.locks_w.lockset()


@dataclass
class MemAccess(object):
    hval: int
    unit: ExecUnit
    sync_locks: Set[int]
    sync_trans: Set[int]


class MemCell(object):

    def __init__(self) -> None:
        self.readers = {}  # type: Dict[int, List[MemAccess]]
        self.writers = {}  # type: Dict[int, List[MemAccess]]


class DartAssertFailure(Exception):

    def __init__(self, reason: str, ledger: str) -> None:
        self.reason = reason
        self.ledger = ledger


@dataclass
class TaskState(object):
    # context
    unit: ExecUnit
    nseq: int
    last_unit: Optional[ExecUnit]

    # call stack
    stack: List[ValueFunc]
    stack_mem: Dict[int, int]

    # sync
    sync_locks: LockMap
    sync_trans: TranMap

    # coverage
    last_blkid: int

    @classmethod
    def create(cls, ptid: int) -> 'TaskState':
        return TaskState(
            unit=ExecUnit.create(ptid),
            nseq=0,
            last_unit=None,
            stack=[],
            stack_mem={},
            sync_locks=LockMap(),
            sync_trans=TranMap(),
            last_blkid=0,
        )


@dataclass
class AsyncSlot(object):
    func: int
    unit: ExecUnit
    others: List[ExecUnit]
    serving: int
    host: Optional[ExecUnit]


@dataclass
class EventSlot(object):
    func: int
    unit: ExecUnit
    servers: Dict[int, Tuple[int, ExecUnit]]
    host: Optional[ExecUnit]


@dataclass
class QueueSlot(object):
    units: Dict[int, ExecUnit]


@dataclass
class OrderSlot(object):
    objv: int
    unit: ExecUnit


class RaceAlias(NamedTuple):
    src: int
    dst: int


class ExecAnalyzer(object):

    def __init__(self, compdb: CompileDatabase) -> None:
        # deps
        self.compdb = compdb

        # runtime states
        self.main_ptid = 0
        self.tasks = {}  # type: Dict[int, TaskState]

        self.mem_sizes_heap = {}  # type: Dict[int, int]
        self.mem_heaps = {}  # type: Dict[int, int]
        self.mem_sizes_pcpu = {}  # type: Dict[int, int]
        self.mem_pcpus = {}  # type: Dict[int, int]

        self.async_slots = {}  # type: Dict[int, AsyncSlot]
        self.event_slots = {}  # type: Dict[int, EventSlot]
        self.queue_slots = {}  # type: Dict[int, QueueSlot]
        self.order_slots = {}  # type: Dict[int, OrderSlot]

        self.cells = {}  # type: Dict[int, MemCell]

        self.races = {}  # type: Dict[RaceAlias, int]

        # COV
        self.cov_cfg_edge_incr = 0
        self.cov_dfg_edge_incr = 0
        self.cov_alias_inst_incr = 0

        # console
        self.console = []  # type: List[str]

        # statistics
        self.stats = {}  # type: Dict[int, Dict[LogType, int]]

        # create task 0 (for holding system information)
        self.tasks[0] = TaskState.create(0)

    # utils
    def _assert(self, cond: bool, message: str, abort: bool = True) -> None:
        if cond:
            return

        # error reporting
        logging.error('[DART] ' + message)
        if not abort:
            return

        raise DartAssertFailure(message, self.ledger)

    def _record(self, message: str, show: bool = False) -> None:
        self.console.append(message)
        if show:
            print(message)

    def _record_divider(self) -> None:
        self._record('-' * 80)

    # record warning
    def _record_warning(
            self, meta: LogMeta, task: TaskState, msg: str
    ) -> None:
        self._record(
            '{}[!] <{}-{}> {} [{}]: {}'.format(
                _tab(task.stack),
                meta.ptid, task.unit.seq,
                meta.ctxt.name, meta.hval,
                msg
            )
        )

    # record info
    def _record_ctxt_init(
            self, meta: LogMeta, task: TaskState, kind: str
    ) -> None:
        self._record(
            '{}|=> <{}-{}> {}: {} {}'.format(
                _tab(task.stack),
                meta.ptid, task.unit.seq, meta.ctxt.name, meta.hval, kind
            ),
        )

    def _record_ctxt_fini(
            self, meta: LogMeta, task: TaskState, kind: str
    ) -> None:
        self._record(
            '{}|<= <{}-{}> {}: {} {}'.format(
                _tab(task.stack),
                meta.ptid, task.unit.seq, meta.ctxt.name, meta.hval, kind
            ),
        )

    def _record_exec_pause(
            self, meta: LogMeta, task: TaskState
    ) -> None:
        self._record(
            '{}|-X <{}-{}> {}'.format(
                _tab(task.stack),
                meta.ptid, task.unit.seq, meta.hval
            ),
        )

    def _record_exec_resume(
            self, meta: LogMeta, task: TaskState
    ) -> None:
        self._record(
            '{}|X- <{}-{}> {}'.format(
                _tab(task.stack),
                meta.ptid, task.unit.seq, meta.hval
            ),
        )

    def _record_func_init(
            self, meta: LogMeta, task: TaskState, func: ValueFunc
    ) -> None:
        self._record(
            '{}|-> <{}-{}> {}'.format(
                _tab(task.stack),
                meta.ptid, task.unit.seq,
                func.name
            ),
        )

    def _record_func_fini(
            self, meta: LogMeta, task: TaskState, func: ValueFunc
    ) -> None:
        self._record(
            '{}|<- <{}-{}> {}'.format(
                _tab(task.stack),
                meta.ptid, task.unit.seq,
                func.name
            ),
        )

    def _record_async_register(
            self, meta: LogMeta, task: TaskState, func: int, kind: str
    ) -> None:
        self._record(
            '{}<-> <{}-{}> {} [{}] {}'.format(
                _tab(task.stack),
                meta.ptid, task.unit.seq, meta.hval,
                func, kind
            )
        )

    def _record_async_cancel(
            self, meta: LogMeta, task: TaskState, func: int, kind: str
    ) -> None:
        self._record(
            '{}>-< <{}-{}> {} [{}] {}'.format(
                _tab(task.stack),
                meta.ptid, task.unit.seq, meta.hval,
                func, kind
            )
        )

    def _record_async_attach(
            self, meta: LogMeta, task: TaskState, func: int, kind: str
    ) -> None:
        self._record(
            '{}>-> <{}-{}> {} [{}] {}'.format(
                _tab(task.stack),
                meta.ptid, task.unit.seq, meta.hval,
                func, kind
            )
        )

    def _record_event_arrive(
            self, meta: LogMeta, task: TaskState, kind: str
    ) -> None:
        self._record(
            '{}<+> <{}-{}> {} {}'.format(
                _tab(task.stack),
                meta.ptid, task.unit.seq, meta.hval,
                kind
            )
        )

    def _record_event_pass(
            self, meta: LogMeta, task: TaskState, kind: str
    ) -> None:
        self._record(
            '{}>+< <{}-{}> {} {}'.format(
                _tab(task.stack),
                meta.ptid, task.unit.seq, meta.hval,
                kind
            )
        )

    def _record_cov_edge(
            self, meta: LogMeta, task: TaskState
    ) -> None:
        self._record(
            '{}--- <{}-{}> {}'.format(
                _tab(task.stack),
                meta.ptid, task.unit.seq, meta.hval
            )
        )

    def _record_mem_add(
            self,
            meta: LogMeta, task: TaskState,
            addr: int, size: int, kind: str
    ) -> None:
        self._record(
            '{}+++ <{}-{}> {}+ {} [{}]'.format(
                _tab(task.stack),
                meta.ptid, task.unit.seq,
                kind, hex(addr), size
            )
        )

    def _record_mem_del(
            self,
            meta: LogMeta, task: TaskState,
            addr: int, size: int, kind: str
    ) -> None:
        self._record(
            '{}+++ <{}-{}> {}- {} [{}]'.format(
                _tab(task.stack),
                meta.ptid, task.unit.seq,
                kind, hex(addr), size
            )
        )

    def _record_mem_reader(
            self, meta: LogMeta, task: TaskState, addr: int, size: int
    ) -> None:
        self._record(
            '{}+++ <{}-{}> R: {} [{}], {}'.format(
                _tab(task.stack),
                meta.ptid, task.unit.seq,
                hex(addr), size, meta.hval
            )
        )

    def _record_mem_writer(
            self, meta: LogMeta, task: TaskState, addr: int, size: int
    ) -> None:
        self._record(
            '{}+++ <{}-{}> W: {} [{}], {}'.format(
                _tab(task.stack),
                meta.ptid, task.unit.seq,
                hex(addr), size, meta.hval
            )
        )

    def _record_sync_lock_acquire(
            self, meta: LogMeta, task: TaskState, rw: str, lock: int, kind: str
    ) -> None:
        self._record(
            '{}|+| <{}-{}> {}: {} {}'.format(
                _tab(task.stack),
                meta.ptid, task.unit.seq,
                rw, hex(lock), kind
            )
        )

    def _record_sync_lock_release(
            self, meta: LogMeta, task: TaskState, rw: str, lock: int, kind: str
    ) -> None:
        self._record(
            '{}|-| <{}-{}> {}: {} {}'.format(
                _tab(task.stack),
                meta.ptid, task.unit.seq,
                rw, hex(lock), kind
            )
        )

    def _record_queue_prefix(
            self, meta: LogMeta, task: TaskState, kind: str
    ) -> None:
        self._record(
            '{}+=> <{}-{}> {} {}'.format(
                _tab(task.stack),
                meta.ptid, task.unit.seq,
                hex(meta.hval), kind
            )
        )

    def _record_queue_suffix(
            self, meta: LogMeta, task: TaskState, kind: str
    ) -> None:
        self._record(
            '{}<=+ <{}-{}> {} {}'.format(
                _tab(task.stack),
                meta.ptid, task.unit.seq,
                hex(meta.hval), kind
            )
        )

    def _record_order_prefix(
            self, meta: LogMeta, task: TaskState, addr: int, kind: str
    ) -> None:
        self._record(
            '{}+-> <{}-{}> {} {}'.format(
                _tab(task.stack),
                meta.ptid, task.unit.seq,
                hex(addr), kind
            )
        )

    def _record_order_suffix(
            self, meta: LogMeta, task: TaskState, addr: int, kind: str
    ) -> None:
        self._record(
            '{}<-+ <{}-{}> {} {}'.format(
                _tab(task.stack),
                meta.ptid, task.unit.seq,
                hex(addr), kind
            )
        )

    # record race
    def _record_race(
            self, task: TaskState, a1: MemAccess, a2: MemAccess, addr: int
    ) -> None:
        self._record(
            '{}[*] RACE <{}-{}-{} |=| {}-{}-{}> [{}:{}] {}'.format(
                _tab(task.stack),
                a1.unit.ptid, a1.unit.seq, a1.unit.clk,
                a2.unit.ptid, a2.unit.seq, a2.unit.clk,
                a1.hval, a2.hval,
                hex(addr)
            )
        )

        inst_src = self.compdb.insts[a1.hval]
        self._record(
            '{}[*] SRC: [{}-{}-{}] <{}> {}: {} [{}] |{}| {}'.format(
                _tab(task.stack),
                a1.unit.ptid, a1.unit.seq, a1.unit.clk,
                CtxtType.from_ptid(a1.unit.ptid).name,
                a1.hval,
                inst_src.get_parent().get_parent().name,
                inst_src.get_locs(),
                self._load_source(inst_src),
                inst_src.text
            )
        )

        inst_dst = self.compdb.insts[a2.hval]
        self._record(
            '{}[*] DST: [{}-{}-{}] <{}> {}: {} [{}] |{}| {}'.format(
                _tab(task.stack),
                a2.unit.ptid, a2.unit.seq, a2.unit.clk,
                CtxtType.from_ptid(a2.unit.ptid).name,
                a2.hval,
                inst_dst.get_parent().get_parent().name,
                inst_dst.get_locs(),
                self._load_source(inst_dst),
                inst_dst.text
            )
        )

        # save it to race alias
        pair = RaceAlias(a1.hval, a2.hval)
        if pair in self.races:
            self.races[pair] += 1
        else:
            self.races[pair] = 1

    # load source
    def _load_source(self, inst: ValueInst) -> str:
        return ' @@ '.join([
            read_source_location(config.PROJ_PATH + '/' + loc)
            for loc in inst.info
        ])

    # iterate over the logs
    def process_log(self, f: BinaryIO) -> Tuple[int, int]:
        entry_num, entry_cur = struct.unpack('QQ', f.read(16))
        logging.debug('[DART] log recorded: {}, size: {}'.format(
            entry_num, entry_cur
        ))

        return entry_num, entry_cur

    # SYS
    def log_sys_launch(self, meta: LogMeta) -> None:
        self._assert(
            meta.ptid > 0,
            'launched with ptid <=0'
        )
        self._assert(
            self.main_ptid == 0,
            'launched multiple times'
        )

        self.main_ptid = meta.ptid

    def log_sys_finish(self, meta: LogMeta) -> None:
        self._assert(
            meta.ptid > 0,
            'terminated with ptid 0'
        )
        self._assert(
            self.main_ptid == meta.ptid,
            'terminated with a different ptid'
        )

        self.main_ptid = -1

    # CTXT (generics)
    def _log_ctxt_enter_get_task(
            self, meta: LogMeta, slot: Optional[Union[AsyncSlot, EventSlot]]
    ) -> TaskState:
        # get the task state (steal it if necessary)
        if meta.ptid not in self.tasks:
            # first time seeing the ptid, create a new task
            task = TaskState.create(meta.ptid)
            self.tasks[meta.ptid] = task
        else:
            task = self.tasks[meta.ptid]
            if slot is None:
                # this is a direct context enter, so ctxt must be clean
                self._assert(
                    task.unit.ctxt is None,
                    'task {}-{}: context is not cleared on entry - '
                    '[ctxt: {}, hval: {}]'.format(
                        meta.ptid, task.unit.seq, task.unit.ctxt, meta.hval
                    )
                )
            elif task.unit.ctxt is not None:
                # existing ctxt is tracing, we are stealing the task
                slot.host = task.unit.clone()
                task.unit = ExecUnit.create(meta.ptid)

                # if we steal from the parent, add the parent into our deps
                task.unit.add_dep(slot.host)
            else:
                # existing ctxt has stopped, we are free to re-use it
                slot.host = None

        # roll over the execution unit count
        self._assert(
            task.unit.clk == 0,
            'task {}-{}: unit clock is not zero on entry - '
            '[hval: {}, clock: {}]'.format(
                meta.ptid, task.unit.seq, meta.hval, task.unit.clk
            )
        )

        # TODO (it may be a bad choice to add last unit as dependency)
        if task.last_unit is not None:
            task.unit.add_dep(task.last_unit)

        # initialize the basics
        task.unit.clk = 0  # (actually, we already asserted...)
        task.unit.seq = task.nseq
        task.nseq += 1

        # mark the start of the context
        task.unit.ctxt = meta.hval

        # return the task
        return task

    def _log_ctxt_enter_put_task(
            self, meta: LogMeta, task: TaskState, kind: str
    ) -> None:
        # record
        self._record_ctxt_init(meta, task, kind)

    def _log_ctxt_exit_get_task(self, meta: LogMeta) -> TaskState:
        self._assert(
            meta.ptid in self.tasks,
            'task {}-X: context existing without entering - '
            '[hval: {}]'.format(
                meta.ptid, meta.hval
            )
        )

        task = self.tasks[meta.ptid]
        self._assert(
            task.unit.ctxt == meta.hval,
            'task {}-{}: context mismatch at exit - '
            '[expect: {}, actual: {}]'.format(
                meta.ptid, task.unit.seq, task.unit.ctxt, meta.hval
            )
        )

        # save the unit in last_unit
        task.last_unit = task.unit.clone()

        # return the task
        return task

    def _log_ctxt_exit_put_task(
            self,
            meta: LogMeta, task: TaskState,
            slot: Optional[Union[AsyncSlot, EventSlot]], kind: str
    ) -> None:
        # record
        self._record_ctxt_fini(meta, task, kind)

        # reset exec unit
        task.unit.clk = 0
        task.unit.ctxt = None
        task.unit.deps = {}

        # restore the task (if stolen)
        if slot is not None and slot.host is not None:
            task.unit = slot.host.clone()
            slot.host = None

    # CTXT (direct)
    def _log_ctxt_direct_enter(self, meta: LogMeta, kind: str) -> None:
        task = self._log_ctxt_enter_get_task(meta, None)
        self._assert(
            task.unit.base is None,
            'task {}-{}: direct context entered with parent - '
            '[hval: {}]'.format(
                meta.ptid, task.unit.seq, meta.hval
            )
        )
        self._log_ctxt_enter_put_task(meta, task, kind)

    def _log_ctxt_direct_exit(self, meta: LogMeta, kind: str) -> None:
        task = self._log_ctxt_exit_get_task(meta)
        self._assert(
            task.unit.base is None,
            'task {}-{}: direct context exited with parent - '
            '[hval: {}]'.format(
                meta.ptid, task.unit.seq, meta.hval
            )
        )
        self._log_ctxt_exit_put_task(meta, task, None, kind)

    def log_ctxt_syscall_enter(self, meta: LogMeta) -> None:
        self._log_ctxt_direct_enter(meta, 'SYSCALL')

    def log_ctxt_syscall_exit(self, meta: LogMeta) -> None:
        self._log_ctxt_direct_exit(meta, 'SYSCALL')

    # CTXT (indirect)
    def _log_ctxt_indirect_enter(
            self, meta: LogMeta, func: int, kind: str
    ) -> None:
        # figure out the async slot
        hval = meta.hval
        self._assert(
            hval in self.async_slots,
            'task {}: indirect context entered without registration - '
            '[hval: {}, func: {}]'.format(
                meta.ptid, hval, func
            )
        )

        slot = self.async_slots[hval]
        self._assert(
            slot.func == func,
            'task {}: indirect context entered with wrong callback - '
            '[hval: {}, expect callback: {}, actual callback: {}]'.format(
                meta.ptid, hval, slot.func, func
            )
        )

        # do generic ctxt enter
        task = self._log_ctxt_enter_get_task(meta, slot)

        # link with parent
        self._assert(
            task.unit.base is None,
            'task {}-{}: indirect context entered with parent'.format(
                meta.ptid, task.unit.seq
            )
        )
        task.unit.base = slot.unit.clone()

        # link with attachments
        for item in slot.others:
            task.unit.add_dep(item)

        # mark that we are serving the callback
        slot.func = 0
        slot.serving = func

        # clear the attachments
        slot.others.clear()

        # finish with logging the task
        self._log_ctxt_enter_put_task(meta, task, kind)

    def _log_ctxt_indirect_exit(
            self, meta: LogMeta, func: int, kind: str
    ) -> None:
        # do the generic context exit to get the task
        task = self._log_ctxt_exit_get_task(meta)

        # figure out the async slot
        hval = meta.hval
        self._assert(
            hval in self.async_slots,
            'task {}-{}: indirect context exited without registration - '
            '[hval: {}, func: {}]'.format(
                meta.ptid, task.unit.seq, hval, func
            )
        )

        slot = self.async_slots[hval]
        self._assert(
            slot.serving == func,
            'task {}-{}: indirect context exited with wrong callback - '
            '[hval: {}, expect callback: {}, actual callback: {}]'.format(
                meta.ptid, task.unit.seq, hval, slot.serving, func
            )
        )

        # reset parent
        self._assert(
            task.unit.base is not None,
            'task {}-{}: indirect context exited without parent'.format(
                meta.ptid, task.unit.seq
            )
        )
        task.unit.base = None

        # mark that we have done with serving the callback
        slot.serving = 0

        # reset the rest of the task
        self._log_ctxt_exit_put_task(meta, task, slot, kind)

    def log_ctxt_rcu_enter(self, meta: LogMeta, func: int) -> None:
        # do context enter first
        self._log_ctxt_indirect_enter(meta, func, 'RCU')

        # implies the start of the rcu write-side critical section
        lock_task = self.tasks[meta.ptid]
        lock_meta = LogMeta(meta.ptid, (1 << 2 | 1 << 0), meta.hval)
        self.log_sync_rcu_lock(lock_meta, lock_task, DART_LOCK_ID_RCU)

    def log_ctxt_rcu_exit(self, meta: LogMeta, func: int) -> None:
        # implies the end of the rcu write-side critical section
        if meta.ptid in self.tasks:
            lock_task = self.tasks[meta.ptid]
            lock_meta = LogMeta(meta.ptid, (1 << 2 | 1 << 0), meta.hval)
            self.log_sync_rcu_unlock(
                lock_meta, lock_task, DART_LOCK_ID_RCU
            )

        # do context exit later
        self._log_ctxt_indirect_exit(meta, func, 'RCU')

    def log_ctxt_work_enter(self, meta: LogMeta, func: int) -> None:
        self._log_ctxt_indirect_enter(meta, func, 'WORK')

    def log_ctxt_work_exit(self, meta: LogMeta, func: int) -> None:
        self._log_ctxt_indirect_exit(meta, func, 'WORK')

    def log_ctxt_task_enter(self, meta: LogMeta, func: int) -> None:
        self._log_ctxt_indirect_enter(meta, func, 'TASK')

    def log_ctxt_task_exit(self, meta: LogMeta, func: int) -> None:
        self._log_ctxt_indirect_exit(meta, func, 'TASK')

    def log_ctxt_timer_enter(self, meta: LogMeta, func: int) -> None:
        self._log_ctxt_indirect_enter(meta, func, 'TIMER')

    def log_ctxt_timer_exit(self, meta: LogMeta, func: int) -> None:
        self._log_ctxt_indirect_exit(meta, func, 'TIMER')

    def log_ctxt_krun_enter(self, meta: LogMeta, func: int) -> None:
        self._log_ctxt_indirect_enter(meta, func, 'KRUN')

    def log_ctxt_krun_exit(self, meta: LogMeta, func: int) -> None:
        self._log_ctxt_indirect_exit(meta, func, 'KRUN')

    def log_ctxt_block_enter(self, meta: LogMeta, func: int) -> None:
        self._log_ctxt_indirect_enter(meta, func, 'BLOCK')

    def log_ctxt_block_exit(self, meta: LogMeta, func: int) -> None:
        self._log_ctxt_indirect_exit(meta, func, 'BLOCK')

    def log_ctxt_ipi_enter(self, meta: LogMeta, func: int) -> None:
        self._log_ctxt_indirect_enter(meta, func, 'IPI')

    def log_ctxt_ipi_exit(self, meta: LogMeta, func: int) -> None:
        self._log_ctxt_indirect_exit(meta, func, 'IPI')

    # EXEC
    def log_exec_pause(self, meta: LogMeta, task: TaskState) -> None:
        pass

    def log_exec_resume(self, meta: LogMeta, task: TaskState) -> None:
        pass

    def log_exec_background(self, meta: LogMeta, task: TaskState) -> None:
        # figure out the async slot
        hval = meta.hval
        self._assert(
            hval in self.async_slots,
            'task {}: exec background without registration - '
            '[hval: {}]'.format(
                meta.ptid, hval
            )
        )

        slot = self.async_slots[hval]
        self._assert(
            slot.host is not None,
            'task {}: exec background without host - '
            '[hval: {}]'.format(
                meta.ptid, hval
            )
        )
        assert slot.host is not None

        # get task
        self._assert(
            meta.ptid in self.tasks,
            'task {}-X: exec background without establishment - '
            '[hval: {}]'.format(
                meta.ptid, hval
            )
        )
        task = self.tasks[meta.ptid]

        # do the switch
        temp = slot.host
        slot.host = task.unit
        task.unit = temp

    def log_exec_foreground(self, meta: LogMeta, task: TaskState) -> None:
        # figure out the async slot
        hval = meta.hval
        self._assert(
            hval in self.async_slots,
            'task {}: exec foreground without registration - '
            '[hval: {}]'.format(
                meta.ptid, hval
            )
        )

        slot = self.async_slots[hval]
        self._assert(
            slot.host is not None,
            'task {}: exec foreground without host - '
            '[hval: {}]'.format(
                meta.ptid, hval
            )
        )
        assert slot.host is not None

        # get task
        self._assert(
            meta.ptid in self.tasks,
            'task {}-X: exec foreground without establishment - '
            '[hval: {}]'.format(
                meta.ptid, hval
            )
        )
        task = self.tasks[meta.ptid]

        # do the switch
        temp = slot.host
        slot.host = task.unit
        task.unit = temp

    def log_exec_func_enter(self,
                            meta: LogMeta, task: TaskState, addr: int) -> None:
        # maintain the call stack
        func = self.compdb.funcs[meta.hval]
        task.stack.append(func)

        # record
        self._record_func_init(meta, task, func)

    def log_exec_func_exit(self,
                           meta: LogMeta, task: TaskState, addr: int) -> None:
        # maintain the call stack
        func = self.compdb.funcs[meta.hval]
        stack = task.stack

        self._assert(
            stack[-1].hval == func.hval,
            'call stack corrupted on exit: expected {}, got {}'.format(
                stack[-1].name, func.name
            )
        )

        # record
        self._record_func_fini(meta, task, func)

        # pop after record
        stack.pop()

    # ASYNC
    def _log_async_register(
            self, meta: LogMeta, task: TaskState, func: int, kind: str
    ) -> None:
        if meta.hval in self.async_slots:
            slot = self.async_slots[meta.hval]

            # check
            self._assert(
                slot.func == 0,
                'task {}-{}: async {} corrupted - '
                '{} registered twice [{}]'.format(
                    meta.ptid, task.unit.seq, kind, meta.hval, func
                )
            )

            # put owner's information into slot
            slot.func = func
            slot.unit = task.unit.clone()

        else:
            self.async_slots[meta.hval] = AsyncSlot(
                func=func,
                unit=task.unit.clone(),
                others=[],
                serving=0,
                host=None,
            )

        # record
        self._record_async_register(meta, task, func, kind)

    def _log_async_cancel(
            self, meta: LogMeta, task: TaskState, func: int, kind: str
    ) -> None:
        self._assert(
            meta.hval in self.async_slots,
            'task {}-{}: async {} corrupted - '
            '{} cancelled without register [{}]'.format(
                meta.ptid, task.unit.seq, kind, meta.hval, func
            )
        )

        slot = self.async_slots[meta.hval]

        # don't delete from async_slots, just mark func to 0
        slot.func = 0

        # also clear the attachments
        slot.others.clear()

        # record
        self._record_async_cancel(meta, task, func, kind)

    def _log_async_attach(
            self, meta: LogMeta, task: TaskState, func: int, kind: str
    ) -> None:
        self._assert(
            meta.hval in self.async_slots,
            'task {}-{}: async {} corrupted - '
            '{} attached without register [{}]'.format(
                meta.ptid, task.unit.seq, kind, meta.hval, func
            )
        )

        slot = self.async_slots[meta.hval]
        self._assert(
            slot.func == func,
            'task {}: async attached with wrong callback - '
            '[hval: {}, expect callback: {}, actual callback: {}]'.format(
                meta.ptid, meta.hval, slot.func, func
            )
        )

        # add the deps
        slot.others.append(task.unit.clone())

        # record
        self._record_async_attach(meta, task, func, kind)

    def log_async_rcu_register(
            self, meta: LogMeta, task: TaskState, func: int
    ) -> None:
        self._log_async_register(meta, task, func, 'RCU')

    def log_async_work_register(
            self, meta: LogMeta, task: TaskState, func: int
    ) -> None:
        self._log_async_register(meta, task, func, 'WORK')

    def log_async_work_cancel(
            self, meta: LogMeta, task: TaskState, func: int
    ) -> None:
        self._log_async_cancel(meta, task, func, 'WORK')

    def log_async_work_attach(
            self, meta: LogMeta, task: TaskState, func: int
    ) -> None:
        self._log_async_attach(meta, task, func, 'WORK')

    def log_async_task_register(
            self, meta: LogMeta, task: TaskState, func: int
    ) -> None:
        self._log_async_register(meta, task, func, 'TASK')

    def log_async_task_cancel(
            self, meta: LogMeta, task: TaskState, func: int
    ) -> None:
        self._log_async_cancel(meta, task, func, 'TASK')

    def log_async_timer_register(
            self, meta: LogMeta, task: TaskState, func: int
    ) -> None:
        self._log_async_register(meta, task, func, 'TIMER')

    def log_async_timer_cancel(
            self, meta: LogMeta, task: TaskState, func: int
    ) -> None:
        self._log_async_cancel(meta, task, func, 'TIMER')

    def log_async_krun_register(
            self, meta: LogMeta, task: TaskState, func: int
    ) -> None:
        self._log_async_register(meta, task, func, 'KRUN')

    def log_async_block_register(
            self, meta: LogMeta, task: TaskState, func: int
    ) -> None:
        self._log_async_register(meta, task, func, 'BLOCK')

    def log_async_ipi_register(
            self, meta: LogMeta, task: TaskState, func: int
    ) -> None:
        self._log_async_register(meta, task, func, 'IPI')

    # EVENT
    def _log_event_arrive(
            self, meta: LogMeta, task: TaskState, func: int, kind: str
    ) -> None:
        if meta.hval in self.event_slots:
            slot = self.event_slots[meta.hval]

            # check
            self._assert(
                slot.func == 0,
                'task {}-{}: event {} corrupted - '
                '{} arrived twice [{}]'.format(
                    meta.ptid, task.unit.seq, kind, meta.hval, func
                )
            )

            for k, v in slot.servers.items():
                self._assert(
                    v[0] == 0,
                    'task {}-{}: event {} corrupted - '
                    '{} arrived while notifier is still executing [{}]'.format(
                        meta.ptid, task.unit.seq, kind, meta.hval, func
                    )
                )

            slot.func = func
            slot.unit = task.unit.clone()
            slot.servers = {}

        else:
            self.event_slots[meta.hval] = EventSlot(
                func=func, unit=task.unit.clone(), servers={}, host=None,
            )

        # record
        self._record_event_arrive(meta, task, kind)

    def _log_event_notify_enter(
            self, meta: LogMeta, func: int, kind: str
    ) -> None:
        # figure out the event slot
        hval = meta.hval
        self._assert(
            hval in self.event_slots,
            'task {}: event notifier entered without arrival - '
            '[hvak: {}, func: {}]'.format(
                meta.ptid, hval, func
            )
        )

        slot = self.event_slots[hval]
        self._assert(
            slot.func == func,
            'task {}: event notifier entered with wrong callback - '
            '[hval: {}, expect callback: {}, actual callback: {}]'.format(
                meta.ptid, hval, slot.func, func
            )
        )

        if meta.ptid in slot.servers:
            self._assert(
                slot.servers[meta.ptid][0] == 0,
                'task {}: event notifier entered twice - '
                '[hval: {}, func: {}]'.format(
                    meta.ptid, hval, func
                )
            )

        # do generic ctxt enter
        task = self._log_ctxt_enter_get_task(meta, slot)

        # link with parent
        self._assert(
            task.unit.base is None,
            'task {}-{}: event notifier entered with parent'.format(
                meta.ptid, task.unit.seq
            )
        )
        task.unit.base = slot.unit.clone()

        # mark that we are serving the callback
        dep = task.unit.clone()
        slot.servers[meta.ptid] = (func, dep)

        # ask the waiter to add dependency already
        # TODO
        #  This again, is a conservative approach. What the code means is that
        #  all incoming wake_up calls must *happen-before* the waiter's
        #  execution once it passes the wait object, although only one wake_up
        #  call may actually release the waiter.
        self.tasks[slot.unit.ptid].unit.add_dep(dep)

        # finish with logging the task
        self._log_ctxt_enter_put_task(meta, task, kind)

    def _log_event_notify_exit(
            self, meta: LogMeta, func: int, kind: str
    ) -> None:
        # do the generic context exit to get the task
        task = self._log_ctxt_exit_get_task(meta)

        # figure out the event slot
        hval = meta.hval
        self._assert(
            hval in self.event_slots,
            'task {}-{}: event notifier exited without arrival - '
            '[hvak: {}, func: {}]'.format(
                meta.ptid, task.unit.seq, hval, func
            )
        )
        slot = self.event_slots[hval]

        # check that we have entered before
        self._assert(
            meta.ptid in slot.servers,
            'task {}-{}: event notifier exited without entering - '
            '[hval: {}, func: {}]'.format(
                meta.ptid, task.unit.seq, hval, func
            )
        )

        n_func, n_unit = slot.servers[meta.ptid]
        self._assert(
            n_func == func,
            'task {}-{}: event notifier exited with wrong callback - '
            '[hval: {}, expect callback: {}, actual callback: {}]'.format(
                meta.ptid, task.unit.seq, hval, slot.servers[meta.ptid][0], func
            )
        )

        # reset parent
        self._assert(
            task.unit.base is not None,
            'task {}-{}: event notifier exited without parent'.format(
                meta.ptid, task.unit.seq
            )
        )
        task.unit.base = None

        # mark that we have done with serving the callback
        slot.servers[meta.ptid] = (0, n_unit)

        # reset the rest of the task
        self._log_ctxt_exit_put_task(meta, task, slot, kind)

    def _log_event_pass(
            self, meta: LogMeta, task: TaskState, func: int, kind: str
    ) -> None:
        # check that slot exits
        self._assert(
            meta.hval in self.event_slots,
            'task {}-{}: event {} corrupted - '
            '{} passed without arrival [{}]'.format(
                meta.ptid, task.unit.seq, kind, meta.hval, func
            )
        )

        slot = self.event_slots[meta.hval]

        # don't delete from event_slots, just mark func to 0
        slot.func = 0

        # record
        self._record_event_pass(meta, task, kind)

    def log_event_wait_arrive(
            self, meta: LogMeta, task: TaskState, func: int
    ) -> None:
        self._log_event_arrive(meta, task, func, 'WAIT')

    def log_event_wait_notify_enter(
            self, meta: LogMeta, func: int
    ) -> None:
        self._log_event_notify_enter(meta, func, 'WAIT')

    def log_event_wait_notify_exit(
            self, meta: LogMeta, func: int
    ) -> None:
        self._log_event_notify_exit(meta, func, 'WAIT')

    def log_event_wait_pass(
            self, meta: LogMeta, task: TaskState, func: int
    ) -> None:
        self._log_event_pass(meta, task, func, 'WAIT')

    def log_event_sema_arrive(
            self, meta: LogMeta, task: TaskState, func: int
    ) -> None:
        self._log_event_arrive(meta, task, func, 'SEMA')

    def log_event_sema_notify_enter(
            self, meta: LogMeta, func: int
    ) -> None:
        self._log_event_notify_enter(meta, func, 'SEMA')

    def log_event_sema_notify_exit(
            self, meta: LogMeta, func: int
    ) -> None:
        self._log_event_notify_exit(meta, func, 'SEMA')

    def log_event_sema_pass(
            self, meta: LogMeta, task: TaskState, func: int
    ) -> None:
        self._log_event_pass(meta, task, func, 'SEMA')

    # QUEUE
    def log_event_queue_arrive(self, meta: LogMeta, task: TaskState) -> None:
        # find exec unit
        if meta.hval in self.queue_slots:
            slot = self.queue_slots[meta.hval]

            # add dependency
            for unit in slot.units.values():
                task.unit.add_dep(unit)

        # record
        self._record_queue_suffix(meta, task, 'QUE')

    def log_event_queue_notify(self, meta: LogMeta, task: TaskState) -> None:
        # check-in exec unit
        if meta.hval in self.queue_slots:
            slot = self.queue_slots[meta.hval]
        else:
            slot = QueueSlot({})
            self.queue_slots[meta.hval] = slot

        slot.units[meta.ptid] = task.unit.clone()

        # record
        self._record_queue_prefix(meta, task, 'QUE')

    # helper
    def _chk_exec_inst_on_stack(self, meta: LogMeta, task: TaskState) -> None:
        func = self.compdb.insts[meta.hval].get_parent().get_parent()
        stack = task.stack

        self._assert(
            stack[-1].hval == func.hval,
            'operation corrupted stack: expected{}, got {}'.format(
                stack[-1].name, func.name
            )
        )

    # COV
    def log_cov_edge(self, meta: LogMeta, task: TaskState) -> None:
        block = self.compdb.blocks[meta.hval]
        stack = task.stack
        self._assert(
            stack[-1].hval == block.get_parent().hval,
            'call stack corrupted in the middle: expect {}, got {}'.format(
                stack[-1].name, block.get_parent().name
            )
        )

        task.last_blkid = meta.hval

        # record
        self._record_cov_edge(meta, task)

    # MEM (generic)
    def _log_mem_add(
            self,
            meta: LogMeta, task: TaskState,
            repo: Dict[int, int], addr: int, size: int, kind: str
    ) -> None:
        for i in range(size):
            pos = addr + i
            self._assert(
                pos not in repo,
                'task {}-{}: memory management ({}) corrupted - '
                '{} add without del [{}]'.format(
                    meta.ptid, task.unit.seq, kind, hex(pos), meta.hval
                )
            )
            repo[pos] = meta.hval

        # record
        self._record_mem_add(meta, task, addr, size, kind)

    def _log_mem_del(
            self,
            meta: LogMeta, task: TaskState,
            repo: Dict[int, int], addr: int, size: int, kind: str
    ) -> None:
        for i in range(size):
            pos = addr + i
            self._assert(
                pos in repo,
                'task {}-{}: memory management ({}) corrupted - '
                '{} del without add [{}]'.format(
                    meta.ptid, task.unit.seq, kind, hex(pos), meta.hval
                )
            )
            del repo[pos]

        # record
        self._record_mem_del(meta, task, addr, size, kind)

    def _log_mem_add_size(
            self,
            meta: LogMeta, task: TaskState,
            repo: Dict[int, int], addr: int, size: int, kind: str
    ) -> None:
        self._assert(
            addr not in repo,
            'task {}-{}: memory management ({}) corrupted - '
            '{} size add without del [{}]'.format(
                meta.ptid, task.unit.seq, kind, hex(addr), size
            )
        )
        repo[addr] = size

    def _log_mem_del_size(
            self,
            meta: LogMeta, task: TaskState,
            repo: Dict[int, int], addr: int, kind: str
    ) -> Optional[int]:
        self._assert(
            addr in repo,
            'task {}-{}: memory management ({}) corrupted - '
            '{} size del without add'.format(
                meta.ptid, task.unit.seq, kind, hex(addr)
            )
        )

        size = repo[addr]
        del repo[addr]
        return size

    # MEM (stack)
    def log_mem_stack_push(
            self, meta: LogMeta, task: TaskState, addr: int, size: int
    ) -> None:
        self._log_mem_add(meta, task, task.stack_mem, addr, size, 'S')

    def log_mem_stack_pop(
            self, meta: LogMeta, task: TaskState, addr: int, size: int
    ) -> None:
        self._log_mem_del(meta, task, task.stack_mem, addr, size, 'S')

    # MEM (heap)
    def log_mem_heap_alloc(
            self, meta: LogMeta, task: TaskState, addr: int, size: int
    ) -> None:
        self._log_mem_add(meta, task, self.mem_heaps, addr, size, 'H')
        self._log_mem_add_size(meta, task, self.mem_sizes_heap, addr, size, 'H')

    def log_mem_heap_free(
            self, meta: LogMeta, task: TaskState, addr: int
    ) -> None:
        size = self._log_mem_del_size(
            meta, task, self.mem_sizes_heap, addr, 'H'
        )
        if size is None:
            return

        self._log_mem_del(meta, task, self.mem_heaps, addr, size, 'H')

    # MEM (percpu)
    def log_mem_percpu_alloc(
            self, meta: LogMeta, task: TaskState, addr: int, size: int
    ) -> None:
        self._log_mem_add(meta, task, self.mem_pcpus, addr, size, 'P')
        self._log_mem_add_size(meta, task, self.mem_sizes_pcpu, addr, size, 'P')

    def log_mem_percpu_free(
            self, meta: LogMeta, task: TaskState, addr: int
    ) -> None:
        size = self._log_mem_del_size(
            meta, task, self.mem_sizes_pcpu, addr, 'P'
        )
        assert size is not None
        self._log_mem_del(meta, task, self.mem_pcpus, addr, size, 'P')

    # MEM (access)
    def _log_mem_cell_reader(
            self, meta: LogMeta, task: TaskState, addr: int
    ) -> None:
        # ignore memory reads on stack and percpu
        if addr in task.stack_mem:
            return

        if addr in self.mem_pcpus:
            return

        # need to analyze the memory read
        if addr not in self.cells:
            self.cells[addr] = MemCell()

        cell = self.cells[addr]
        if meta.ptid not in cell.readers:
            cell.readers[meta.ptid] = []

        # construct the access
        access = MemAccess(
            hval=meta.hval,
            unit=task.unit.clone(),
            sync_locks=task.sync_locks.lockset_r(),
            sync_trans=task.sync_trans.transet_r(),
        )

        # check for race candidates
        for ptid, vals in cell.writers.items():
            # a task does not race against itself
            if ptid == meta.ptid:
                continue

            another = vals[-1]

            # TODO (simply ignore races when both parties are in interrupt)
            if meta.ctxt != CtxtType.TASK and \
                    CtxtType.from_ptid(another.unit.ptid) != CtxtType.TASK:
                continue

            # it is not a race if we can establish happens-before relation
            if another.unit.happens_before(access.unit):
                continue

            # it is not a race if protected by the lock
            if len(another.sync_locks.intersection(access.sync_locks)) != 0:
                continue

            # find the pending transaction that may invalidate the race
            pending = set()
            for trans_key in another.sync_trans:
                if trans_key in access.sync_trans:
                    pending.add(trans_key)

            # no locks and no transaction, definitely a race
            if len(pending) == 0 and not self.race_blacklist(another, access):
                self._record_race(task, another, access, addr)
                continue

            # save to candidate pool if we cannot confirm now
            # TODO

        # put the access to log
        cell.readers[meta.ptid].append(access)

    def _log_mem_cell_writer(
            self, meta: LogMeta, task: TaskState, addr: int
    ) -> None:
        # ignore memory writes on stack and percpu
        if addr in task.stack_mem:
            return

        if addr in self.mem_pcpus:
            return

        # need to analyze the memory write
        if addr not in self.cells:
            self.cells[addr] = MemCell()

        cell = self.cells[addr]
        if meta.ptid not in cell.writers:
            cell.writers[meta.ptid] = []

        # construct the access
        access = MemAccess(
            hval=meta.hval,
            unit=task.unit.clone(),
            sync_locks=task.sync_locks.lockset_w(),
            sync_trans=task.sync_trans.transet_w(),
        )

        # check for race candidates
        for ptid, vals in cell.readers.items():
            if ptid == meta.ptid:
                continue

            another = vals[-1]

            # TODO (simply ignore races when both parties are in interrupt)
            if meta.ctxt != CtxtType.TASK and \
                    CtxtType.from_ptid(another.unit.ptid) != CtxtType.TASK:
                continue

            # it is not a race if we can establish happens-before relation
            if another.unit.happens_before(access.unit):
                continue

            # it is not a race if protected by the lock
            if len(another.sync_locks.intersection(access.sync_locks)) != 0:
                continue

            # find the pending transaction that may invalidate the race
            pending = set()
            for trans_key in access.sync_trans:
                if trans_key in another.sync_trans:
                    pending.add(trans_key)

            # no locks and no transaction, definitely a race
            if len(pending) == 0 and not self.race_blacklist(another, access):
                self._record_race(task, another, access, addr)
                continue

            # save to candidate pool if we cannot confirm now
            # TODO

        for ptid, vals in cell.writers.items():
            if ptid == meta.ptid:
                continue

            another = vals[-1]

            # TODO (simply ignore races when both parties are in interrupt)
            if meta.ctxt != CtxtType.TASK and \
                    CtxtType.from_ptid(another.unit.ptid) != CtxtType.TASK:
                continue

            # it is not a race if we can establish happens-before relation
            if another.unit.happens_before(access.unit):
                continue

            # it is not a race if protected by the lock
            if len(another.sync_locks.intersection(access.sync_locks)) != 0:
                continue

            # transaction does not apply to writer-writer race, so report
            self._record_race(task, another, access, addr)

        # put the access to log
        cell.writers[meta.ptid].append(access)

    def log_mem_read(
            self, meta: LogMeta, task: TaskState, addr: int, size: int
    ) -> None:
        # sanity check
        self._chk_exec_inst_on_stack(meta, task)

        # record
        self._record_mem_reader(meta, task, addr, size)

        # race check
        for i in range(size):
            self._log_mem_cell_reader(meta, task, addr + i)

    def log_mem_write(
            self, meta: LogMeta, task: TaskState, addr: int, size: int
    ) -> None:

        # sanity check
        self._chk_exec_inst_on_stack(meta, task)

        # record
        self._record_mem_writer(meta, task, addr, size)

        # race check
        for i in range(size):
            self._log_mem_cell_writer(meta, task, addr + i)

    # SYNC (generic lock)
    def log_sync_gen_lock(
            self, meta: LogMeta, task: TaskState, lock: int
    ) -> None:
        # derive info
        info = SyncInfo(meta.info)
        if info.is_try and not info.is_succ:
            return

        # add into lockset
        if info.is_rw:
            depth = task.sync_locks.add_lock_w(lock)
            dirch = 'E'
        else:
            depth = task.sync_locks.add_lock_r(lock)
            dirch = 'S'

        # generic locks cannot be nested
        self._assert(
            depth == 0,
            'gen_lock acquired with wrong depth: <{}> {} [{}]'.format(
                meta.ptid, hex(lock), depth
            )
        )

        # record
        self._record_sync_lock_acquire(meta, task, dirch, lock, 'GEN')

    def log_sync_gen_unlock(
            self, meta: LogMeta, task: TaskState, lock: int
    ) -> None:
        # derive info
        info = SyncInfo(meta.info)
        if info.is_try and not info.is_succ:
            return

        # del from lockset
        if info.is_rw:
            depth = task.sync_locks.del_lock_w(lock)
            dirch = 'E'
        else:
            depth = task.sync_locks.del_lock_r(lock)
            dirch = 'S'

        # generic locks cannot be nested
        self._assert(
            depth == 1,
            'gen_lock released with wrong depth: <{}> {} [{}]'.format(
                meta.ptid, hex(lock), depth
            )
        )

        # record
        self._record_sync_lock_release(meta, task, dirch, lock, 'GEN')

    # SYNC (sequence lock)
    def log_sync_seq_lock(
            self, meta: LogMeta, task: TaskState, lock: int
    ) -> None:
        # derive info
        info = SyncInfo(meta.info)
        if info.is_try and not info.is_succ:
            return

        # add into lockset
        if info.is_rw:
            depth = task.sync_trans.add_lock_w(lock)

            # writer lock cannot be nested
            self._assert(
                depth == 0,
                'seq_lock [E] acquired with wrong depth: <{}> {} [{}]'.format(
                    meta.ptid, hex(lock), depth
                )
            )

            dirch = 'E'
        else:
            prior = task.sync_trans.add_tran_r(lock, task.unit.clone())

            # TODO (we don't know whether seqlock_read can be nested, so, warn)
            if prior is None:
                self._record_warning(
                    meta, task,
                    'seq_lock [S] acquired with wrong depth: {} [0:0]'.format(
                        hex(lock)
                    ),
                )

            dirch = 'S'

        # record
        self._record_sync_lock_acquire(meta, task, dirch, lock, 'SEQ')

    def log_sync_seq_unlock(
            self, meta: LogMeta, task: TaskState, lock: int
    ) -> None:
        info = SyncInfo(meta.info)
        if info.is_try and not info.is_succ:
            return

        # del from lockset
        if info.is_rw:
            depth = task.sync_trans.del_lock_w(lock)

            # writer lock cannot be nested
            self._assert(
                depth == 1,
                'seq_lock [E] released with wrong depth: <{}> {} [{}]'.format(
                    meta.ptid, hex(lock), depth
                )
            )

            dirch = 'E'
        else:
            prior = task.sync_trans.del_tran_r(lock, task.unit.clone())

            # it is OK for one reader lock to have multiple unlocks,
            # but there must be a lock first
            self._assert(
                prior is not None,
                'seq_lock [S] released with wrong depth: <{}> {} [0:0]'.format(
                    meta.ptid, hex(lock)
                )
            )

            assert prior is not None
            self._assert(
                prior.seq == task.unit.seq,
                'seq_lock [S] released with wrong ctxt: <{}> {} [{}:{}]'.format(
                    meta.ptid, hex(lock), prior.seq, task.unit.seq
                )
            )

            dirch = 'S'

        # record
        self._record_sync_lock_release(meta, task, dirch, lock, 'SEQ')

    # SYNC (rcu lock)
    def log_sync_rcu_lock(
            self, meta: LogMeta, task: TaskState, lock: int
    ) -> None:
        # derive info
        info = SyncInfo(meta.info)
        if info.is_try and not info.is_succ:
            return

        # add into lockset
        if info.is_rw:
            depth = task.sync_locks.add_lock_w(lock)

            # rcu writer locks cannot be nested
            self._assert(
                depth == 0,
                'rcu_lock [E] acquired with wrong depth: <{}> {} [{}]'.format(
                    meta.ptid, hex(lock), depth
                )
            )

            dirch = 'E'
        else:
            task.sync_locks.add_lock_r(lock)
            dirch = 'S'

        # record
        self._record_sync_lock_acquire(meta, task, dirch, lock, 'RCU')

    def log_sync_rcu_unlock(
            self, meta: LogMeta, task: TaskState, lock: int
    ) -> None:
        info = SyncInfo(meta.info)
        if info.is_try and not info.is_succ:
            return

        # del from lockset
        if info.is_rw:
            depth = task.sync_locks.del_lock_w(lock)
            dirch = 'E'
        else:
            depth = task.sync_locks.del_lock_r(lock)
            dirch = 'S'

        # rcu locks cannot be unlocked more times than locked
        self._assert(
            depth >= 1,
            'rcu_lock released with wrong depth: <{}> {} [{}]'.format(
                meta.ptid, hex(lock), depth
            )
        )

        # record
        self._record_sync_lock_release(meta, task, dirch, lock, 'RCU')

    # ORDER
    def log_order_ps_publish(
            self, meta: LogMeta, task: TaskState, addr: int
    ) -> None:
        '''
        # check-in exec unit
        if addr in self.order_slots:
            self.order_slots[addr].units[meta.ptid] = task.unit.clone()
        else:
            self.order_slots[addr] = OrderSlot(
                units={meta.ptid: task.unit.clone()}
            )
        '''

        # TODO: this is very conservative, i.e.,
        #  P1, P2, S --> both P1 and P2 happen-before S,
        #  which might not be true

        # record
        self._record_order_prefix(meta, task, addr, 'RCU')

    def log_order_ps_subscribe(
            self, meta: LogMeta, task: TaskState, addr: int
    ) -> None:
        '''
        # check-out exec unit
        if addr in self.order_slots:
            task.unit.add_deps(self.order_slots[addr].units)

        # TODO (see comments above)
        '''

        # record
        self._record_order_suffix(meta, task, addr, 'RCU')

    def log_order_obj_deposit(
            self, meta: LogMeta, task: TaskState, addr: int, objv: int
    ) -> None:
        # check-in exec unit
        self.order_slots[addr] = OrderSlot(objv, task.unit.clone())

        # record
        self._record_order_prefix(meta, task, addr, 'OBJ')

    def log_order_obj_consume(
            self, meta: LogMeta, task: TaskState, addr: int
    ) -> None:
        # find exec unit
        self._assert(
            addr in self.order_slots,
            'order slot addr mismatch'
        )

        slot = self.order_slots[addr]

        # add dependency
        task.unit.add_dep(slot.unit)

        # record
        self._record_order_suffix(meta, task, addr, 'OBJ')

    # iterate over the logs
    def iterate_log(self, n: int, b: BinaryIO) -> None:
        log_types = {i.value: i for i in LogType}

        # read log entry by entry
        unhandled = 0

        for i in range(n):
            cval, ptid, info, hval = struct.unpack('IIQQ', b.read(24))
            code = log_types[cval]
            meta = LogMeta(ptid, info, hval)

            # statistics accounting
            if ptid not in self.stats:
                self.stats[ptid] = {}

            if code not in self.stats[ptid]:
                self.stats[ptid][code] = 0

            self.stats[ptid][code] += 1

            # SYS
            if code == LogType.SYS_LAUNCH:
                self._assert(
                    i == 0,
                    'first log entry is not sys_launch'
                )
                self.log_sys_launch(meta)
                continue

            if code == LogType.SYS_FINISH:
                self._assert(
                    i == n - 1,
                    'last log entry is not sys_finish'
                )
                self.log_sys_finish(meta)
                continue

            # CTXT
            if code == LogType.CTXT_SYSCALL_ENTER:
                self.log_ctxt_syscall_enter(meta)
                continue

            if code == LogType.CTXT_SYSCALL_EXIT:
                self.log_ctxt_syscall_exit(meta)
                continue

            if code == LogType.CTXT_RCU_ENTER:
                func = struct.unpack('Q', b.read(8))[0]
                self.log_ctxt_rcu_enter(meta, func)
                continue

            if code == LogType.CTXT_RCU_EXIT:
                func = struct.unpack('Q', b.read(8))[0]
                self.log_ctxt_rcu_exit(meta, func)
                continue

            if code == LogType.CTXT_WORK_ENTER:
                func = struct.unpack('Q', b.read(8))[0]
                self.log_ctxt_work_enter(meta, func)
                continue

            if code == LogType.CTXT_WORK_EXIT:
                func = struct.unpack('Q', b.read(8))[0]
                self.log_ctxt_work_exit(meta, func)
                continue

            if code == LogType.CTXT_TASK_ENTER:
                func = struct.unpack('Q', b.read(8))[0]
                self.log_ctxt_task_enter(meta, func)
                continue

            if code == LogType.CTXT_TASK_EXIT:
                func = struct.unpack('Q', b.read(8))[0]
                self.log_ctxt_task_exit(meta, func)
                continue

            if code == LogType.CTXT_TIMER_ENTER:
                func = struct.unpack('Q', b.read(8))[0]
                self.log_ctxt_timer_enter(meta, func)
                continue

            if code == LogType.CTXT_TIMER_EXIT:
                func = struct.unpack('Q', b.read(8))[0]
                self.log_ctxt_timer_exit(meta, func)
                continue

            if code == LogType.CTXT_KRUN_ENTER:
                func = struct.unpack('Q', b.read(8))[0]
                self.log_ctxt_krun_enter(meta, func)
                continue

            if code == LogType.CTXT_KRUN_EXIT:
                func = struct.unpack('Q', b.read(8))[0]
                self.log_ctxt_krun_exit(meta, func)
                continue

            if code == LogType.CTXT_BLOCK_ENTER:
                func = struct.unpack('Q', b.read(8))[0]
                self.log_ctxt_block_enter(meta, func)
                continue

            if code == LogType.CTXT_BLOCK_EXIT:
                func = struct.unpack('Q', b.read(8))[0]
                self.log_ctxt_block_exit(meta, func)
                continue

            if code == LogType.CTXT_IPI_ENTER:
                func = struct.unpack('Q', b.read(8))[0]
                self.log_ctxt_ipi_enter(meta, func)
                continue

            if code == LogType.CTXT_IPI_EXIT:
                func = struct.unpack('Q', b.read(8))[0]
                self.log_ctxt_ipi_exit(meta, func)
                continue

            # EVENT (notifier part only)
            if code == LogType.EVENT_WAIT_NOTIFY_ENTER:
                func = struct.unpack('Q', b.read(8))[0]
                self.log_event_wait_notify_enter(meta, func)
                continue

            if code == LogType.EVENT_WAIT_NOTIFY_EXIT:
                func = struct.unpack('Q', b.read(8))[0]
                self.log_event_wait_notify_exit(meta, func)
                continue

            if code == LogType.EVENT_SEMA_NOTIFY_ENTER:
                func = struct.unpack('Q', b.read(8))[0]
                self.log_event_sema_notify_enter(meta, func)
                continue

            if code == LogType.EVENT_SEMA_NOTIFY_EXIT:
                func = struct.unpack('Q', b.read(8))[0]
                self.log_event_sema_notify_exit(meta, func)
                continue

            # from now on, we have a task
            self._assert(
                meta.ptid in self.tasks,
                'log entry does not contain a task'
            )
            task = self.tasks[meta.ptid]

            if code == LogType.EXEC_BACKGROUND:
                self.log_exec_background(meta, task)
                continue

            if code == LogType.EXEC_FOREGROUND:
                self.log_exec_foreground(meta, task)
                continue

            # from now on, we have a unit
            task.unit.clk += 1

            # EXEC
            if code == LogType.EXEC_PAUSE:
                self.log_exec_pause(meta, task)
                continue

            if code == LogType.EXEC_RESUME:
                self.log_exec_resume(meta, task)
                continue

            if code == LogType.EXEC_FUNC_ENTER:
                addr = struct.unpack('Q', b.read(8))[0]
                self.log_exec_func_enter(meta, task, addr)
                continue

            if code == LogType.EXEC_FUNC_EXIT:
                addr = struct.unpack('Q', b.read(8))[0]
                self.log_exec_func_exit(meta, task, addr)
                continue

            # ASYNC
            if code == LogType.ASYNC_RCU_REGISTER:
                func = struct.unpack('Q', b.read(8))[0]
                self.log_async_rcu_register(meta, task, func)
                continue

            if code == LogType.ASYNC_WORK_REGISTER:
                func = struct.unpack('Q', b.read(8))[0]
                self.log_async_work_register(meta, task, func)
                continue

            if code == LogType.ASYNC_WORK_CANCEL:
                func = struct.unpack('Q', b.read(8))[0]
                self.log_async_work_cancel(meta, task, func)
                continue

            if code == LogType.ASYNC_WORK_ATTACH:
                func = struct.unpack('Q', b.read(8))[0]
                self.log_async_work_attach(meta, task, func)
                continue

            if code == LogType.ASYNC_TASK_REGISTER:
                func = struct.unpack('Q', b.read(8))[0]
                self.log_async_task_register(meta, task, func)
                continue

            if code == LogType.ASYNC_TASK_CANCEL:
                func = struct.unpack('Q', b.read(8))[0]
                self.log_async_task_cancel(meta, task, func)
                continue

            if code == LogType.ASYNC_TIMER_REGISTER:
                func = struct.unpack('Q', b.read(8))[0]
                self.log_async_timer_register(meta, task, func)
                continue

            if code == LogType.ASYNC_TIMER_CANCEL:
                func = struct.unpack('Q', b.read(8))[0]
                self.log_async_timer_cancel(meta, task, func)
                continue

            if code == LogType.ASYNC_KRUN_REGISTER:
                func = struct.unpack('Q', b.read(8))[0]
                self.log_async_krun_register(meta, task, func)
                continue

            if code == LogType.ASYNC_BLOCK_REGISTER:
                func = struct.unpack('Q', b.read(8))[0]
                self.log_async_block_register(meta, task, func)
                continue

            if code == LogType.ASYNC_IPI_REGISTER:
                func = struct.unpack('Q', b.read(8))[0]
                self.log_async_ipi_register(meta, task, func)
                continue

            # EVENT
            if code == LogType.EVENT_QUEUE_ARRIVE:
                self.log_event_queue_arrive(meta, task)
                continue

            if code == LogType.EVENT_QUEUE_NOTIFY:
                self.log_event_queue_notify(meta, task)
                continue

            if code == LogType.EVENT_WAIT_ARRIVE:
                func = struct.unpack('Q', b.read(8))[0]
                self.log_event_wait_arrive(meta, task, func)
                continue

            if code == LogType.EVENT_WAIT_PASS:
                func = struct.unpack('Q', b.read(8))[0]
                self.log_event_wait_pass(meta, task, func)
                continue

            if code == LogType.EVENT_SEMA_ARRIVE:
                func = struct.unpack('Q', b.read(8))[0]
                self.log_event_sema_arrive(meta, task, func)
                continue

            if code == LogType.EVENT_SEMA_PASS:
                func = struct.unpack('Q', b.read(8))[0]
                self.log_event_sema_pass(meta, task, func)
                continue

            # COV
            if code == LogType.COV_CFG:
                self.log_cov_edge(meta, task)
                continue

            # MEM
            if code == LogType.MEM_STACK_PUSH:
                addr, size = struct.unpack('QQ', b.read(16))
                self.log_mem_stack_push(meta, task, addr, size)
                continue

            if code == LogType.MEM_STACK_POP:
                addr, size = struct.unpack('QQ', b.read(16))
                self.log_mem_stack_pop(meta, task, addr, size)
                continue

            if code == LogType.MEM_HEAP_ALLOC:
                addr, size = struct.unpack('QQ', b.read(16))
                self.log_mem_heap_alloc(meta, task, addr, size)
                continue

            if code == LogType.MEM_HEAP_FREE:
                addr = struct.unpack('Q', b.read(8))[0]
                self.log_mem_heap_free(meta, task, addr)
                continue

            if code == LogType.MEM_PERCPU_ALLOC:
                addr, size = struct.unpack('QQ', b.read(16))
                self.log_mem_percpu_alloc(meta, task, addr, size)
                continue

            if code == LogType.MEM_PERCPU_FREE:
                addr = struct.unpack('Q', b.read(8))[0]
                self.log_mem_percpu_free(meta, task, addr)
                continue

            if code == LogType.MEM_READ:
                addr, size = struct.unpack('QQ', b.read(16))
                self.log_mem_read(meta, task, addr, size)
                continue

            if code == LogType.MEM_WRITE:
                addr, size = struct.unpack('QQ', b.read(16))
                self.log_mem_write(meta, task, addr, size)
                continue

            # SYNC
            if code == LogType.SYNC_GEN_LOCK:
                lock = struct.unpack('Q', b.read(8))[0]
                self.log_sync_gen_lock(meta, task, lock)
                continue

            if code == LogType.SYNC_GEN_UNLOCK:
                lock = struct.unpack('Q', b.read(8))[0]
                self.log_sync_gen_unlock(meta, task, lock)
                continue

            if code == LogType.SYNC_SEQ_LOCK:
                lock = struct.unpack('Q', b.read(8))[0]
                self.log_sync_seq_lock(meta, task, lock)
                continue

            if code == LogType.SYNC_SEQ_UNLOCK:
                lock = struct.unpack('Q', b.read(8))[0]
                self.log_sync_seq_unlock(meta, task, lock)
                continue

            if code == LogType.SYNC_RCU_LOCK:
                lock = struct.unpack('Q', b.read(8))[0]
                self.log_sync_rcu_lock(meta, task, lock)
                continue

            if code == LogType.SYNC_RCU_UNLOCK:
                lock = struct.unpack('Q', b.read(8))[0]
                self.log_sync_rcu_unlock(meta, task, lock)
                continue

            # ORDER
            if code == LogType.ORDER_PS_PUBLISH:
                addr = struct.unpack('Q', b.read(8))[0]
                self.log_order_ps_publish(meta, task, addr)
                continue

            if code == LogType.ORDER_PS_SUBSCRIBE:
                addr = struct.unpack('Q', b.read(8))[0]
                self.log_order_ps_subscribe(meta, task, addr)
                continue

            if code == LogType.ORDER_OBJ_DEPOSIT:
                addr, objv = struct.unpack('QQ', b.read(16))
                self.log_order_obj_deposit(meta, task, addr, objv)
                continue

            if code == LogType.ORDER_OBJ_CONSUME:
                addr = struct.unpack('Q', b.read(8))[0]
                self.log_order_obj_consume(meta, task, addr)
                continue

            # MARK
            if code == LogType.MARK_V0:
                continue

            if code == LogType.MARK_V1:
                b.read(8)
                continue

            if code == LogType.MARK_V2:
                b.read(16)
                continue

            if code == LogType.MARK_V3:
                b.read(24)
                continue

            unhandled += 1

        # warn if we have left any messages unhandled (TODO change to assert)
        if unhandled != 0:
            logging.warning('{} log messages not handled'.format(unhandled))

        # all async calls should have been invoked
        leftover_async = {
            hval: slot
            for hval, slot in self.async_slots.items()
            if slot.func != 0 or slot.serving != 0
        }
        self._assert(
            len(leftover_async) == 0,
            'global - async slots leftover: {}\n\t{}'.format(
                len(leftover_async),
                '\n\t'.join([
                    '{}: {} - {}:{}:{}'.format(
                        hval, hex(slot.func),
                        slot.unit.ptid, slot.unit.seq, slot.unit.clk
                    )
                    for hval, slot in sorted(leftover_async.items())
                ])
            )
        )

        # all event waiters should have been notified
        leftover_event = {
            hval: slot
            for hval, slot in self.event_slots.items()
            if slot.func != 0 or sum([v[0] for v in slot.servers.values()]) != 0
        }
        self._assert(
            len(leftover_event) == 0,
            'global - events slots leftover: {}\n\t{}'.format(
                len(leftover_event),
                '\n\t'.join([
                    '{}: {} - {}:{}:{}'.format(
                        hval, hex(slot.func),
                        slot.unit.ptid, slot.unit.seq, slot.unit.clk
                    )
                    for hval, slot in sorted(leftover_event.items())
                ])
            )
        )

        # all context should be terminated
        for ptid, task in self.tasks.items():
            self._assert(
                task.unit.ctxt is None,
                'ptid {} - still tracing: {}'.format(
                    ptid, task.unit.ctxt
                )
            )

        # call stack should be empty
        for ptid, task in self.tasks.items():
            self._assert(
                len(task.stack) == 0,
                'ptid {} - call stack leftover: {}\n\t{}'.format(
                    ptid, len(task.stack),
                    '\n\t'.join([func.name for func in task.stack])
                )
            )

        # variables pushed onto the stack must be cleared
        for ptid, task in self.tasks.items():
            self._assert(
                len(task.stack_mem) == 0,
                'ptid {} - stack frame leftover: {}\n\t{}'.format(
                    ptid, len(task.stack_mem),
                    '\n\t'.join([
                        hex(addr) for addr in sorted(task.stack_mem.keys())
                    ])
                )
            )

        # all locks should have been unlocked
        for ptid, task in self.tasks.items():
            self._assert(
                len(task.sync_locks.locks_r.locks) == 0,
                'ptid {} - reader lock leftover: {}\n\t{}'.format(
                    ptid, len(task.sync_locks.locks_r.locks),
                    '\n\t'.join([
                        '{}: {}'.format(hex(addr), cval)
                        for addr, cval in task.sync_locks.locks_r.locks.items()
                    ])
                )
            )
            self._assert(
                len(task.sync_locks.locks_w.locks) == 0,
                'ptid {} - writer lock leftover: {}\n\t{}'.format(
                    ptid, len(task.sync_locks.locks_w.locks),
                    '\n\t'.join([
                        '{}: {}'.format(hex(addr), cval)
                        for addr, cval in task.sync_locks.locks_w.locks.items()
                    ])
                )
            )
            self._assert(
                len(task.sync_trans.locks_w.locks) == 0,
                'ptid {} - writer tran leftover: {}\n\t{}'.format(
                    ptid, len(task.sync_trans.locks_w.locks),
                    '\n\t'.join([
                        '{}: {}'.format(hex(addr), cval)
                        for addr, cval in task.sync_trans.locks_w.locks.items()
                    ])
                )
            )

            # TODO (there maybe seqlocks not unlocked)
            pending_trans = task.sync_trans.trans_r.pending()
            if len(pending_trans) != 0:
                self._record_divider()
                self._record(
                    '[!] ptid {} - reader tran leftover: {}\n\t{}'.format(
                        ptid, len(pending_trans),
                        '\n\t'.join([
                            hex(addr) for addr in sorted(pending_trans)
                        ])
                    )
                )

        # heap region should be cleaned out properly
        self._assert(
            len(self.mem_sizes_pcpu) == 0,
            'global - pcpu info leftover: {}\n\t{}'.format(
                len(self.mem_sizes_pcpu),
                '\n\t'.join([
                    hex(addr) for addr in sorted(self.mem_sizes_pcpu.keys())
                ])
            )
        )

        # TODO (there are still objects in the heap, likely due to radix tree)
        if len(self.mem_sizes_heap) != 0:
            self._record_divider()
            self._record(
                '[!] global - heap info leftover: {}\n\t{}'.format(
                    len(self.mem_sizes_heap),
                    '\n\t'.join([
                        hex(addr) for addr in sorted(self.mem_sizes_heap.keys())
                    ])
                )
            )

        # record race pairs
        self._record_divider()
        for pair, stat in sorted(self.races.items(), key=lambda x: x[1]):
            self._record('{}:{} - {}'.format(pair.src, pair.dst, stat))

    # ledger
    @property
    def ledger(self) -> str:
        return '\n'.join(self.console)

    # shortcut functions
    @classmethod
    def validate(cls, logfile: str) -> str:
        # construct the analyzer
        analyzer = ExecAnalyzer(CompileDatabase(Package_LINUX().path_build))

        # parse and validate the log entries
        with open(logfile, 'rb') as f:
            n, s = analyzer.process_log(f)
            if s > config.OUTPUT_LEDGER_SIZE:
                raise DartAssertFailure('ledger overflowed', '')

            try:
                analyzer.iterate_log(n, f)
            except DartAssertFailure as ae:
                raise ae
            except Exception as ex:
                logging.exception(str(ex))
                raise DartAssertFailure('unexpected errors', analyzer.ledger)

        # return parsed ledger
        return analyzer.ledger

    # blacklist
    def race_blacklist(self, a1: MemAccess, a2: MemAccess) -> bool:
        i1 = self.compdb.insts[a1.hval]
        i2 = self.compdb.insts[a2.hval]

        for i in RACE_BLACKLIST:
            if i in i1.get_locs() or i in i2.get_locs():
                return True

        return False


RACE_BLACKLIST = [
    '<placeholder>',
    # benign race:
    #   cache->free_space_ctl->free_space
    'kernel/linux/fs/btrfs/block-group.c:404:2',
    # reported:
    #   delayed_rsv->full,
    #   https://www.mail-archive.com/linux-btrfs@vger.kernel.org/msg91838.html
    'kernel/linux/fs/btrfs/block-rsv.c:195:52',
]
