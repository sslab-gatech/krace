from typing import cast, Any, BinaryIO, NamedTuple, Union, Optional, \
    List, Dict, Set, Tuple

import struct
import pickle

from enum import Enum
from abc import ABC, abstractmethod
from dataclasses import dataclass
from collections import defaultdict

from dart import SyncInfo, \
    LogType, CtxtType, ExecUnitType, MemType, LockType, QueueType, OrderType
from pkg_linux import Package_LINUX
from racer_parse_compile_data import CompileDatabase, \
    ValueFunc, ValueBlock, ValueInst

from util import read_source_location

import config


class VizPoint(NamedTuple):
    ptid: int
    seq: int
    clk: int

    def __str__(self) -> str:
        return '{}-{}-{}'.format(self.ptid, self.seq, self.clk)

    def __lt__(self, other: Any) -> bool:
        assert isinstance(other, VizPoint)
        assert self.ptid == other.ptid
        assert self.seq == other.seq

        return self.clk < other.clk

    def __gt__(self, other: Any) -> bool:
        assert isinstance(other, VizPoint)
        assert self.ptid == other.ptid
        assert self.seq == other.seq

        return self.clk > other.clk

    def __le__(self, other: Any) -> bool:
        assert isinstance(other, VizPoint)
        assert self.ptid == other.ptid
        assert self.seq == other.seq

        return self.clk <= other.clk

    def __ge__(self, other: Any) -> bool:
        assert isinstance(other, VizPoint)
        assert self.ptid == other.ptid
        assert self.seq == other.seq

        return self.clk >= other.clk

    def __eq__(self, other: Any) -> bool:
        assert isinstance(other, VizPoint)
        return (self.ptid == other.ptid) and \
               (self.seq == other.seq) and \
               (self.clk == other.clk)

    def __ne__(self, other: Any) -> bool:
        assert isinstance(other, VizPoint)
        return (self.ptid != other.ptid) or \
               (self.seq != other.seq) or \
               (self.clk != other.clk)

    def step(self) -> 'VizPoint':
        return VizPoint(self.ptid, self.seq, self.clk + 1)

    @classmethod
    def happens_before(cls, src: 'VizPoint', dst: 'VizPoint') -> Optional[bool]:
        if src.ptid != dst.ptid or src.seq != dst.seq:
            return None
        return src.clk <= dst.clk

    @classmethod
    def parse(cls, pos: str) -> 'VizPoint':
        tok = pos.split('-')
        if len(tok) != 3:
            raise RuntimeError('Invalid position {}'.format(pos))

        return VizPoint(int(tok[0]), int(tok[1]), int(tok[2]))


@dataclass
class VizSlotFork(object):
    kind: ExecUnitType
    hval: int
    func: int
    point: VizPoint
    other: List[VizPoint]
    users: List[VizPoint]


@dataclass
class VizSlotJoin(object):
    kind: ExecUnitType
    hval: int
    func: int
    head: int
    point: VizPoint
    other: List[VizPoint]
    users: List[VizPoint]


@dataclass
class VizSlotQueue(object):
    kind: QueueType
    hval: int
    point: VizPoint
    other: List[VizPoint]
    users: List[VizPoint]


@dataclass
class VizSlotOrder(object):
    kind: OrderType
    addr: int
    objv: int
    point: VizPoint
    users: List[VizPoint]


class VizJointType(Enum):
    FORK = 0
    JOIN = 1
    EMBED = 2
    QUEUE = 3
    ORDER = 4
    FIFO = 5


class VizItem(ABC):

    def __init__(
            self, parent: 'VizFunc'
    ) -> None:
        # links
        self.parent = parent

        # reverse links
        self.parent.items.append(self)
        self.parent.unit.children.append(self)

        # position in the globally serialized trace
        runtime = self.parent.unit.parent.parent
        self.gcnt = runtime.count
        runtime.count += 1

        # error mark
        self.error = []  # type: List[str]

    @abstractmethod
    def icon(self) -> str:
        raise RuntimeError('Method not implemented')

    @abstractmethod
    def desc(self) -> str:
        raise RuntimeError('Method not implemented')

    def code(self) -> Optional[str]:
        return None

    @property
    def unit(self) -> 'VizExec':
        return self.parent.unit

    @property
    def task(self) -> 'VizTask':
        return self.unit.parent

    def chain(self) -> List['VizFunc']:
        res = []  # type: List[VizFunc]

        cur = self.parent  # type: Optional[VizFunc]
        while cur is not None:
            res.append(cur)
            cur = cur.call_from

        return res

    def locate(self) -> VizPoint:
        return self.unit.loc_item(self)

    def record(self) -> None:
        text = '{} <{}-{}-{}> {} {}'.format(
            '  ' * self.parent.depth,
            self.task.ptid, self.unit.seq, self.unit.clk,
            self.icon(), self.desc()
        )
        self.task.parent.records.append(text)

    def add_error(self, text: str) -> None:
        self.error.append(text)


class VizItemError(VizItem):

    def __init__(
            self, parent: 'VizFunc',
            text: str
    ) -> None:
        super().__init__(parent)
        self.text = text
        self.error.append(text)

    def icon(self) -> str:
        return '[!]'

    def desc(self) -> str:
        return self.text


class VizItemStep(VizItem):

    def __init__(
            self, parent: 'VizFunc'
    ) -> None:
        super().__init__(parent)
        # compensate for the missing clock incremental
        self.parent.unit.clk += 1

    def icon(self) -> str:
        return '^^^'

    def desc(self) -> str:
        return ''


# CTXT
class VizItemCtxtRun(VizItem):

    def __init__(
            self, parent: 'VizFunc',
            kind: ExecUnitType, hval: int
    ) -> None:
        super().__init__(parent)
        self.kind = kind
        self.hval = hval

    def icon(self) -> str:
        return '==='

    def desc(self) -> str:
        return '{}: {}'.format(self.kind.name, self.hval)


class VizItemCtxtEnd(VizItem):

    def __init__(
            self, parent: 'VizFunc',
            kind: ExecUnitType, hval: int
    ) -> None:
        super().__init__(parent)
        self.kind = kind
        self.hval = hval

    def icon(self) -> str:
        return '==='

    def desc(self) -> str:
        return '{}: {}'.format(self.kind.name, self.hval)


# EXEC
class VizItemExecPause(VizItem):

    def __init__(
            self, parent: 'VizFunc',
            info: int, hval: int
    ) -> None:
        super().__init__(parent)
        self.info = info
        self.hval = hval

    def icon(self) -> str:
        return '|-X'

    def desc(self) -> str:
        return str(self.hval)


class VizItemExecResume(VizItem):

    def __init__(
            self, parent: 'VizFunc',
            info: int, hval: int
    ) -> None:
        super().__init__(parent)
        self.info = info
        self.hval = hval

    def icon(self) -> str:
        return '|X-'

    def desc(self) -> str:
        return str(self.hval)


class VizItemFuncEnter(VizItem):

    def __init__(
            self, parent: 'VizFunc',
            func: 'VizFunc'
    ) -> None:
        super().__init__(parent)
        self.func = func

    def icon(self) -> str:
        return '|->'

    def desc(self) -> str:
        return self.func.func.name


class VizItemFuncExit(VizItem):

    def __init__(
            self, parent: 'VizFunc',
            func: 'VizFunc'
    ) -> None:
        super().__init__(parent)
        self.func = func

    def icon(self) -> str:
        return '|<-'

    def desc(self) -> str:
        return self.func.func.name


# COV
class VizItemCFGBlock(VizItem):

    def __init__(
            self, parent: 'VizFunc',
            block: ValueBlock
    ) -> None:
        super().__init__(parent)
        self.block = block

    def icon(self) -> str:
        return '---'

    def desc(self) -> str:
        return str(self.block.hval)

    def code(self) -> Optional[str]:
        func = self.block.get_parent()
        return '{} -- {}'.format(func.get_parent().name, func.name)


# ASYNC
class VizItemForkRegister(VizItem):

    def __init__(
            self, parent: 'VizFunc',
            slot: VizSlotFork
    ) -> None:
        super().__init__(parent)
        self.slot = slot

    def icon(self) -> str:
        return '<->'

    def desc(self) -> str:
        return '{}: {} [{}]'.format(
            self.slot.kind.name, self.slot.hval, hex(self.slot.func)
        )


class VizItemForkCancel(VizItem):

    def __init__(
            self, parent: 'VizFunc',
            slot: VizSlotFork
    ) -> None:
        super().__init__(parent)
        self.slot = slot

    def icon(self) -> str:
        return '>-<'

    def desc(self) -> str:
        return '{}: {} [{}]'.format(
            self.slot.kind.name, self.slot.hval, hex(self.slot.func)
        )


class VizItemForkAttach(VizItem):

    def __init__(
            self, parent: 'VizFunc',
            slot: VizSlotFork
    ) -> None:
        super().__init__(parent)
        self.slot = slot

    def icon(self) -> str:
        return '>->'

    def desc(self) -> str:
        return '{}: {} [{}]'.format(
            self.slot.kind.name, self.slot.hval, hex(self.slot.func)
        )


class VizItemJoinArrive(VizItem):

    def __init__(
            self, parent: 'VizFunc',
            slot: VizSlotJoin
    ) -> None:
        super().__init__(parent)
        self.slot = slot

    def icon(self) -> str:
        return '<+>'

    def desc(self) -> str:
        return '{}: {} [{}]'.format(
            self.slot.kind.name, self.slot.hval, hex(self.slot.func)
        )


class VizItemJoinPass(VizItem):

    def __init__(
            self, parent: 'VizFunc',
            slot: VizSlotJoin
    ) -> None:
        super().__init__(parent)
        self.slot = slot

    def icon(self) -> str:
        return '>+<'

    def desc(self) -> str:
        return '{}: {} [{}]'.format(
            self.slot.kind.name, self.slot.hval, hex(self.slot.func)
        )


class VizItemMemAlloc(VizItem):

    def __init__(
            self, parent: 'VizFunc',
            mem: 'VizMem'
    ) -> None:
        super().__init__(parent)
        self.mem = mem

    def icon(self) -> str:
        return '(+)'

    def desc(self) -> str:
        return '{}: {} [{}]'.format(
            self.mem.kind.name[0], hex(self.mem.addr), self.mem.size
        )


class VizItemMemFree(VizItem):

    def __init__(
            self, parent: 'VizFunc',
            mem: 'VizMem'
    ) -> None:
        super().__init__(parent)
        self.mem = mem

    def icon(self) -> str:
        return '(-)'

    def desc(self) -> str:
        return '{}: {} [{}]'.format(
            self.mem.kind.name[0], hex(self.mem.addr), self.mem.size
        )


class VizItemMemRead(VizItem):

    def __init__(
            self, parent: 'VizFunc',
            inst: ValueInst, addr: int, size: int
    ) -> None:
        super().__init__(parent)
        self.inst = inst
        self.addr = addr
        self.size = size

    def icon(self) -> str:
        return '<<<'

    def desc(self) -> str:
        return '{} [{}]'.format(
            hex(self.addr), self.size
        )

    def code(self) -> Optional[str]:
        return '{} -- {}'.format(self.inst.get_locs(), self.inst.text)


class VizItemMemWrite(VizItem):

    def __init__(
            self, parent: 'VizFunc',
            inst: ValueInst, addr: int, size: int
    ) -> None:
        super().__init__(parent)
        self.inst = inst
        self.addr = addr
        self.size = size

    def icon(self) -> str:
        return '>>>'

    def desc(self) -> str:
        return '{} [{}]'.format(
            hex(self.addr), self.size
        )

    def code(self) -> Optional[str]:
        return '{} -- {}'.format(self.inst.get_locs(), self.inst.text)


# LOCK
class VizItemLockAcquire(VizItem):

    def __init__(
            self, parent: 'VizFunc',
            lock: int, rdwr: bool, kind: LockType
    ) -> None:
        super().__init__(parent)
        self.lock = lock
        self.rdwr = rdwr
        self.kind = kind

    def icon(self) -> str:
        return '|+|'

    def desc(self) -> str:
        return '{}: {} {}'.format(
            self.kind.name, 'E' if self.rdwr else 'S', hex(self.lock)
        )


class VizItemLockRelease(VizItem):

    def __init__(
            self, parent: 'VizFunc',
            lock: int, rdwr: bool, kind: LockType
    ) -> None:
        super().__init__(parent)
        self.lock = lock
        self.rdwr = rdwr
        self.kind = kind

    def icon(self) -> str:
        return '|-|'

    def desc(self) -> str:
        return '{}: {} {}'.format(
            self.kind.name, 'E' if self.rdwr else 'S', hex(self.lock)
        )


# QUEUE
class VizItemQueueArrive(VizItem):

    def __init__(
            self, parent: 'VizFunc',
            slot: VizSlotQueue
    ) -> None:
        super().__init__(parent)
        self.slot = slot

    def icon(self) -> str:
        return '<=+'

    def desc(self) -> str:
        return '{}: {}'.format(
            self.slot.kind.name, hex(self.slot.hval)
        )


class VizItemQueueNotify(VizItem):

    def __init__(
            self, parent: 'VizFunc',
            slot: VizSlotQueue
    ) -> None:
        super().__init__(parent)
        self.slot = slot

    def icon(self) -> str:
        return '+=>'

    def desc(self) -> str:
        return '{}: {}'.format(
            self.slot.kind.name, hex(self.slot.hval)
        )


# ORDER
class VizItemOrderPublish(VizItem):

    def __init__(
            self, parent: 'VizFunc',
            addr: int, kind: OrderType
    ) -> None:
        super().__init__(parent)
        self.addr = addr
        self.kind = kind

    def icon(self) -> str:
        return '+->'

    def desc(self) -> str:
        return '{}: {}'.format(
            self.kind.name, hex(self.addr)
        )


class VizItemOrderSubscribe(VizItem):

    def __init__(
            self, parent: 'VizFunc',
            addr: int, kind: OrderType
    ) -> None:
        super().__init__(parent)
        self.addr = addr
        self.kind = kind

    def icon(self) -> str:
        return '<-+'

    def desc(self) -> str:
        return '{}: {}'.format(
            self.kind.name, hex(self.addr)
        )


class VizItemOrderDeposit(VizItem):

    def __init__(
            self, parent: 'VizFunc',
            slot: VizSlotOrder
    ) -> None:
        super().__init__(parent)
        self.slot = slot

    def icon(self) -> str:
        return '+->'

    def desc(self) -> str:
        return '{}: {} [{}]'.format(
            self.slot.kind.name, hex(self.slot.addr), hex(self.slot.objv)
        )


class VizItemOrderConsume(VizItem):

    def __init__(
            self, parent: 'VizFunc',
            slot: VizSlotOrder
    ) -> None:
        super().__init__(parent)
        self.slot = slot

    def icon(self) -> str:
        return '<-+'

    def desc(self) -> str:
        return '{}: {} [{}]'.format(
            self.slot.kind.name, hex(self.slot.addr), hex(self.slot.objv)
        )


# MARK
class VizItemMark(VizItem):

    def __init__(
            self, parent: 'VizFunc',
            hval: int, vars: List[int]
    ) -> None:
        super().__init__(parent)
        self.hval = hval
        self.vars = vars

    def icon(self) -> str:
        return '[*]'

    def desc(self) -> str:
        return '[{}] {}'.format(
            self.hval, ', '.join([str(i) for i in self.vars])
        )


class VizMem(object):

    def __init__(
            self, addr: int, size: int, kind: MemType
    ) -> None:
        # basic
        self.addr = addr
        self.size = size
        self.kind = kind

        # alloc and free
        self.item_alloc = None  # type: Optional[VizItemMemAlloc]
        self.item_free = None  # type: Optional[VizItemMemFree]

    @property
    def site_alloc(self) -> VizItemMemAlloc:
        assert self.item_alloc is not None
        return self.item_alloc

    @property
    def site_free(self) -> VizItemMemFree:
        assert self.item_free is not None
        return self.item_free


class VizFunc(object):

    def __init__(
            self, base: Union['VizFunc', 'VizExec'],
            func: ValueFunc, addr: int
    ) -> None:
        # basic
        self.func = func
        self.addr = addr

        # links
        if isinstance(base, VizExec):
            self.unit = base
            self.call_from = None
        else:
            self.unit = base.unit
            self.call_from = base

        self.call_into = []  # type: List[VizFunc]

        # items
        self.items = []  # type: List[VizItem]

    @property
    def task(self) -> 'VizTask':
        return self.unit.parent

    @property
    def depth(self) -> int:
        if self.call_from is None:
            return 0

        return self.call_from.depth + 1

    @classmethod
    def create_unit_base(cls, unit: 'VizExec') -> 'VizFunc':
        return VizFunc(
            unit,
            # create a fake ValueFunc to mark the base of a unit
            ValueFunc(0, '{}-{}'.format(unit.parent.ptid, unit.seq)),
            0
        )


class VizLockMapImpl(object):

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


class VizLockMap(object):

    def __init__(self) -> None:
        self.locks_r = VizLockMapImpl()
        self.locks_w = VizLockMapImpl()

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


class VizTranInfo(object):

    def __init__(self) -> None:
        self.begin = None  # type: Optional[VizPoint]
        self.retry = None  # type: Optional[VizPoint]


class VizTranMapImpl(object):

    def __init__(self) -> None:
        self.trans = defaultdict(VizTranInfo)  # type: Dict[int, VizTranInfo]

    def add_tran(self, tran: int, point: VizPoint) -> Optional[VizPoint]:
        """
        return <None>: first addition
        return <point>: location of the last transaction retry
        """
        prior = self.trans[tran].retry
        self.trans[tran].begin = point
        self.trans[tran].retry = None
        return prior

    def del_tran(self, tran: int, point: VizPoint) -> Optional[VizPoint]:
        """
        return <None>: no prior transaction found
        return <point>: location of the transaction begin
        """
        prior = self.trans[tran].begin
        self.trans[tran].retry = point
        return prior

    def has_tran(self, tran: int) -> bool:
        return tran in self.trans

    def lockset_candidates(self) -> Set[int]:
        # NOTE: this is just candidate lockset, not actual lockset
        return set(self.trans.keys())

    def pending(self) -> Set[int]:
        return {i for i, v in self.trans.items() if v.retry is None}


class VizTranMap(object):

    def __init__(self) -> None:
        self.trans_r = VizTranMapImpl()
        self.locks_w = VizLockMapImpl()

    def add_tran_r(self, tran: int, point: VizPoint) -> Optional[VizPoint]:
        return self.trans_r.add_tran(tran, point)

    def del_tran_r(self, tran: int, point: VizPoint) -> Optional[VizPoint]:
        return self.trans_r.del_tran(tran, point)

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
class VizMemAccess(object):
    inst: ValueInst
    point: VizPoint
    sync_locks: Set[int]
    sync_trans: Set[int]


class VizMemCell(object):

    def __init__(self) -> None:
        self.readers = {}  # type: Dict[int, List[VizMemAccess]]
        self.writers = {}  # type: Dict[int, List[VizMemAccess]]


class VizDataRace(NamedTuple):
    addr: int
    src: VizMemAccess
    dst: VizMemAccess


class VizExec(object):

    def __init__(
            self, parent: 'VizTask',
            kind: ExecUnitType, hval: int, seq: int
    ) -> None:
        # basic
        self.kind = kind
        self.hval = hval
        self.seq = seq

        # links
        self.parent = parent
        self.children = []  # type: List[VizItem]

        # state
        self.cursor = None  # type: Optional[VizFunc]
        self.clk = 0
        self.paused = 0
        self.exited = False

        # stack
        self.stack = [
            VizFunc.create_unit_base(self)
        ]

        # memory
        self.mem_local_info = {}  # type: Dict[int, VizMem]

        # sync
        self.sync_locks = VizLockMap()
        self.sync_trans = VizTranMap()

        # embed
        self.embed_from = None  # type: Optional[VizPoint]
        self.embed_into = {}  # type: Dict[VizPoint, VizExec]

        # async
        self.fork_from = None  # type: Optional[VizSlotFork]
        self.fork_done = False
        self.fork_into = []  # type: List[VizSlotFork]

        self.join_into = None  # type: Optional[VizSlotJoin]
        self.join_done = False
        self.join_from = []  # type: List[VizSlotJoin]

        # queue
        self.queue_from = []  # type: List[VizSlotQueue]
        self.queue_into = []  # type: List[VizSlotQueue]

        # order
        self.order_from = []  # type: List[VizSlotOrder]
        self.order_into = []  # type: List[VizSlotOrder]

        # aggregated dependencies
        self.deps_on = {}  # type: Dict[VizPoint, Dict[VizPoint, VizJointType]]
        self.deps_by = {}  # type: Dict[VizPoint, Dict[VizPoint, VizJointType]]

        # dump the first item
        item = VizItemCtxtRun(self.cur, self.kind, hval)
        item.record()

    @property
    def cur(self) -> VizFunc:
        return self.stack[-1]

    def add_func(self, func: ValueFunc, addr: int) -> None:
        cur = self.cur
        obj = VizFunc(cur, func, addr)

        # mark that current function calls the new func
        cur.call_into.append(obj)

        # add the new func on top of the stack
        self.stack.append(obj)

    def pop_func(self) -> None:
        # pop the func from the call stack
        self.stack.pop()

    def add_item(self, item: VizItem) -> None:
        self.children.append(item)
        self.cur.items.append(item)

    def loc_item(self, item: VizItem) -> VizPoint:
        idx = self.children.index(item)
        assert idx >= 0
        return VizPoint(self.parent.ptid, self.seq, idx)

    def set_fork_from(self, slot: VizSlotFork) -> None:
        assert self.fork_from is None
        self.fork_from = slot
        slot.users.append(self.snapshot)

    def set_join_into(self, slot: VizSlotJoin) -> None:
        assert self.join_into is None
        self.join_into = slot
        slot.users.append(self.snapshot)

    @property
    def snapshot(self) -> VizPoint:
        return VizPoint(self.parent.ptid, self.seq, self.clk)

    def check(self) -> None:
        # make sure that we did accounting correctly
        assert self.clk + 1 == len(self.children)


class VizTask(object):

    def __init__(
            self, parent: 'VizRuntime',
            ptid: int
    ) -> None:
        # basic
        self.ptid = ptid

        # links
        self.parent = parent
        self.children = []  # type: List[VizExec]

        # state
        self.nseq = 0
        self.hold = None  # type: Optional[VizExec]
        self.stack = []  # type: List[VizExec]
        self.last_unit = None  # type: Optional[VizExec]

    @property
    def cur(self) -> VizExec:
        return self.stack[-1]

    def add(self, kind: ExecUnitType, hval: int) -> None:
        # we cannot add or pop while in bg
        assert self.hold is None

        # check if this unit is embedded (must be before unit creation)
        if len(self.stack) == 0:
            host = None  # type: Optional[VizExec]
        else:
            host = self.stack[-1]
            assert not host.exited

        # create the new unit
        unit = VizExec(self, kind, hval, self.nseq)
        self.nseq += 1
        self.stack.append(unit)

        # keep it in children (as it will be popped from stack on exit)
        self.children.append(unit)

        # link with embed
        if host is not None:
            unit.embed_from = host.snapshot
            host.embed_into[host.snapshot] = unit

            # add dependencies
            self.parent.link(host.snapshot, unit.snapshot, VizJointType.EMBED)

            # reserve the step
            step = VizItemStep(host.cur)
            step.record()

        # connect it with the last exited unit
        last = self.last_unit
        if last is not None:
            self.parent.link(last.snapshot, unit.snapshot, VizJointType.FIFO)

    def pop(self) -> None:
        # we cannot add or pop while in bg
        assert self.hold is None

        # pop it from the stack, modify the cursor
        unit = self.stack.pop()

        # link with embed
        if unit.embed_from is not None:
            host = self.cur
            self.parent.link(unit.snapshot, host.snapshot, VizJointType.EMBED)

    def bg(self) -> None:
        assert self.hold is None
        self.hold = self.stack.pop()

    def fg(self) -> None:
        assert self.hold is not None
        self.stack.append(self.hold)
        self.hold = None

    def check(self) -> None:
        # make sure that the unit stack is cleared
        assert self.hold is None
        assert len(self.stack) == 0

        # make sure that we did accounting correctly
        assert self.nseq == len(self.children)

        # delegate checks to children
        for i in self.children:
            i.check()

    def title(self) -> str:
        return '{}: {}'.format(self.ptid, CtxtType.from_ptid(self.ptid).name)


class VizRuntime(object):

    def __init__(self) -> None:
        # load the compilation database
        self.compdb = CompileDatabase(Package_LINUX().path_build)

        # number of items processed
        self.count = 0

        # initialize states
        self.tasks = {}  # type: Dict[int, VizTask]

        self.slots_fork = {}  # type: Dict[int, VizSlotFork]
        self.slots_join = {}  # type: Dict[int, VizSlotJoin]

        self.slots_queue = {}  # type: Dict[int, VizSlotQueue]
        self.slots_order = {}  # type: Dict[int, VizSlotOrder]

        self.mem_info_heap = {}  # type: Dict[int, VizMem]
        self.mem_info_pcpu = {}  # type: Dict[int, VizMem]

        self.cells = {}  # type: Dict[int, VizMemCell]
        self.races = []  # type: List[VizDataRace]

        self.cache_hb = {}  # type: Dict[Tuple[VizPoint, VizPoint], bool]

        # records
        self.records = []  # type: List[str]

    def process(self, path: str) -> None:
        with open(path, 'rb') as f:
            self._process(f)

    # look-up by point
    def _get_task(self, point: VizPoint) -> VizTask:
        return self.tasks[point.ptid]

    def _get_unit(self, point: VizPoint) -> VizExec:
        task = self._get_task(point)
        return task.children[point.seq]

    def _get_item(self, point: VizPoint) -> VizItem:
        unit = self._get_unit(point)
        return unit.children[point.clk]

    # link two points
    def link(self, src: VizPoint, dst: VizPoint, kind: VizJointType) -> None:
        unit_src = self._get_unit(src)
        unit_dst = self._get_unit(dst)

        if dst not in unit_dst.deps_on:
            unit_dst.deps_on[dst] = {src: kind}
        else:
            assert src not in unit_dst.deps_on[dst]
            unit_dst.deps_on[dst][src] = kind

        if src not in unit_src.deps_by:
            unit_src.deps_by[src] = {dst: kind}
        else:
            assert dst not in unit_src.deps_by[src]
            unit_src.deps_by[src][dst] = kind

    # happens-before
    def _happens_before(
            self,
            src: VizPoint, dst: VizPoint,
            hist: Dict[Tuple[VizPoint, VizPoint], bool],
            stks: List[Tuple[VizPoint, VizPoint]]
    ) -> bool:
        # return cached results
        key = (src, dst)
        if key in hist:
            return hist[key]

        # return same-unit ordering
        res = VizPoint.happens_before(src, dst)
        if res is not None:
            hist[key] = res
            return res

        # check for cycles
        if key in stks:
            raise RuntimeError('LOOP IN HAPPENS-BEFORE: {} --> {}\n{}'.format(
                src, dst,
                '\n'.join(['{} --> {}'.format(p[0], p[1]) for p in stks])
            ))

        # default to not happens before
        stks.append(key)
        res = False

        # recurse on dependencies
        unit = self._get_unit(dst)
        for k, v in unit.deps_on.items():
            # it does not make sense to check points after the dst timestamp
            if k > dst:
                continue

            # if src --> dep && dep --> dst, then, src --> dst
            for dep in v:
                res = self._happens_before(src, dep, hist, stks)
                if res:
                    break

            if res:
                break

        # check stack integrity
        h_src, h_dst = stks.pop()
        assert h_src == src and h_dst == dst

        # save the results
        hist[key] = res
        return res

    def happens_before(self, src: VizPoint, dst: VizPoint) -> bool:
        return self._happens_before(src, dst, self.cache_hb, [])

    # race checks
    def _check_race(
            self, src: VizMemAccess, dst: VizMemAccess, addr: int, rw: bool
    ) -> None:
        # TODO (now we ignore races when both parties are in interrupt)
        if CtxtType.from_ptid(src.point.ptid) != CtxtType.TASK and \
                CtxtType.from_ptid(dst.point.ptid) != CtxtType.TASK:
            return

        # TODO (ignore executions in hardirq)
        if CtxtType.from_ptid(src.point.ptid) == CtxtType.HARDIRQ or \
                CtxtType.from_ptid(dst.point.ptid) == CtxtType.HARDIRQ:
            return

        # TODO (there is sth wrong with the BLOCK softirq, ignore them for now)
        if self._get_unit(src.point).kind == ExecUnitType.BLOCK or \
                self._get_unit(dst.point).kind == ExecUnitType.BLOCK:
            return

        # it is not a race if we can establish happens-before relation
        if self.happens_before(src.point, dst.point):
            return

        # it is not a race if protected by locks
        if len(src.sync_locks.intersection(dst.sync_locks)) != 0:
            return

        # find the pending transactions that may invalidate the race
        if rw:
            pending = set()
            for trans_key in src.sync_trans:
                if trans_key in dst.sync_trans:
                    pending.add(trans_key)

            if len(pending) != 0:
                # TODO save to candidate pool if we cannot confirm now
                return

        # no locks and no transaction, report as a race
        if not race_blacklist(src, dst):
            self.races.append(VizDataRace(addr, src, dst))

    def _check_mem_cell_reader(
            self, unit: VizExec, inst: ValueInst, addr: int
    ) -> None:
        # ignore memory reads on stack
        if addr in unit.mem_local_info:
            return

        # ignore memory writes on percpu
        if addr in self.mem_info_pcpu:
            return

        ptid = unit.parent.ptid

        # get the cell (create the cell if not exist)
        if addr not in self.cells:
            self.cells[addr] = VizMemCell()

        cell = self.cells[addr]
        if ptid not in cell.readers:
            cell.readers[ptid] = []

        # construct the access
        access = VizMemAccess(
            inst=inst,
            point=unit.snapshot,
            sync_locks=unit.sync_locks.lockset_r(),
            sync_trans=unit.sync_trans.transet_r(),
        )

        # check write-read races
        for k, v in cell.writers.items():
            # a task does not race against itself
            if ptid == k:
                continue

            # check against the last access from that task
            another = v[-1]
            self._check_race(another, access, addr, True)

        # put the access to log
        cell.readers[ptid].append(access)

    def _check_mem_cell_writer(
            self, unit: VizExec, inst: ValueInst, addr: int
    ) -> None:
        # ignore memory reads on stack
        if addr in unit.mem_local_info:
            return

        # ignore memory writes on percpu
        if addr in self.mem_info_pcpu:
            return

        ptid = unit.parent.ptid

        # get the cell (create the cell if not exist)
        if addr not in self.cells:
            self.cells[addr] = VizMemCell()

        cell = self.cells[addr]
        if ptid not in cell.writers:
            cell.writers[ptid] = []

        # construct the access
        access = VizMemAccess(
            inst=inst,
            point=unit.snapshot,
            sync_locks=unit.sync_locks.lockset_w(),
            sync_trans=unit.sync_trans.transet_w(),
        )

        # check read-write races
        for k, v in cell.readers.items():
            # a task does not race against itself
            if ptid == k:
                continue

            # check against the last access from that task
            another = v[-1]
            self._check_race(another, access, addr, True)

        # check write-write races
        for k, v in cell.writers.items():
            # a task does not race against itself
            if ptid == k:
                continue

            # check against the last access from that task
            another = v[-1]
            self._check_race(another, access, addr, False)

        # put the access to log
        cell.writers[ptid].append(access)

    # CTXT: generic
    def _handle_ctxt_enter(
            self, ptid: int, kind: ExecUnitType, hval: int
    ) -> None:
        if ptid not in self.tasks:
            self.tasks[ptid] = VizTask(self, ptid)

        self.tasks[ptid].add(kind, hval)

    def _handle_ctxt_exit(
            self, ptid: int, kind: ExecUnitType, hval: int
    ) -> None:
        cur = self.tasks[ptid].cur

        # check that ctxt exited match with ctxt entered
        assert cur.kind == kind
        assert cur.hval == hval

        # check that the pause/resume pair are balanced
        assert cur.paused == 0

        # check that the context is still running
        assert not cur.exited

        # check that call stack is all cleared
        assert len(cur.stack) == 1
        assert cur.stack[0].call_from is None

        # check that the local memory (stack memory) is all cleared
        assert len(cur.mem_local_info) == 0

        # check that all locks are unlocked
        assert len(cur.sync_locks.locks_w.locks) == 0
        assert len(cur.sync_locks.locks_r.locks) == 0
        assert len(cur.sync_trans.locks_w.locks) == 0
        # NOTE: there may be pending transaction reads
        # assert len(cur.sync_trans.trans_r.pending()) == 0

        # check that async are properly exited
        if cur.fork_from is not None:
            assert cur.fork_done

        if cur.join_into is not None:
            assert cur.join_done

        # one last item
        item = VizItemCtxtEnd(cur.cur, cur.kind, cur.hval)
        item.record()
        cur.clk += 1  # compensate the clock

        # ctxt can only be re-enabled with _handle_ctxt_enter()
        cur.exited = True
        task = cur.parent
        task.pop()

        # make it the last unit
        task.last_unit = cur

    # CTXT and ASYNC: fork-style
    def _handle_fork_register(
            self, unit: VizExec, kind: ExecUnitType, hval: int, func: int
    ) -> None:
        # we cannot have double registration of the same fork-func
        assert hval not in self.slots_fork

        # create a slot and put it in our fork-queue
        slot = VizSlotFork(kind, hval, func, unit.snapshot, [], [])
        unit.fork_into.append(slot)

        # put it globally so others can consume it
        self.slots_fork[hval] = slot

        # add the item
        item = VizItemForkRegister(unit.cur, slot)
        item.record()

    def _handle_fork_cancel(
            self, unit: VizExec, kind: ExecUnitType, hval: int, func: int
    ) -> None:
        # we must fetch a matched slot
        slot = self.slots_fork[hval]
        assert slot.kind == kind
        assert slot.hval == hval
        assert slot.func == func

        # make sure that the slot exists in its owners fork-queue
        # NOTE: for fork-style async,
        #       not only the unit that registers it may cancel it, other
        #       units may also cancel it (e.g., a queued delayed_work)
        assert slot in self._get_unit(slot.point).fork_into

        # make sure that the slot has not been consumed
        # NOTE: for fork-style async,
        #       a consumed async call cannot be cancelled
        assert len(slot.users) == 0

        # establish dependency
        self.link(slot.point, unit.snapshot, VizJointType.QUEUE)
        for point in slot.other:
            self.link(point, unit.snapshot, VizJointType.QUEUE)

        # mark that the slot is gone
        del self.slots_fork[hval]

        # add the item
        item = VizItemForkCancel(unit.cur, slot)
        item.record()

    def _handle_fork_attach(
            self, unit: VizExec, kind: ExecUnitType, hval: int, func: int
    ) -> None:
        # we must fetch a matched slot
        slot = self.slots_fork[hval]
        assert slot.kind == kind
        assert slot.hval == hval
        assert slot.func == func

        # make sure that the slot has not been consumed
        # NOTE: for fork-style async,
        #       a consumed async call cannot be attached
        assert len(slot.users) == 0

        # add the attachment
        slot.other.append(unit.snapshot)

        # add the item
        item = VizItemForkAttach(unit.cur, slot)
        item.record()

    def _handle_fork_ctxt_entered(
            self, unit: VizExec, kind: ExecUnitType, hval: int, func: int
    ) -> None:
        # we must fetch a matched slot
        slot = self.slots_fork[hval]
        assert slot.kind == kind
        assert slot.hval == hval
        assert slot.func == func

        # mark that we are forked from this slot
        unit.set_fork_from(slot)

        # add dependencies
        self.link(slot.point, unit.snapshot, VizJointType.FORK)
        for point in slot.other:
            self.link(point, unit.snapshot, VizJointType.FORK)

        # mark that the slot is consumed
        # NOTE: for fork-style async,
        #       only one recipient may exist and the slot is consumed on enter
        del self.slots_fork[hval]

    def _handle_fork_ctxt_exited(
            self, unit: VizExec, kind: ExecUnitType, hval: int, func: int
    ) -> None:
        # find the fork-style slot from our queue and make sure it is a match
        slot = unit.fork_from
        assert slot is not None
        assert slot.kind == kind
        assert slot.hval == hval
        assert slot.func == func

        # we guarantee that such slot does not exist globally anymore
        if hval in self.slots_fork:
            assert self.slots_fork[hval] != slot

        # make that we are done with the fork
        unit.fork_done = True

    def _handle_ctxt_enter_into_fork(
            self, ptid: int, kind: ExecUnitType, hval: int, func: int
    ) -> None:
        self._handle_ctxt_enter(ptid, kind, hval)
        self._handle_fork_ctxt_entered(self.tasks[ptid].cur, kind, hval, func)

    def _handle_ctxt_exit_from_fork(
            self, ptid: int, kind: ExecUnitType, hval: int, func: int
    ) -> None:
        self._handle_fork_ctxt_exited(self.tasks[ptid].cur, kind, hval, func)
        self._handle_ctxt_exit(ptid, kind, hval)

    # CTXT and ASYNC: join-style
    def _handle_join_arrive(
            self, unit: VizExec, kind: ExecUnitType, hval: int, func: int,
            head: int
    ) -> None:
        # we cannot have double registration of the same join-func
        assert hval not in self.slots_join

        # create a slot and put it in the join-queue
        slot = VizSlotJoin(kind, hval, func, head, unit.snapshot, [], [])
        unit.join_from.append(slot)

        # put it globally so others can consume it
        self.slots_join[hval] = slot

        # add the item
        item = VizItemJoinArrive(unit.cur, slot)
        item.record()

        # reserve the step item too
        step = VizItemStep(unit.cur)
        step.record()

    def _handle_join_pass(
            self, unit: VizExec, kind: ExecUnitType, hval: int, func: int
    ) -> None:
        # we must fetch a matched slot
        slot = self.slots_join[hval]
        assert slot.kind == kind
        assert slot.hval == hval
        assert slot.func == func

        # make sure that the slot exists in the waiter's join-queue
        # NOTE: for join-style async,
        #       either the waiter or the notifier may pass it
        if unit.parent.ptid == slot.point.ptid:
            # we are the waiter
            assert slot in unit.join_from

            # if no one notifies us, then we are too late, try queue_notify
            if len(slot.users) == 0 and slot.head in self.slots_queue:
                qlot = self.slots_queue[slot.head]

                # mark that we queued from this slot
                unit.queue_from.append(qlot)
                qlot.users.append(unit.snapshot)

                # add dependencies
                self.link(qlot.point, unit.snapshot, VizJointType.QUEUE)
                for point in qlot.other:
                    self.link(point, unit.snapshot, VizJointType.QUEUE)

                # mark that the slot is gone
                del self.slots_queue[slot.head]

        else:
            # we are the notifier
            assert len(slot.users) >= 1

            target_ptid = slot.users[0].ptid
            assert unit.parent.ptid == target_ptid
            for user in slot.users:
                assert user.ptid == target_ptid

            assert slot in self._get_unit(slot.point).join_from

        # mark that the slot is gone
        del self.slots_join[hval]

        # add the item
        item = VizItemJoinPass(unit.cur, slot)
        item.record()

    def _handle_join_ctxt_entered(
            self, unit: VizExec, kind: ExecUnitType, hval: int, func: int
    ) -> None:
        # we must fetch a matched slot
        slot = self.slots_join[hval]
        assert slot.kind == kind
        assert slot.hval == hval
        assert slot.func == func

        # mark that we have joined into this slot
        unit.set_join_into(slot)

        # add dependencies (fork-side)
        self.link(slot.point, unit.snapshot, VizJointType.FORK)
        for point in slot.other:
            self.link(point, unit.snapshot, VizJointType.FORK)

        # add dependencies (join-side)
        step = slot.point.step()
        item = self._get_item(step)
        assert isinstance(item, VizItemStep)
        self.link(unit.snapshot, step, VizJointType.JOIN)

        for point in slot.other:
            step = point.step()
            item = self._get_item(step)
            assert isinstance(item, VizItemStep)
            self.link(unit.snapshot, point, VizJointType.JOIN)

        # NOTE: for join-style async,
        #       the recipient may entered multiple times and thus,
        #       we do not mark consumption here.

    def _handle_join_ctxt_exited(
            self, unit: VizExec, kind: ExecUnitType, hval: int, func: int
    ) -> None:
        # find the join-style slot from our queue and make sure it is a match
        slot = unit.join_into
        assert slot is not None
        assert slot.kind == kind
        assert slot.hval == hval
        assert slot.func == func

        # NOTE: unlike fork-style func, we do not know whether the slot globally
        # is still there or not, and thus, we do not check

        # mark that we are done with the join
        unit.join_done = True

    def _handle_ctxt_enter_into_join(
            self, ptid: int, kind: ExecUnitType, hval: int, func: int
    ) -> None:
        self._handle_ctxt_enter(ptid, kind, hval)
        self._handle_join_ctxt_entered(self.tasks[ptid].cur, kind, hval, func)

    def _handle_ctxt_exit_from_join(
            self, ptid: int, kind: ExecUnitType, hval: int, func: int
    ) -> None:
        self._handle_join_ctxt_exited(self.tasks[ptid].cur, kind, hval, func)
        self._handle_ctxt_exit(ptid, kind, hval)

    # EXEC: pause and resume
    def _handle_exec_pause(
            self, unit: VizExec, info: int, hval: int
    ) -> None:
        # state update
        unit.paused += 1

        # add the item
        item = VizItemExecPause(unit.cur, info, hval)
        item.record()

    def _handle_exec_resume(
            self, unit: VizExec, info: int, hval: int
    ) -> None:
        # state upate
        unit.paused -= 1

        # add the item
        item = VizItemExecResume(unit.cur, info, hval)
        item.record()

    # EXEC: func
    def _handle_func_enter(
            self, unit: VizExec, hval: int, addr: int
    ) -> None:
        func = self.compdb.funcs[hval]

        # save the current function
        cur = unit.cur

        # push to the call stack
        unit.add_func(func, addr)

        # add the item
        item = VizItemFuncEnter(cur, unit.cur)
        item.record()

    def _handle_func_exit(
            self, unit: VizExec, hval: int, addr: int
    ) -> None:
        func = self.compdb.funcs[hval]

        # save the current function
        cur = unit.cur

        # check that func exited match with func entered
        assert cur.func == func
        assert cur.addr == addr

        # pop from the call stack
        unit.pop_func()

        # add the item
        item = VizItemFuncExit(unit.cur, cur)
        item.record()

    # COV
    def _handle_cov_cfg(
            self, unit: VizExec, hval: int
    ) -> None:
        block = self.compdb.blocks[hval]

        # add the item
        item = VizItemCFGBlock(unit.cur, block)
        item.record()

    # MEM: alloc and free
    def _handle_mem_alloc_impl(
            self, unit: VizExec, repo: Dict[int, VizMem],
            kind: MemType, addr: int, size: int
    ) -> None:
        # construct the mem object
        mobj = VizMem(addr, size, kind)

        # add to repo and check for non-duplication
        for i in range(size):
            assert (addr + i) not in repo
            repo[addr + i] = mobj

        # add the item
        item = VizItemMemAlloc(unit.cur, mobj)
        item.record()

        # register the item with the memory object
        mobj.item_alloc = item

    def _handle_mem_alloc(
            self, unit: VizExec, kind: MemType, addr: int, size: int
    ) -> None:
        if kind == MemType.STACK:
            self._handle_mem_alloc_impl(
                unit, unit.mem_local_info, kind, addr, size
            )

        elif kind == MemType.HEAP:
            self._handle_mem_alloc_impl(
                unit, self.mem_info_heap, kind, addr, size
            )

        elif kind == MemType.PERCPU:
            self._handle_mem_alloc_impl(
                unit, self.mem_info_pcpu, kind, addr, size
            )

        else:
            assert False

    def _handle_mem_free_impl(
            self, unit: VizExec, repo: Dict[int, VizMem],
            kind: MemType, addr: int
    ) -> None:
        # lookup the memory object
        assert addr in repo
        mobj = repo[addr]

        # the address has to be the object start
        assert mobj.addr == addr
        assert mobj.kind == kind

        # add to repo and check for non-duplication
        for i in range(mobj.size):
            assert repo[addr + i] == mobj
            del repo[addr + i]

        # add the item
        item = VizItemMemFree(unit.cur, mobj)
        item.record()

        # register the item with the memory object
        mobj.item_free = item

    def _handle_mem_free(
            self, unit: VizExec, kind: MemType, addr: int
    ) -> None:
        if kind == MemType.STACK:
            self._handle_mem_free_impl(
                unit, unit.mem_local_info, kind, addr
            )

        elif kind == MemType.HEAP:
            self._handle_mem_free_impl(
                unit, self.mem_info_heap, kind, addr
            )

        elif kind == MemType.PERCPU:
            self._handle_mem_free_impl(
                unit, self.mem_info_pcpu, kind, addr
            )

        else:
            assert False

    # MEM: read and write
    def _handle_mem_read(
            self, unit: VizExec, hval: int, addr: int, size: int
    ) -> None:
        # check instruction is on stack
        inst = self.compdb.insts[hval]
        assert inst.get_parent().get_parent().hval == unit.cur.func.hval

        # race check
        for i in range(size):
            self._check_mem_cell_reader(unit, inst, addr + i)

        # add the item
        item = VizItemMemRead(unit.cur, inst, addr, size)
        item.record()

    def _handle_mem_write(
            self, unit: VizExec, hval: int, addr: int, size: int
    ) -> None:
        # check instruction is on stack
        inst = self.compdb.insts[hval]
        assert inst.get_parent().get_parent().hval == unit.cur.func.hval

        # race check
        for i in range(size):
            self._check_mem_cell_writer(unit, inst, addr + i)

        # add the item
        item = VizItemMemWrite(unit.cur, inst, addr, size)
        item.record()

    # LOCK:
    def _handle_lock_acquire(
            self, unit: VizExec, kind: LockType, info: int, lock: int
    ) -> None:
        # build the sync pack
        sync = SyncInfo(info)
        assert sync.is_succ

        # add into lockset
        if sync.is_rw:
            depth = unit.sync_locks.add_lock_w(lock)
        else:
            depth = unit.sync_locks.add_lock_r(lock)

        # generic locks cannot be nested
        if kind == LockType.GEN:
            assert depth == 0

        # add the item
        item = VizItemLockAcquire(unit.cur, lock, sync.is_rw, kind)
        item.record()

    def _handle_lock_release(
            self, unit: VizExec, kind: LockType, info: int, lock: int
    ) -> None:
        # build the sync pack
        sync = SyncInfo(info)
        assert sync.is_succ

        # del from lockset
        if sync.is_rw:
            depth = unit.sync_locks.del_lock_w(lock)
        else:
            depth = unit.sync_locks.del_lock_r(lock)

        # generic locks cannot be nested
        if kind == LockType.GEN:
            assert depth == 1
        elif kind == LockType.RCU:
            assert depth >= 1

        # add the item
        item = VizItemLockRelease(unit.cur, lock, sync.is_rw, kind)
        item.record()

    # TRAN
    def _handle_tran_acquire(
            self, unit: VizExec, kind: LockType, info: int, lock: int
    ) -> None:
        # build the sync pack
        sync = SyncInfo(info)
        assert sync.is_succ

        # hold errors
        error = None  # type: Optional[str]

        # add into transet
        if sync.is_rw:
            depth = unit.sync_trans.add_lock_w(lock)

            # seq locks (writer) cannot be nested
            if kind == LockType.SEQ:
                assert depth == 0
        else:
            prior = unit.sync_trans.add_tran_r(lock, unit.snapshot)

            # TODO (we don't know whether seqlock_read can be nested, so, warn)
            if kind == LockType.SEQ:
                if prior is None:
                    error = 'acquired without release'

        # add the item
        item = VizItemLockAcquire(unit.cur, lock, sync.is_rw, kind)
        item.record()

        # record errors
        if error is not None:
            item.add_error(error)

    def _handle_tran_release(
            self, unit: VizExec, kind: LockType, info: int, lock: int
    ) -> None:
        # build the sync pack
        sync = SyncInfo(info)
        assert sync.is_succ

        # del from lockset
        if sync.is_rw:
            depth = unit.sync_trans.del_lock_w(lock)

            # seq locks (writer) cannot be nested
            if kind == LockType.SEQ:
                assert depth == 1
        else:
            prior = unit.sync_trans.del_tran_r(lock, unit.snapshot)

            # seq locks (reader) may be nested, but has to have a prior first
            assert prior is not None

        # add the item
        item = VizItemLockRelease(unit.cur, lock, sync.is_rw, kind)
        item.record()

    # QUEUE
    def _handle_queue_arrive(
            self, unit: VizExec, kind: QueueType, hval: int
    ) -> None:
        # find or create the queue slot
        if hval in self.slots_queue:
            slot = self.slots_queue[hval]
            assert slot.kind == kind
            assert slot.hval == hval

            # mark that we queued from this slot
            unit.queue_from.append(slot)
            slot.users.append(unit.snapshot)

            # add dependencies
            self.link(slot.point, unit.snapshot, VizJointType.QUEUE)
            for point in slot.other:
                self.link(point, unit.snapshot, VizJointType.QUEUE)

            # mark that the slot is gone
            del self.slots_queue[hval]

        else:
            # create a mock slot if the queue can be passed without notifier
            slot = VizSlotQueue(kind, hval, unit.snapshot, [], [])

        # add the item
        item = VizItemQueueArrive(unit.cur, slot)
        item.record()

    def _handle_queue_notify(
            self, unit: VizExec, kind: QueueType, hval: int
    ) -> None:
        # see whether we are the first to notify
        if hval in self.slots_queue:
            slot = self.slots_queue[hval]

            # make sure that the slot has not been consumed
            assert len(slot.users) == 0

            # add as attachment
            slot.other.append(unit.snapshot)
        else:
            slot = VizSlotQueue(kind, hval, unit.snapshot, [], [])
            unit.queue_into.append(slot)

            # put it globally so others can consume it
            self.slots_queue[hval] = slot

        # add the item
        item = VizItemQueueNotify(unit.cur, slot)
        item.record()

    # ORDER
    def _handle_order_publish(
            self, unit: VizExec, kind: OrderType, addr: int
    ) -> None:
        '''
        # create the slot and put it in the forward-facing list
        slot = VizSlotOrder(kind, addr, 0, unit.snapshot, [])
        unit.order_into.append(slot)

        # put it globally so others can consume it
        self.slots_order[addr] = slot
        '''

        # add the item
        item = VizItemOrderPublish(unit.cur, addr, kind)
        item.record()

    def _handle_order_subscribe(
            self, unit: VizExec, kind: OrderType, addr: int
    ) -> None:
        '''
        if addr in self.slots_order:
            slot = self.slots_order[addr]
            assert slot.kind == kind

            # mark that we consumed this slot
            unit.order_from.append(slot)
            slot.users.append(unit.snapshot)

            # add dependencies
            self.link(slot.point, unit.snapshot, VizJointType.ORDER)
        '''

        # add the item
        item = VizItemOrderSubscribe(unit.cur, addr, kind)
        item.record()

    def _handle_order_deposit(
            self, unit: VizExec, kind: OrderType, addr: int, objv: int
    ) -> None:
        # create the slot and put it in the forward-facing list
        slot = VizSlotOrder(kind, addr, objv, unit.snapshot, [])
        unit.order_into.append(slot)

        # put it globally so others can consume it
        self.slots_order[addr] = slot

        # add the item
        item = VizItemOrderDeposit(unit.cur, slot)
        item.record()

    def _handle_order_consume(
            self, unit: VizExec, kind: OrderType, addr: int
    ) -> None:
        # we must fetch a matched slot
        slot = self.slots_order[addr]
        assert slot.kind == kind

        # mark that we consumed this slot
        unit.order_from.append(slot)
        slot.users.append(unit.snapshot)

        # add dependencies
        self.link(slot.point, unit.snapshot, VizJointType.ORDER)

        # add the item
        item = VizItemOrderConsume(unit.cur, slot)
        item.record()

    # main processing function
    def _process(self, b: BinaryIO) -> None:
        # parse meta
        n, _ = struct.unpack('QQ', b.read(16))

        # parse data
        log_types = {i.value: i for i in LogType}

        for i in range(n):
            cval, ptid, info, hval = struct.unpack('IIQQ', b.read(24))
            code = log_types[cval]

            # SYS
            if code == LogType.SYS_LAUNCH:
                assert i == 0
                self._handle_ctxt_enter(0, ExecUnitType.ROOT, 0)
                continue

            if code == LogType.SYS_FINISH:
                assert i == n - 1
                self._handle_ctxt_exit(0, ExecUnitType.ROOT, 0)
                continue

            # CTXT
            if code == LogType.CTXT_SYSCALL_ENTER:
                self._handle_ctxt_enter(ptid, ExecUnitType.SYSCALL, hval)
                continue

            if code == LogType.CTXT_SYSCALL_EXIT:
                self._handle_ctxt_exit(ptid, ExecUnitType.SYSCALL, hval)
                continue

            if code == LogType.CTXT_RCU_ENTER:
                addr = struct.unpack('Q', b.read(8))[0]
                self._handle_ctxt_enter_into_fork(
                    ptid, ExecUnitType.RCU, hval, addr
                )
                continue

            if code == LogType.CTXT_RCU_EXIT:
                addr = struct.unpack('Q', b.read(8))[0]
                self._handle_ctxt_exit_from_fork(
                    ptid, ExecUnitType.RCU, hval, addr
                )
                continue

            if code == LogType.CTXT_WORK_ENTER:
                addr = struct.unpack('Q', b.read(8))[0]
                self._handle_ctxt_enter_into_fork(
                    ptid, ExecUnitType.WORK, hval, addr
                )
                continue

            if code == LogType.CTXT_WORK_EXIT:
                addr = struct.unpack('Q', b.read(8))[0]
                self._handle_ctxt_exit_from_fork(
                    ptid, ExecUnitType.WORK, hval, addr
                )
                continue

            if code == LogType.CTXT_TASK_ENTER:
                addr = struct.unpack('Q', b.read(8))[0]
                self._handle_ctxt_enter_into_fork(
                    ptid, ExecUnitType.TASK, hval, addr
                )
                continue

            if code == LogType.CTXT_TASK_EXIT:
                addr = struct.unpack('Q', b.read(8))[0]
                self._handle_ctxt_exit_from_fork(
                    ptid, ExecUnitType.TASK, hval, addr
                )
                continue

            if code == LogType.CTXT_TIMER_ENTER:
                addr = struct.unpack('Q', b.read(8))[0]
                self._handle_ctxt_enter_into_fork(
                    ptid, ExecUnitType.TIMER, hval, addr
                )
                continue

            if code == LogType.CTXT_TIMER_EXIT:
                addr = struct.unpack('Q', b.read(8))[0]
                self._handle_ctxt_exit_from_fork(
                    ptid, ExecUnitType.TIMER, hval, addr
                )
                continue

            if code == LogType.CTXT_KRUN_ENTER:
                addr = struct.unpack('Q', b.read(8))[0]
                self._handle_ctxt_enter_into_fork(
                    ptid, ExecUnitType.KRUN, hval, addr
                )
                continue

            if code == LogType.CTXT_KRUN_EXIT:
                addr = struct.unpack('Q', b.read(8))[0]
                self._handle_ctxt_exit_from_fork(
                    ptid, ExecUnitType.KRUN, hval, addr
                )
                continue

            if code == LogType.CTXT_BLOCK_ENTER:
                addr = struct.unpack('Q', b.read(8))[0]
                self._handle_ctxt_enter_into_fork(
                    ptid, ExecUnitType.BLOCK, hval, addr
                )
                continue

            if code == LogType.CTXT_BLOCK_EXIT:
                addr = struct.unpack('Q', b.read(8))[0]
                self._handle_ctxt_exit_from_fork(
                    ptid, ExecUnitType.BLOCK, hval, addr
                )
                continue

            if code == LogType.CTXT_IPI_ENTER:
                addr = struct.unpack('Q', b.read(8))[0]
                self._handle_ctxt_enter_into_fork(
                    ptid, ExecUnitType.IPI, hval, addr
                )
                continue

            if code == LogType.CTXT_IPI_EXIT:
                addr = struct.unpack('Q', b.read(8))[0]
                self._handle_ctxt_exit_from_fork(
                    ptid, ExecUnitType.IPI, hval, addr
                )
                continue

            if code == LogType.CTXT_CUSTOM_ENTER:
                addr = struct.unpack('Q', b.read(8))[0]
                self._handle_ctxt_enter_into_fork(
                    ptid, ExecUnitType.CUSTOM, hval, addr
                )
                continue

            if code == LogType.CTXT_CUSTOM_EXIT:
                addr = struct.unpack('Q', b.read(8))[0]
                self._handle_ctxt_exit_from_fork(
                    ptid, ExecUnitType.CUSTOM, hval, addr
                )
                continue

            if code == LogType.EVENT_WAIT_NOTIFY_ENTER:
                addr = struct.unpack('Q', b.read(8))[0]
                self._handle_ctxt_enter_into_join(
                    ptid, ExecUnitType.WAIT_NOTIFY, hval, addr
                )
                continue

            if code == LogType.EVENT_WAIT_NOTIFY_EXIT:
                addr = struct.unpack('Q', b.read(8))[0]
                self._handle_ctxt_exit_from_join(
                    ptid, ExecUnitType.WAIT_NOTIFY, hval, addr
                )
                continue

            if code == LogType.EVENT_SEMA_NOTIFY_ENTER:
                addr = struct.unpack('Q', b.read(8))[0]
                self._handle_ctxt_enter_into_join(
                    ptid, ExecUnitType.SEMA_NOTIFY, hval, addr
                )
                continue

            if code == LogType.EVENT_SEMA_NOTIFY_EXIT:
                addr = struct.unpack('Q', b.read(8))[0]
                self._handle_ctxt_exit_from_join(
                    ptid, ExecUnitType.SEMA_NOTIFY, hval, addr
                )
                continue

            # from now on, we have a task
            task = self.tasks[ptid]

            if code == LogType.EXEC_BACKGROUND:
                task.bg()
                continue

            if code == LogType.EXEC_FOREGROUND:
                task.fg()
                continue

            # from now on, we have a unit
            unit = task.cur
            unit.clk += 1

            # EXEC
            if code == LogType.EXEC_PAUSE:
                self._handle_exec_pause(unit, info, hval)
                continue

            if code == LogType.EXEC_RESUME:
                self._handle_exec_resume(unit, info, hval)
                continue

            if code == LogType.EXEC_FUNC_ENTER:
                addr = struct.unpack('Q', b.read(8))[0]
                self._handle_func_enter(unit, hval, addr)
                continue

            if code == LogType.EXEC_FUNC_EXIT:
                addr = struct.unpack('Q', b.read(8))[0]
                self._handle_func_exit(unit, hval, addr)
                continue

            # ASYNC
            if code == LogType.ASYNC_RCU_REGISTER:
                addr = struct.unpack('Q', b.read(8))[0]
                self._handle_fork_register(unit, ExecUnitType.RCU, hval, addr)
                continue

            if code == LogType.ASYNC_WORK_REGISTER:
                addr = struct.unpack('Q', b.read(8))[0]
                self._handle_fork_register(unit, ExecUnitType.WORK, hval, addr)
                continue

            if code == LogType.ASYNC_WORK_CANCEL:
                addr = struct.unpack('Q', b.read(8))[0]
                self._handle_fork_cancel(unit, ExecUnitType.WORK, hval, addr)
                continue

            if code == LogType.ASYNC_WORK_ATTACH:
                addr = struct.unpack('Q', b.read(8))[0]
                self._handle_fork_attach(unit, ExecUnitType.WORK, hval, addr)
                continue

            if code == LogType.ASYNC_TASK_REGISTER:
                addr = struct.unpack('Q', b.read(8))[0]
                self._handle_fork_register(unit, ExecUnitType.TASK, hval, addr)
                continue

            if code == LogType.ASYNC_TASK_CANCEL:
                addr = struct.unpack('Q', b.read(8))[0]
                self._handle_fork_cancel(unit, ExecUnitType.TASK, hval, addr)
                continue

            if code == LogType.ASYNC_TIMER_REGISTER:
                addr = struct.unpack('Q', b.read(8))[0]
                self._handle_fork_register(unit, ExecUnitType.TIMER, hval, addr)
                continue

            if code == LogType.ASYNC_TIMER_CANCEL:
                addr = struct.unpack('Q', b.read(8))[0]
                self._handle_fork_cancel(unit, ExecUnitType.TIMER, hval, addr)
                continue

            if code == LogType.ASYNC_TIMER_ATTACH:
                addr = struct.unpack('Q', b.read(8))[0]
                self._handle_fork_attach(unit, ExecUnitType.TIMER, hval, addr)
                continue

            if code == LogType.ASYNC_KRUN_REGISTER:
                addr = struct.unpack('Q', b.read(8))[0]
                self._handle_fork_register(unit, ExecUnitType.KRUN, hval, addr)
                continue

            if code == LogType.ASYNC_BLOCK_REGISTER:
                addr = struct.unpack('Q', b.read(8))[0]
                self._handle_fork_register(unit, ExecUnitType.BLOCK, hval, addr)
                continue

            if code == LogType.ASYNC_IPI_REGISTER:
                addr = struct.unpack('Q', b.read(8))[0]
                self._handle_fork_register(unit, ExecUnitType.IPI, hval, addr)
                continue

            if code == LogType.ASYNC_CUSTOM_REGISTER:
                addr = struct.unpack('Q', b.read(8))[0]
                self._handle_fork_register(
                    unit, ExecUnitType.CUSTOM, hval, addr
                )
                continue

            if code == LogType.ASYNC_CUSTOM_ATTACH:
                addr = struct.unpack('Q', b.read(8))[0]
                self._handle_fork_attach(unit, ExecUnitType.CUSTOM, hval, addr)
                continue

            # EVENT (queue)
            if code == LogType.EVENT_QUEUE_ARRIVE:
                self._handle_queue_arrive(unit, QueueType.WQ, hval)
                continue

            if code == LogType.EVENT_QUEUE_NOTIFY:
                self._handle_queue_notify(unit, QueueType.WQ, hval)
                continue

            # EVENT (wait/sema)
            if code == LogType.EVENT_WAIT_ARRIVE:
                addr, head = struct.unpack('QQ', b.read(16))
                self._handle_join_arrive(
                    unit, ExecUnitType.WAIT_NOTIFY, hval, addr, head
                )
                continue

            if code == LogType.EVENT_WAIT_PASS:
                addr = struct.unpack('Q', b.read(8))[0]
                self._handle_join_pass(
                    unit, ExecUnitType.WAIT_NOTIFY, hval, addr
                )
                continue

            if code == LogType.EVENT_SEMA_ARRIVE:
                addr, head = struct.unpack('QQ', b.read(16))
                self._handle_join_arrive(
                    unit, ExecUnitType.SEMA_NOTIFY, hval, addr, head
                )
                continue

            if code == LogType.EVENT_SEMA_PASS:
                addr = struct.unpack('Q', b.read(8))[0]
                self._handle_join_pass(
                    unit, ExecUnitType.SEMA_NOTIFY, hval, addr
                )
                continue

            # COV
            if code == LogType.COV_CFG:
                self._handle_cov_cfg(unit, hval)
                continue

            # MEM
            if code == LogType.MEM_STACK_PUSH:
                addr, size = struct.unpack('QQ', b.read(16))
                self._handle_mem_alloc(unit, MemType.STACK, addr, size)
                continue

            if code == LogType.MEM_STACK_POP:
                addr, size = struct.unpack('QQ', b.read(16))
                self._handle_mem_free(unit, MemType.STACK, addr)
                continue

            if code == LogType.MEM_HEAP_ALLOC:
                addr, size = struct.unpack('QQ', b.read(16))
                self._handle_mem_alloc(unit, MemType.HEAP, addr, size)
                continue

            if code == LogType.MEM_HEAP_FREE:
                addr = struct.unpack('Q', b.read(8))[0]
                self._handle_mem_free(unit, MemType.HEAP, addr)
                continue

            if code == LogType.MEM_PERCPU_ALLOC:
                addr, size = struct.unpack('QQ', b.read(16))
                self._handle_mem_alloc(unit, MemType.PERCPU, addr, size)
                continue

            if code == LogType.MEM_PERCPU_FREE:
                addr = struct.unpack('Q', b.read(8))[0]
                self._handle_mem_free(unit, MemType.PERCPU, addr)
                continue

            if code == LogType.MEM_READ:
                addr, size = struct.unpack('QQ', b.read(16))
                self._handle_mem_read(unit, hval, addr, size)
                continue

            if code == LogType.MEM_WRITE:
                addr, size = struct.unpack('QQ', b.read(16))
                self._handle_mem_write(unit, hval, addr, size)
                continue

            # SYNC
            if code == LogType.SYNC_GEN_LOCK:
                lock = struct.unpack('Q', b.read(8))[0]
                self._handle_lock_acquire(unit, LockType.GEN, info, lock)
                continue

            if code == LogType.SYNC_GEN_UNLOCK:
                lock = struct.unpack('Q', b.read(8))[0]
                self._handle_lock_release(unit, LockType.GEN, info, lock)
                continue

            if code == LogType.SYNC_SEQ_LOCK:
                lock = struct.unpack('Q', b.read(8))[0]
                self._handle_tran_acquire(unit, LockType.SEQ, info, lock)
                continue

            if code == LogType.SYNC_SEQ_UNLOCK:
                lock = struct.unpack('Q', b.read(8))[0]
                self._handle_tran_release(unit, LockType.SEQ, info, lock)
                continue

            if code == LogType.SYNC_RCU_LOCK:
                lock = struct.unpack('Q', b.read(8))[0]
                self._handle_lock_acquire(unit, LockType.RCU, info, lock)
                continue

            if code == LogType.SYNC_RCU_UNLOCK:
                lock = struct.unpack('Q', b.read(8))[0]
                self._handle_lock_release(unit, LockType.RCU, info, lock)
                continue

            # ORDER
            if code == LogType.ORDER_PS_PUBLISH:
                addr = struct.unpack('Q', b.read(8))[0]
                self._handle_order_publish(unit, OrderType.RCU, addr)
                continue

            if code == LogType.ORDER_PS_SUBSCRIBE:
                addr = struct.unpack('Q', b.read(8))[0]
                self._handle_order_subscribe(unit, OrderType.RCU, addr)
                continue

            if code == LogType.ORDER_OBJ_DEPOSIT:
                addr, objv = struct.unpack('QQ', b.read(16))
                self._handle_order_deposit(unit, OrderType.OBJ, addr, objv)
                continue

            if code == LogType.ORDER_OBJ_CONSUME:
                addr = struct.unpack('Q', b.read(8))[0]
                self._handle_order_consume(unit, OrderType.OBJ, addr)
                continue

            # MARK
            if code == LogType.MARK_V0:
                item = VizItemMark(unit.cur, hval, [])
                item.record()
                continue

            if code == LogType.MARK_V1:
                var0 = struct.unpack('Q', b.read(8))[0]
                item = VizItemMark(unit.cur, hval, [var0])
                item.record()
                continue

            if code == LogType.MARK_V2:
                var0, var1 = struct.unpack('QQ', b.read(16))
                item = VizItemMark(unit.cur, hval, [var0, var1])
                item.record()
                continue

            if code == LogType.MARK_V3:
                var0, var1, var2 = struct.unpack('QQQ', b.read(24))
                item = VizItemMark(unit.cur, hval, [var0, var1, var2])
                item.record()
                continue

        # check the overall results
        for ptid, task in self.tasks.items():
            task.check()

        # check there is no async slots left
        assert len(self.slots_fork) == 0
        assert len(self.slots_join) == 0

        # check there is no memory objects left
        assert len(self.mem_info_pcpu) == 0
        # TODO (fixme)
        # assert len(self.mem_info_heap) == 0
        for mobj in set(self.mem_info_heap.values()):
            mobj.site_alloc.add_error('dangling')

    def dump_races(self, path: str) -> None:
        with open(path, 'w') as f:
            table = {}  # type: Dict[Tuple[int, int], int]

            for race in self.races:
                f.write(
                    'RACE <{}:{} |=| {}:{}> [{}:{}] {}\n'.format(
                        race.src.point, self._get_item(race.src.point).gcnt,
                        race.dst.point, self._get_item(race.dst.point).gcnt,
                        race.src.inst.hval, race.dst.inst.hval,
                        race.addr
                    )
                )
                f.write(
                    'SRC: [{}] <{}> {}: {} [{}] |{}| {}\n'.format(
                        race.src.point,
                        CtxtType.from_ptid(race.src.point.ptid).name,
                        race.src.inst.hval,
                        race.src.inst.get_parent().get_parent().name,
                        race.src.inst.get_locs(),
                        load_source(race.src.inst),
                        race.src.inst.text
                    )
                )
                f.write(
                    'DST: [{}] <{}> {}: {} [{}] |{}| {}\n'.format(
                        race.dst.point,
                        CtxtType.from_ptid(race.dst.point.ptid).name,
                        race.dst.inst.hval,
                        race.dst.inst.get_parent().get_parent().name,
                        race.dst.inst.get_locs(),
                        load_source(race.dst.inst),
                        race.dst.inst.text
                    )
                )
                f.write('\n')

                key = (race.src.inst.hval, race.dst.inst.hval)
                if key not in table:
                    table[key] = 1
                else:
                    table[key] += 1

            f.write('-' * 80 + '\n')
            for pair, stat in sorted(table.items(), key=lambda x: x[1]):
                f.write('{}:{} - {}\n'.format(pair[0], pair[1], stat))


class VizPack(object):

    def __init__(self, tasks: Dict[int, VizTask]) -> None:
        self.tasks = tasks

    def save(self, path: str) -> None:
        with open(path, 'wb') as f:
            pickle.dump(self, f)

    @classmethod
    def load(cls, path: str) -> 'VizPack':
        with open(path, 'rb') as f:
            return cast(VizPack, pickle.load(f))

    # look-up by point
    def get_task(self, point: VizPoint) -> VizTask:
        return self.tasks[point.ptid]

    def get_unit(self, point: VizPoint) -> VizExec:
        task = self.get_task(point)
        return task.children[point.seq]

    def get_item(self, point: VizPoint) -> VizItem:
        unit = self.get_unit(point)
        return unit.children[point.clk]

    # context
    def _scope(
            self,
            unit: VizExec, hist: Set[VizExec], depth: int, limit: Optional[int],
            link: Set[VizPoint],
    ) -> None:
        # only trace to a limited depth
        if limit is not None and depth == limit:
            return
        depth += 1

        # avoid cycles
        if unit in hist:
            return
        hist.add(unit)

        # trace upward
        for dst, val in unit.deps_on.items():
            for src, kind in val.items():
                link.add(dst)
                link.add(src)
                self._scope(self.get_unit(src), hist, depth, limit, link)

        # trace downward
        for src, val in unit.deps_by.items():
            for dst, kind in val.items():
                link.add(src)
                link.add(dst)
                self._scope(self.get_unit(dst), hist, depth, limit, link)

    def scope(self, unit: VizExec, depth: Optional[int]) -> Tuple[
        Set[VizExec], Set[VizPoint]
    ]:
        hist = set()  # type: Set[VizExec]
        link = set()  # type: Set[VizPoint]
        self._scope(unit, hist, 0, depth, link)
        return hist, link

    def _scope_with_edge_src(
            self,
            unit: VizExec,
            hist: Set[VizExec],
            node: Set[VizPoint],
            edge: Dict[Tuple[VizPoint, VizPoint], VizJointType],
            depth: Dict[VizJointType, int],
            limit: Dict[VizJointType, Optional[int]],
    ) -> None:
        # avoid cycles
        if unit in hist:
            return
        hist.add(unit)

        # trace
        for dst, val in unit.deps_on.items():
            for src, kind in val.items():
                # per-category limitation
                if limit[kind] is not None and depth[kind] == limit[kind]:
                    continue

                # incremental depth for that type
                new_depth = depth.copy()
                new_depth[kind] += 1

                # linking
                node.add(dst)
                node.add(src)
                edge[(src, dst)] = kind

                # recurse
                self._scope_with_edge_src(
                    self.get_unit(src), hist, node, edge, new_depth, limit
                )

    def _scope_with_edge_dst(
            self,
            unit: VizExec,
            hist: Set[VizExec],
            node: Set[VizPoint],
            edge: Dict[Tuple[VizPoint, VizPoint], VizJointType],
            depth: Dict[VizJointType, int],
            limit: Dict[VizJointType, Optional[int]],
    ) -> None:
        # avoid cycles
        if unit in hist:
            return
        hist.add(unit)

        # trace
        for src, val in unit.deps_by.items():
            for dst, kind in val.items():
                # per-category limitation
                if limit[kind] is not None and depth[kind] == limit[kind]:
                    continue

                # incremental depth for that type
                new_depth = depth.copy()
                new_depth[kind] += 1

                # linking
                node.add(src)
                node.add(dst)
                edge[(src, dst)] = kind

                # recurse
                self._scope_with_edge_dst(
                    self.get_unit(dst), hist, node, edge, new_depth, limit
                )

    # WARNING: will get a massive graph without limiting depth
    def scope_with_edge(
            self,
            unit: VizExec,
            limit_src: Dict[VizJointType, Optional[int]],
            limit_dst: Dict[VizJointType, Optional[int]],
    ) -> Tuple[
        Set[VizExec],
        Set[VizPoint],
        Dict[Tuple[VizPoint, VizPoint], VizJointType]
    ]:
        # src side
        hist_src = set()  # type: Set[VizExec]
        node_src = set()  # type: Set[VizPoint]
        edge_src = {}  # type: Dict[Tuple[VizPoint, VizPoint], VizJointType]
        self._scope_with_edge_src(
            unit, hist_src, node_src, edge_src,
            {t: 0 for t in VizJointType}, limit_src
        )

        # dst side
        hist_dst = set()  # type: Set[VizExec]
        node_dst = set()  # type: Set[VizPoint]
        edge_dst = {}  # type: Dict[Tuple[VizPoint, VizPoint], VizJointType]
        self._scope_with_edge_dst(
            unit, hist_dst, node_dst, edge_dst,
            {t: 0 for t in VizJointType}, limit_dst
        )

        # join them
        hist = set()  # type: Set[VizExec]
        hist.update(hist_src)
        hist.update(hist_dst)

        node = set()  # type: Set[VizPoint]
        node.update(node_src)
        node.update(node_dst)

        edge = {}  # type: Dict[Tuple[VizPoint, VizPoint], VizJointType]
        edge.update(edge_src)
        edge.update(edge_dst)

        return hist, node, edge


# source code
def load_source(inst: ValueInst) -> str:
    return ' @@ '.join([
        read_source_location(config.PROJ_PATH + '/' + loc)
        for loc in inst.info
    ])


# blacklist
def race_blacklist(a1: VizMemAccess, a2: VizMemAccess) -> bool:
    l1 = a1.inst.get_locs()
    l2 = a2.inst.get_locs()

    for i in RACE_BLACKLIST:
        if i in l1 or i in l2:
            return True

    return False


RACE_BLACKLIST = [
    '<placeholder>',
    # reported:
    #   if (!drop && (sb->s_flags & SB_ACTIVE))
    'kernel/linux/fs/inode.c:1543:20',
    # reported:
    #   !atomic_read(&inode->i_count) && inode->i_sb->s_flags & SB_ACTIVE)
    'kernel/linux/fs/inode.c:441:52',
    # ignored:
    #   BUG_ON(!(inode->i_state & I_FREEING));
    'kernel/linux/fs/inode.c:557:2',
    # need investigation:
    #   if (!(inode->i_state & (I_DIRTY_ALL | I_SYNC | I_FREEING | I_WILL_FREE)
    'kernel/linux/fs/inode.c:439:15',
    # ignored:
    #   BUG_ON(inode->i_state & I_CLEAR);
    'kernel/linux/fs/inode.c:1579:2',
    # invalid
    #   pending_bios->tail->bi_next = bio;
    'kernel/linux/fs/btrfs/volumes.c:6458:31',
    # invalid
    #   wq = work->wq;
    'kernel/linux/fs/btrfs/async-thread.c:384:13',
    # benign race:
    #   cache->free_space_ctl->free_space
    'kernel/linux/fs/btrfs/block-group.c:408:2',
    # benign race:
    #   cache->cached == BTRFS_CACHE_FINISHED
    #   although this is a race, it does not matter which value it read
    'kernel/linux/fs/btrfs/block-group.h:246:16',
    # benign race:
    #   block_group->cached = ret ? BTRFS_CACHE_ERROR : BTRFS_CACHE_FINISHED
    #   although this is a race, it does not matter which value it read
    'kernel/linux/fs/btrfs/block-group.c:654:22',
    # pending:
    #   fs_info->generation++
    'kernel/linux/fs/btrfs/transaction.c:269:21',
    # pending:
    #  cur_trans->state = TRANS_STATE_COMMIT_START
    'kernel/linux/fs/btrfs/transaction.c:2057:19',
    # ignored:
    #   if (!page->private)
    'kernel/linux/fs/btrfs/disk-io.c:607:13',
    # ignored:
    #   BTRFS_SETGET_STACK_FUNCS(super_generation, struct btrfs_super_block,...
    'kernel/linux/fs/btrfs/ctree.h:2117:1',
    # reported:
    #   if (delayed_refs_rsv->full == 0),
    'kernel/linux/fs/btrfs/transaction.c:495:25',
    # reported:
    #   delayed_rsv->full,
    #   https://www.mail-archive.com/linux-btrfs@vger.kernel.org/msg91838.html
    'kernel/linux/fs/btrfs/block-rsv.c:195:52',
    # reported:
    #   if (unlikely(block_rsv->size == 0))
    'kernel/linux/fs/btrfs/block-rsv.c:391:6',
    # re-use of address:
    #   WARN_ON(pages[i]->mapping);
    'kernel/linux/fs/btrfs/inode.c:635:5',
]
