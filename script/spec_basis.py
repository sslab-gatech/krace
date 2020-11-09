from typing import cast, NewType, TypeVar, Generic, Union, Optional, \
    List, Dict, Set, Tuple

import json
import struct
import hashlib

from abc import ABC, abstractmethod
from enum import Enum
from functools import cmp_to_key
from dataclasses import dataclass, asdict

from spec_const import SPEC_PTR_SIZE, SPEC_PROG_HEAP_OFFSET
from spec_pack import pack_ptr
from spec_random import SPEC_RANDOM
from util_bean import Bean, BeanRef


class Rand(Bean):
    """
    Typed dict, holds the input to kernel in a Lego object.
    """

    lego: BeanRef['Lego']


T_Rand = TypeVar('T_Rand', bound=Rand)
N_Rand = NewType('N_Rand', Rand)


class Kobj(Bean):
    """
    Typed dict, holds the output from kernel in a Lego object
    """

    lego: BeanRef['Lego']


T_Kobj = TypeVar('T_Kobj', bound=Kobj)
N_Kobj = NewType('N_Kobj', Kobj)


class KindSend(Bean, ABC, Generic[T_Rand]):
    """
    Semantic types that assign meaning to input to kernel
    """

    lego: BeanRef['Lego']

    # debug
    def dump(self) -> str:
        note = self.note()
        if len(note) != 0:
            note = '[' + note + ']'
        return self.__class__.__name__[len('KindSend'):] + note

    @abstractmethod
    def note(self) -> str:
        raise RuntimeError('Method not implemented')

    # chain
    @abstractmethod
    def link(self, ctxt: 'Syscall') -> None:
        raise RuntimeError('Method not implemented')

    # memory
    @abstractmethod
    def length(self) -> Optional[int]:
        raise RuntimeError('Method not implemented')

    # builder
    @abstractmethod
    def mk_rand(self) -> T_Rand:
        raise RuntimeError('Method not implemented')

    # operation: engage and remove
    @abstractmethod
    def engage_rand(self, rand: T_Rand, prog: 'Program') -> None:
        raise RuntimeError('Method not implemented')

    @abstractmethod
    def remove_rand(self, rand: T_Rand, prog: 'Program') -> None:
        raise RuntimeError('Method not implemented')

    # operations: mutate and puzzle
    @abstractmethod
    def mutate_rand(self, rand: T_Rand, prog: 'Program') -> None:
        raise RuntimeError('Method not implemented')

    @abstractmethod
    def puzzle_rand(self, rand: T_Rand, prog: 'Program') -> None:
        raise RuntimeError('Method not implemented')

    # operations: update
    @abstractmethod
    def update_rand(self, rand: T_Rand, prog: 'Program') -> None:
        raise RuntimeError('Method not implemented')

    # operations: migrate
    @abstractmethod
    def migrate_rand(
            self,
            rand: T_Rand, orig: T_Rand,
            ctxt: Dict[Bean, Bean], hist: Set['Lego']
    ) -> None:
        raise RuntimeError('Method not implemented')

    # show
    @abstractmethod
    def expo_rand(self, rand: T_Rand) -> str:
        raise RuntimeError('Method not implemented')

    # blob
    @abstractmethod
    def blob_size_rand(self, rand: T_Rand) -> int:
        raise RuntimeError('Method not implemented')

    @abstractmethod
    def blob_hole_rand(self, rand: T_Rand, inst: 'Executable') -> None:
        raise RuntimeError('Method not implemented')

    @abstractmethod
    def blob_data_rand(self, rand: T_Rand, inst: 'Executable') -> bytes:
        raise RuntimeError('Method not implemented')

    @abstractmethod
    def blob_fill_rand(self, rand: T_Rand, inst: 'Executable') -> None:
        raise RuntimeError('Method not implemented')

    # relationship
    @abstractmethod
    def rely_on_rand(self, rand: T_Rand, prog: 'Program') -> Set[int]:
        raise RuntimeError('Method not implemented')


class KindRecv(Bean, ABC, Generic[T_Kobj]):
    """
    Semantic types that assign meaning to input to kernel
    """

    lego: BeanRef['Lego']

    # debug
    def dump(self) -> str:
        note = self.note()
        if len(note) != 0:
            note = '[' + note + ']'
        return self.__class__.__name__[len('KindRecv'):] + note

    @abstractmethod
    def note(self) -> str:
        raise RuntimeError('Method not implemented')

    # chain
    @abstractmethod
    def link(self, ctxt: 'Syscall') -> None:
        raise RuntimeError('Method not implemented')

    # memory
    @abstractmethod
    def length(self) -> Optional[int]:
        raise RuntimeError('Method not implemented')

    # builder
    @abstractmethod
    def mk_kobj(self) -> T_Kobj:
        raise RuntimeError('Method not implemented')

    # operations: engage and remove
    @abstractmethod
    def engage_kobj(self, kobj: T_Kobj, prog: 'Program') -> None:
        raise RuntimeError('Method not implemented')

    @abstractmethod
    def remove_kobj(self, kobj: T_Kobj, prog: 'Program') -> None:
        raise RuntimeError('Method not implemented')

    # show
    @abstractmethod
    def expo_kobj(self, kobj: T_Kobj) -> str:
        raise RuntimeError('Method not implemented')

    # blob
    @abstractmethod
    def blob_size_kobj(self, kobj: T_Kobj) -> int:
        raise RuntimeError('Method not implemented')

    @abstractmethod
    def blob_hole_kobj(self, kobj: T_Kobj, inst: 'Executable') -> None:
        raise RuntimeError('Method not implemented')

    @abstractmethod
    def blob_data_kobj(self, kobj: T_Kobj, inst: 'Executable') -> bytes:
        raise RuntimeError('Method not implemented')

    @abstractmethod
    def blob_fill_kobj(self, kobj: T_Kobj, inst: 'Executable') -> None:
        raise RuntimeError('Method not implemented')

    # relationship
    @abstractmethod
    def rely_on_kobj(self, kobj: T_Kobj, prog: 'Program') -> Set[int]:
        raise RuntimeError('Method not implemented')


class Lego(Bean, ABC, Generic[T_Rand, T_Kobj]):
    """
    Building blocks in the input space.
    """

    ctxt: Optional[BeanRef['Syscall']]
    root: Optional[BeanRef[Union['Lego', 'Arg', 'Ret']]]

    def __init__(self) -> None:
        super().__init__()

        # default values
        self.ctxt = None
        self.root = None

        # indicates whether this lego has Rand or Kobj or both
        self.rand = None  # type: Optional[T_Rand]
        self.kobj = None  # type: Optional[T_Kobj]

        # indicates how many lego depends on this lego
        # (i.e., Rand and Kobj won't be deleted until all rdeps are cleared)
        self.rdeps_rand = set()  # type: Set[Lego]
        self.rdeps_kobj = set()  # type: Set[Lego]

        # indicate the epoch where the Rand and Kobj object are updated
        self.epoch_rand = 0
        self.epoch_kobj = 0

    # debug
    def dump(self) -> str:
        note = self.note()
        if len(note) != 0:
            note = '<' + note + '>'
        return self.__class__.__name__[len('Lego'):] + note

    @abstractmethod
    def note(self) -> str:
        raise RuntimeError('Method not implemented')

    def show(self) -> str:
        return self.expo()

    @abstractmethod
    def expo(self) -> str:
        raise RuntimeError('Method not implemented')

    # chain
    def link(
            self, root: Optional[Union['Lego', 'Arg', 'Ret']], ctxt: 'Syscall'
    ) -> None:
        # ASSERT: link can be called at anytime, enough checks are placed to
        # ensure that once the root and ctxt is set, they cannot be altered

        # set root
        if root is not None:
            if self.root is not None:
                assert self.root.bean == root
            else:
                self.root = BeanRef[Union[Lego, Arg, Ret]](root)

        # set ctxt
        if self.ctxt is not None:
            assert self.ctxt.bean == ctxt

        else:
            self.ctxt = BeanRef[Syscall](ctxt)
            self.link_impl(ctxt)

        # ASSERT: after link
        #   - root may be Arg, Ret, Lego, or None
        #   - ctxt must be set to the correct Syscall

    @abstractmethod
    def link_impl(self, ctxt: 'Syscall') -> None:
        # ASSERT: link_impl can be called only once and is called
        # when ctxt is first set
        raise RuntimeError('Method not implemented')

    # memory
    @abstractmethod
    def length(self) -> Optional[int]:
        raise RuntimeError('Method not implemented')

    # input/output
    # NOTE: both input/output functions guides the allocation of heap slots:
    #   - prepare heap slot for this lego if has_info_send()
    #   - pre-allocate heap slot if this lego (not has_info_send())
    #   - re-associate heap slot if this lego (has_info_send())
    @abstractmethod
    def has_info_send(self) -> bool:
        raise RuntimeError('Method not implemented')

    @abstractmethod
    def has_info_recv(self) -> bool:
        raise RuntimeError('Method not implemented')

    # builders
    def _mk_rand(self) -> None:
        self.rand = self._mk_rand_impl()
        self.rand.lego = BeanRef[Lego](self)

    @abstractmethod
    def _mk_rand_impl(self) -> T_Rand:
        raise RuntimeError('Method not implemented')

    def _mk_kobj(self) -> None:
        self.kobj = self._mk_kobj_impl()
        self.kobj.lego = BeanRef[Lego](self)

    @abstractmethod
    def _mk_kobj_impl(self) -> T_Kobj:
        raise RuntimeError('Method not implemented')

    # operations: engage
    def engage_rand(self, prog: 'Program') -> None:
        # do nothing if we have nothing to send into kernel
        if not self.has_info_send():
            return

        # do nothing if we have already created the Rand object
        if self.rand is not None:
            return

        # create and initialize the Rand object
        self._mk_rand()
        self.engage_rand_impl(prog)

    @abstractmethod
    def engage_rand_impl(self, prog: 'Program') -> None:
        raise RuntimeError('Method not implemented')

    def engage_kobj(self, prog: 'Program') -> None:
        # do nothing if we have nothing to recv from kernel
        if not self.has_info_recv():
            return

        # do nothing if we have already created the Kobj object
        if self.kobj is not None:
            return

        # create and initialize the Kobj object
        self._mk_kobj()
        self.engage_kobj_impl(prog)

    @abstractmethod
    def engage_kobj_impl(self, prog: 'Program') -> None:
        raise RuntimeError('Method not implemented')

    def engage(self, prog: 'Program') -> None:
        self.engage_rand(prog)
        self.engage_kobj(prog)

    # operations: remove
    def remove_rand(self, prog: 'Program') -> None:
        # nothing to remove if we have nothing to send into kernel
        if not self.has_info_send():
            return

        # nothing to remove if we have not created the Rand object
        if self.rand is None:
            return

        # do not remove the Rand object yet until we clear all reverse deps
        if len(self.rdeps_rand) != 0:
            return

        # un-initialize the Rand object and clear it
        self.remove_rand_impl(prog)
        self.rand = None

    @abstractmethod
    def remove_rand_impl(self, prog: 'Program') -> None:
        raise RuntimeError('Method not implemented')

    def remove_kobj(self, prog: 'Program') -> None:
        # nothing to remove if we have nothing to recv from kernel
        if not self.has_info_recv():
            return

        # nothing to remove if we have not created the Kobj object
        if self.kobj is None:
            return

        # do not remove the Kobj object yet until we clear all reverse deps
        if len(self.rdeps_kobj) != 0:
            return

        # un-initialize the Kobj object and clear it
        self.remove_kobj_impl(prog)
        self.kobj = None

    @abstractmethod
    def remove_kobj_impl(self, prog: 'Program') -> None:
        raise RuntimeError('Method not implemented')

    def remove(self, prog: 'Program') -> None:
        self.remove_rand(prog)
        self.remove_kobj(prog)

    # operations: mutate and puzzle
    def mutate_rand(self, prog: 'Program') -> None:
        # the Rand object has to be engaged
        assert self.rand is not None

        # do not alter the Rand twice in one epoch
        if prog.has_epoch_mod(self):
            return

        # alter it
        self.mutate_rand_impl(prog)
        prog.add_epoch_mod(self)

    @abstractmethod
    def mutate_rand_impl(self, prog: 'Program') -> None:
        # ASSERT: upon reaching here, self.rand is guaranteed to be not None
        raise RuntimeError('Method not implemented')

    def puzzle_rand(self, prog: 'Program') -> None:
        # the Rand object has to be engaged
        assert self.rand is not None

        # do not alter the Rand twice in one epoch
        if prog.has_epoch_mod(self):
            return

        # alter it
        self.puzzle_rand_impl(prog)
        prog.add_epoch_mod(self)

    @abstractmethod
    def puzzle_rand_impl(self, prog: 'Program') -> None:
        # ASSERT: upon reaching here, self.rand is guaranteed to be not None
        raise RuntimeError('Method not implemented')

    # operations: update
    def update_rand(self, prog: 'Program') -> None:
        # the Rand object has to be engaged
        assert self.rand is not None

        # always update
        self.update_rand_impl(prog)
        prog.add_epoch_mod(self)

    @abstractmethod
    def update_rand_impl(self, prog: 'Program') -> None:
        # ASSERT: upon reaching here, self.rand is guaranteed to be not None
        raise RuntimeError('Method not implemented')

    # operations: migrate
    def migrate(
            self, other: 'Lego', ctxt: Dict[Bean, Bean], hist: Set['Lego']
    ) -> None:
        if self in hist:
            # do not fall into loops
            return

        hist.add(self)
        self.migrate_impl(other, ctxt, hist)

    @abstractmethod
    def migrate_impl(
            self, other: 'Lego', ctxt: Dict[Bean, Bean], hist: Set['Lego']
    ) -> None:
        raise RuntimeError('Method not implemented')

    # blob
    @abstractmethod
    def blob_size(self) -> int:
        raise RuntimeError('Method not implemented')

    def blob_hole(self, root: Optional['Lego'], inst: 'Executable') -> None:
        # check existence
        if inst.has_hole(self):
            return

        # check root validity
        if self.root is None:
            assert root is None

        elif isinstance(self.root.bean, (Arg, Ret)):
            assert root is None

        else:
            if root is None:
                root = self.root.bean
            else:
                assert root == self.root.bean

            # allows forward cascading only, but not backward
            if not inst.has_hole(root):
                root = None

        # top-down step 1: reserve size for the lego itself
        size = self.blob_size()
        inst.add_hole(self, size, root)

        # top-down step 2: reserve sizes for components (if any)
        self.blob_hole_impl(inst)

    @abstractmethod
    def blob_hole_impl(self, inst: 'Executable') -> None:
        raise RuntimeError('Method not implemented')

    @abstractmethod
    def blob_data(self, inst: 'Executable') -> bytes:
        raise RuntimeError('Method not implemented')

    def blob_fill(self, inst: 'Executable') -> None:
        # get data
        data = self.blob_data(inst)

        # fill the hole
        inst.fill_hole(inst.get_hole(self), data)

        # cascading the filling to components
        self.blob_fill_impl(inst)

    @abstractmethod
    def blob_fill_impl(self, inst: 'Executable') -> None:
        raise RuntimeError('Method not implemented')

    # reverse dependencies
    def add_rdep_rand(self, lego: 'Lego') -> None:
        assert lego not in self.rdeps_rand
        self.rdeps_rand.add(lego)

    def del_rdep_rand(self, lego: 'Lego') -> None:
        assert lego in self.rdeps_rand
        self.rdeps_rand.remove(lego)

    def add_rdep_kobj(self, lego: 'Lego') -> None:
        assert lego not in self.rdeps_kobj
        self.rdeps_kobj.add(lego)

    def del_rdep_kobj(self, lego: 'Lego') -> None:
        assert lego in self.rdeps_kobj
        self.rdeps_kobj.remove(lego)

    # relationship
    @abstractmethod
    def rely_on(self, prog: 'Program') -> Set[int]:
        raise RuntimeError('Method not implemented')


class Field(Bean):
    """
    A wrapper over Lego to hold extra information representing a field
    in a composite type (array, struct, union, etc).
    """

    name: str
    tyid: str
    size: int
    lego: Lego

    # bean
    def validate(self) -> None:
        # size check
        field_size = self.lego.length()
        assert field_size is not None and field_size == self.size

    # debug
    def dump(self) -> str:
        return '{}: {}'.format(self.name, self.lego.dump())


class Arg(Bean):
    """
    A wrapper over Lego to hold extra information representing an argument
    in a syscall.
    """

    name: str
    tyid: str
    size: int
    lego: Lego

    # bean
    def validate(self) -> None:
        # size check
        arg_size = self.lego.length()
        assert arg_size is not None
        assert arg_size == self.size <= SPEC_PTR_SIZE

        # arg does not recv information
        assert not self.lego.has_info_recv()

    # debug
    def dump(self) -> str:
        return '{}: {}'.format(self.name, self.lego.dump())

    def show(self) -> str:
        return self.lego.show()


class Ret(Bean):
    """
    A wrapper over Lego to hold extra information representing a return
    value from a syscall.
    """

    tyid: str
    size: int
    lego: Lego

    # bean
    def validate(self) -> None:
        # size check
        ret_size = self.lego.length()
        assert ret_size is not None
        assert ret_size == self.size <= SPEC_PTR_SIZE

        # ret does not send information
        assert not self.lego.has_info_send()

    # debug
    def dump(self) -> str:
        return self.lego.dump()

    def show(self) -> str:
        return self.lego.show()


class Syscall(Bean):
    """
    A Syscall object essentially consists of a lot of Lego objects
    and charts how these Lego objects are organized.
    """

    snum: int
    name: str
    args: List[Arg]
    retv: Ret

    # debug
    def dump(self) -> str:
        return '{}({}) -> {}'.format(
            self.name,
            ', '.join([i.dump() for i in self.args]),
            self.retv.dump()
        )

    def show(self) -> str:
        return '{}({}) -> {}'.format(
            self.name,
            ', '.join([i.show() for i in self.args]),
            self.retv.show()
        )

    # chain
    def link(self) -> None:
        # link args
        for arg in self.args:
            arg.lego.link(arg, self)

        # link retv
        self.retv.lego.link(self.retv, self)

    # operations: engage and remove
    def engage(self, prog: 'Program') -> None:
        # engage rand in args
        for arg in self.args:
            arg.lego.engage(prog)

        # engage kobj in retv
        self.retv.lego.engage(prog)

    def remove(self, prog: 'Program') -> None:
        # remove rand in args
        for arg in self.args:
            arg.lego.remove(prog)

        # remove kobj in retv
        self.retv.lego.remove(prog)

    # operations: mutate and puzzle
    def mutate(self, prog: 'Program') -> None:
        if len(self.args) == 0:
            return

        p = SPEC_RANDOM.random()

        if p < 0.8:
            # [TOSS] change only one arg
            SPEC_RANDOM.choice(self.args).lego.mutate_rand(prog)

        else:
            # [TOSS] change multiple args at once
            num = SPEC_RANDOM.randint(1, len(self.args))
            for arg in SPEC_RANDOM.sample(self.args, num):
                arg.lego.mutate_rand(prog)

    def puzzle(self, prog: 'Program') -> None:
        if len(self.args) == 0:
            return

        p = SPEC_RANDOM.random()

        if p < 0.8:
            # [DRAG] change only one arg
            SPEC_RANDOM.choice(self.args).lego.puzzle_rand(prog)

        else:
            # [DRAG] change multiple args at once
            num = SPEC_RANDOM.randint(1, len(self.args))
            for arg in SPEC_RANDOM.sample(self.args, num):
                arg.lego.puzzle_rand(prog)

    # operations: update
    def update(self, prog: 'Program') -> None:
        for arg in self.args:
            arg.lego.update_rand(prog)

    # operations: migrate
    def migrate(
            self, other: 'Syscall', ctxt: Dict[Bean, Bean], hist: Set[Lego]
    ) -> None:
        for a1, a2 in zip(self.args, other.args):
            a1.lego.migrate(a2.lego, ctxt, hist)

    # blob
    def blob(self, inst: 'Executable') -> None:
        for arg in self.args:
            arg.lego.blob_hole(None, inst)
            arg.lego.blob_fill(inst)

        self.retv.lego.blob_hole(None, inst)
        self.retv.lego.blob_fill(inst)

    # relationship
    def rely(self, prog: 'Program') -> Set[int]:
        deps = set()  # type: Set[int]
        for arg in self.args:
            deps.update(arg.lego.rely_on(prog))

        return deps


class SyscallGroup(object):

    def __init__(self) -> None:
        self.base = None  # type: Optional[Syscall]
        self.vals = set()  # type: Set[str]
        self.opts = {}  # type: Dict[Syscall, float]

    def set_base(self, base: Syscall, weight: float) -> Syscall:
        assert self.base is None
        self.base = base
        self.add_option(base, weight)
        return base

    def get_base(self) -> Syscall:
        assert self.base is not None
        return self.base

    def add_option(self, option: Syscall, weight: float) -> None:
        assert option.name not in self.vals
        self.vals.add(option.name)
        self.opts[option] = weight

    def finalize(self) -> None:
        for item in self.opts:
            assert item.ready()


class NodeType(Enum):
    GENERIC = 0
    FILE = 1
    DIR = 2
    LINK = 3
    SYM = 4


class PathType(Enum):
    NEW = 0
    EXT = 1


class FdType(Enum):
    NEW = 0
    EXT = 1
    RES = 2


class DirFdType(Enum):
    NEW = 0
    EXT = 1
    RES = 2
    CWD = 3


@dataclass
class Synopsis(object):
    sketch: List[List[str]]

    @staticmethod
    def _cmp_thread(t1: List[str], t2: List[str]) -> int:
        if len(t1) != len(t2):
            return len(t1) - len(t2)

        for i1, i2 in zip(t1, t2):
            if i1 != i2:
                return 1 if i1 > i2 else -1

        return 0

    def _order(self) -> List[List[str]]:
        return sorted(self.sketch, key=cmp_to_key(Synopsis._cmp_thread))

    def codec(self) -> str:
        sketch = self._order()
        hasher = hashlib.sha1()
        for t in sketch:
            hasher.update(struct.pack('I', len(t)))
            for i in t:
                hasher.update(i.encode('charmap'))

        return hasher.hexdigest()

    def match(self, other: 'Synopsis') -> bool:
        if len(self.sketch) != len(other.sketch):
            return False

        sk1 = self._order()
        sk2 = other._order()

        for t1, t2 in zip(sk1, sk2):
            if len(t1) != len(t2):
                return False

            for i1, i2 in zip(t1, t2):
                if i1 != i2:
                    return False

        return True


class Program(object):
    """
    Holds the references and internal data of the generated program
    """

    def __init__(self, ncpu: int) -> None:
        # multi-threading
        self.ncpu = ncpu

        # the sequence of syscalls in the program (sorted by generation order)
        self.syscalls = []  # type: List[Syscall]
        self.syscalls_start = 0

        # syscalls partitioned by threads
        self.thread_main = []  # type: List[Syscall]
        self.thread_subs = []  # type: List[List[Syscall]]
        self.thread_dist = {}  # type: Dict[Syscall, int]

        # resource repositories
        self.repo_path_rand = {}  # type: Dict[NodeType, List[Lego]]

        self.repo_fd_rand = {}  # type: Dict[NodeType, List[Lego]]
        self.repo_fd_kobj = {}  # type: Dict[NodeType, List[Lego]]

        # epoch information
        self.epoch_changes = set()  # type: Set[Lego]

        # initialize
        for i in NodeType:
            self.repo_path_rand[i] = []

            self.repo_fd_rand[i] = []
            self.repo_fd_kobj[i] = []

        for _ in range(self.ncpu):
            self.thread_subs.append([])

    # util
    def lego_index(self, lego: Lego) -> int:
        assert lego.ctxt is not None
        index = self.syscalls.index(lego.ctxt.bean)
        assert index >= 0
        return index

    def lego_in_precall(self, lego: Lego) -> bool:
        # lego in precalls should be preserved and not be mutated or puzzled
        return self.lego_index(lego) < self.syscalls_start

    def syscall_index(self, syscall: Syscall) -> Tuple[int, int]:
        i = self.thread_dist[syscall]
        return i, self.thread_subs[i].index(syscall)

    # precalls
    def bootstrap(self, preload: List[Syscall]) -> None:
        for syscall in preload:
            # put in global sequence
            self.syscalls.append(syscall)
            self.syscalls_start += 1

            # engage
            syscall.engage(self)

            # put in local sequence
            self.thread_main.append(syscall)
            self.thread_dist[syscall] = -1

    # syscalls
    def add_syscall(self, syscall: Syscall, tid: Optional[int] = None) -> None:
        # find the location and insert syscall
        pos = SPEC_RANDOM.randint(self.syscalls_start, len(self.syscalls))
        self.syscalls.insert(pos, syscall)

        # prepare the syscall
        syscall.engage(self)

        # update the subsequent syscalls
        for i in range(pos, len(self.syscalls)):
            self.syscalls[i].update(self)

        # add syscall in local sequence
        thread = SPEC_RANDOM.choice(self.thread_subs) if tid is None else \
            self.thread_subs[tid]

        before = 0
        i = pos - 1
        while i >= 0:
            if self.thread_dist[self.syscalls[i]] == thread:
                before = thread.index(self.syscalls[i]) + 1
                break
            i -= 1

        thread.insert(before, syscall)
        self.thread_dist[syscall] = self.thread_subs.index(thread)

    def mod_syscall(self, victim: Optional[int]) -> None:
        # find the syscall to modify
        pos = victim if victim is not None else \
            SPEC_RANDOM.randrange(self.syscalls_start, len(self.syscalls))
        syscall = self.syscalls[pos]

        if SPEC_RANDOM.random() < 0.8:
            syscall.mutate(self)
        else:
            syscall.puzzle(self)

        # update the subsequent syscalls
        for i in range(pos, len(self.syscalls)):
            self.syscalls[i].update(self)

    def del_syscall(self, victim: Optional[int]) -> None:
        # find the syscall to modify
        pos = victim if victim is not None else \
            SPEC_RANDOM.randrange(self.syscalls_start, len(self.syscalls))
        syscall = self.syscalls[pos]

        # delete the syscall
        syscall.remove(self)
        del self.syscalls[pos]

        # update the subsequent syscalls
        for i in range(pos, len(self.syscalls)):
            self.syscalls[i].update(self)

        # del syscall in local sequence
        thread = self.thread_subs[self.thread_dist[syscall]]
        thread.remove(syscall)
        del self.thread_dist[syscall]

    def num_syscall(self) -> int:
        return len(self.syscalls) - self.syscalls_start

    def mod_all_syscalls(self) -> None:
        for pos, syscall in enumerate(self.syscalls):
            # do not mutate precalls
            if pos < self.syscalls_start:
                continue

            # decide mutate or puzzle
            if SPEC_RANDOM.random() < 0.8:
                syscall.mutate(self)
            else:
                syscall.puzzle(self)

            # update the subsequent syscalls
            for i in range(pos, len(self.syscalls)):
                self.syscalls[i].update(self)

    # combination of programs
    def merge(self, prog: 'Program') -> None:
        ctxt = {}  # type: Dict[Bean, Bean]

        # NOTE: after merging, the syscalls will be interleaved but their
        # relative orders are preserved

        # fist link the precalls
        for s1, s2 in zip(
                self.syscalls[:self.syscalls_start],
                prog.syscalls[:prog.syscalls_start]
        ):
            s2.unite(s1, ctxt)

        # next migrate the syscalls
        hist = set()  # type: Set[Lego]
        prev = self.syscalls_start
        for other in prog.syscalls[prog.syscalls_start:]:
            # clone the syscall structure
            syscall = other.clone(ctxt)

            # integrity linkage and checks
            syscall.link()
            syscall.check()

            # find the location and insert syscall
            pos = SPEC_RANDOM.randint(prev, len(self.syscalls))
            self.syscalls.insert(pos, syscall)

            # engage the syscall
            syscall.engage(self)

            # transfer the rand objects over
            syscall.migrate(other, ctxt, hist)

            # update the subsequent syscalls
            for i in range(pos, len(self.syscalls)):
                self.syscalls[i].update(self)

            # add syscall to local sequence
            thread = self.thread_subs[prog.thread_dist[other]]

            before = 0
            i = pos - 1
            while i >= 0:
                if self.thread_dist[self.syscalls[i]] == thread:
                    before = thread.index(self.syscalls[i]) + 1
                    break
                i -= 1

            thread.insert(before, syscall)
            self.thread_dist[syscall] = self.thread_subs.index(thread)

            # the next syscall must be added after this one
            prev = pos + 1

    # show
    def gen_readable(self) -> str:
        code = ['[MAIN]']
        code.extend([syscall.show() for syscall in self.thread_main])

        for i, thread in enumerate(self.thread_subs):
            code.append('[SUB{}]'.format(i))
            code.extend([syscall.show() for syscall in thread])

        return '\n'.join(code)

    # blob
    def _pack_thread(
            self, inst: 'Executable', syscalls: List[Syscall]
    ) -> bytearray:
        code = bytearray(pack_ptr(len(syscalls)))

        for syscall in syscalls:
            prep_list = inst.prep.get(syscall, [])

            # syscall prep
            code += pack_ptr(len(prep_list))
            for prep_item in prep_list:
                code += pack_ptr(prep_item[0].addr)
                code += pack_ptr(prep_item[0].size)
                code += pack_ptr(prep_item[1].addr)
                code += pack_ptr(prep_item[1].size)

            # syscall id
            code += pack_ptr(syscall.snum)

            # syscall retv
            hole = inst.get_hole(syscall.retv.lego)
            code += pack_ptr(hole.addr)
            code += pack_ptr(hole.size)

            # syscall args
            code += pack_ptr(len(syscall.args))
            for arg in syscall.args:
                hole = inst.get_hole(arg.lego)
                code += pack_ptr(hole.addr)
                code += pack_ptr(hole.size)

        return code

    def gen_bytecode(self) -> Tuple['Executable', bytearray]:
        # NOTE: general executable layout:
        #   - head
        #       - (8) magic string (bytecode)
        #       - (8) meta offset
        #       - (8) code offset
        #       - (8) heap offset
        #   - meta
        #       - (8) number of pointers
        #       - (*) offset to heap of each pointer
        #       - (8) number of fds
        #       - (*) per each fd
        #           - (8) fd addr
        #           - (8) fd size
        #   - code
        #       - (8) number of threads
        #       - (8) offset to main thread
        #       - (*) offset to each of the sub threads
        #       - (*) per each thread (main and subs)
        #           - (8) number of syscalls
        #           - (*) per syscall
        #               - (8) number of prep entries
        #               - (*) per prep entry
        #                   - (8) src addr
        #                   - (8) src size
        #                   - (8) dst addr
        #                   - (8) dst size
        #               - (8) syscall id
        #               - (8) retv addr
        #               - (8) retv size
        #               - (8) number of syscall args
        #               - (*) per each arg
        #                   - (8) arg addr
        #                   - (8) arg size
        #   - heap

        # build component: heap
        inst = Executable()

        for syscall in self.syscalls:
            syscall.blob(inst)

        inst.check()
        region_heap = inst.heap

        # build component: meta
        region_meta = bytearray(pack_ptr(len(inst.ptrs)))

        # save all ptr locations so we could adjust it with actual value
        for ptr in sorted(inst.ptrs, key=lambda h: h.addr):
            region_meta += pack_ptr(ptr.addr)

        # save all fd used so we could close all of them at the end
        all_fd = {}  # type: Dict[int, int]
        for fd in inst.fds:
            if fd.addr in all_fd:
                assert all_fd[fd.addr] == fd.size
            else:
                all_fd[fd.addr] = fd.size

        region_meta += pack_ptr(len(all_fd))
        for fd_addr in sorted(all_fd.keys()):
            region_meta += pack_ptr(fd_addr)
            region_meta += pack_ptr(all_fd[fd_addr])

        # build component: code
        region_code = bytearray(pack_ptr(self.ncpu))

        # pre-build the bytecode for main and subs
        thread_main = self._pack_thread(
            inst, self.syscalls[:self.syscalls_start]
        )
        thread_subs = [
            self._pack_thread(inst, thread) for thread in self.thread_subs
        ]

        # derive cursors
        cursor = (1 + 1 + self.ncpu) * SPEC_PTR_SIZE
        region_code += pack_ptr(cursor)

        cursor += len(thread_main)
        for sub in thread_subs:
            region_code += pack_ptr(cursor)
            cursor += len(sub)

        # add thread bytecode
        region_code += thread_main
        for sub in thread_subs:
            region_code += sub

        # build component: head
        region_head = bytearray('bytecode'.encode('charmap'))

        cursor = 4 * SPEC_PTR_SIZE
        region_head += pack_ptr(cursor)  # meta offset

        cursor += len(region_meta)
        region_head += pack_ptr(cursor)  # code offset

        cursor += len(region_code)
        region_head += pack_ptr(cursor)  # heap offset

        # return combined
        return inst, region_head + region_meta + region_code + region_heap

    # form
    def gen_synopsis(self) -> Synopsis:
        return Synopsis(
            sketch=[
                [syscall.name for syscall in thread]
                for thread in self.thread_subs
            ]
        )

    # epoch
    def add_epoch_mod(self, lego: Lego) -> None:
        self.epoch_changes.add(lego)

    def has_epoch_mod(self, lego: Lego) -> bool:
        return lego in self.epoch_changes

    def clear_epoch(self) -> None:
        self.epoch_changes.clear()

    # repo: path
    def add_path_rand(self, mark: NodeType, lego: Lego) -> None:
        assert lego not in self.repo_path_rand[mark]
        self.repo_path_rand[mark].append(lego)

    def gen_path_rand(self, mark: NodeType, lego: Lego) -> Lego:
        index = self.lego_index(lego)
        return SPEC_RANDOM.choice([
            i for i in self.repo_path_rand[mark]
            if self.lego_index(i) < index
        ])

    def del_path_rand(self, mark: NodeType, lego: Lego) -> None:
        assert lego in self.repo_path_rand[mark]
        self.repo_path_rand[mark].remove(lego)

    # repo: fd
    def add_fd_rand(self, mark: NodeType, lego: Lego) -> None:
        assert lego not in self.repo_fd_rand[mark]
        self.repo_fd_rand[mark].append(lego)

    def gen_fd_rand(self, mark: NodeType, lego: Lego) -> Lego:
        index = self.lego_index(lego)
        return SPEC_RANDOM.choice([
            i for i in self.repo_fd_rand[mark]
            if self.lego_index(i) < index
        ])

    def del_fd_rand(self, mark: NodeType, lego: Lego) -> None:
        assert lego in self.repo_fd_rand[mark]
        self.repo_fd_rand[mark].remove(lego)

    def add_fd_kobj(self, mark: NodeType, lego: Lego) -> None:
        assert lego not in self.repo_fd_kobj[mark]
        self.repo_fd_kobj[mark].append(lego)

    def gen_fd_kobj(self, mark: NodeType, lego: Lego) -> Lego:
        index = self.lego_index(lego)
        return SPEC_RANDOM.choice([
            i for i in self.repo_fd_kobj[mark]
            if self.lego_index(i) < index
        ])

    def del_fd_kobj(self, mark: NodeType, lego: Lego) -> None:
        assert lego in self.repo_fd_kobj[mark]
        self.repo_fd_kobj[mark].remove(lego)

    # inspect execution results
    @staticmethod
    def _extract_retv(hole: 'Hole', blob: bytes) -> int:
        fmt = 'b' if hole.size == 1 \
            else 'h' if hole.size == 2 \
            else 'i' if hole.size == 4 \
            else 'q' if hole.size == 8 \
            else 'X'

        data = blob[hole.addr:hole.addr + hole.size]
        return cast(int, struct.unpack(fmt, data)[0])

    @staticmethod
    def _inspect_thread(
            syscalls: List[Syscall], inst: 'Executable', blob: bytes
    ) -> List[int]:
        return [
            Program._extract_retv(inst.get_hole(syscall.retv.lego), blob)
            for syscall in syscalls
        ]

    def inspect(self, inst: 'Executable', blob: bytes) -> 'Outcome':
        return Outcome(
            Program._inspect_thread(self.thread_main, inst, blob),
            [
                Program._inspect_thread(sub, inst, blob)
                for sub in self.thread_subs
            ]
        )

    def summary(self) -> Tuple[str, str]:
        sketch = self.gen_synopsis().codec()

        _, code = self.gen_bytecode()

        hasher = hashlib.sha1()
        hasher.update(code)
        digest = hasher.hexdigest()

        return sketch, digest


class Hole(object):

    def __init__(self, addr: int, size: int) -> None:
        self.addr = addr
        self.size = size
        self.fill = False

    def covers(self, hole: 'Hole') -> bool:
        return \
            self.addr <= hole.addr and \
            (self.addr + self.size) >= (hole.addr + hole.size)


class Executable(object):
    """
    The synthesized executable.
    """

    def __init__(self) -> None:
        self.repo = {}  # type: Dict[Lego, Hole]
        self.repo_offset = {}  # type: Dict[Lego, int]

        # tracks the offset of each object in data region
        # NOTE: heap starts from an offset instead of 0
        self.heap = bytearray(b'\x00' * SPEC_PROG_HEAP_OFFSET)
        self.heap_offset = SPEC_PROG_HEAP_OFFSET

        # pointers
        self.ptrs = set()  # type: Set[Hole]

        # fds
        self.fds = set()  # type: Set[Hole]

        # preparation before syscalls
        self.prep = {}  # type: Dict[Syscall, List[Tuple[Hole, Hole]]]

    # digging
    def add_hole(self, lego: Lego, size: int, root: Optional[Lego]) -> Hole:
        # one lego is allocated to one hole in heap
        assert lego not in self.repo

        # conservative check
        dec_size = lego.length()
        if dec_size is not None:
            assert dec_size == size

        # allocation or division depending on whether there is a root
        if root is None:
            # allocate
            self.heap.extend(b'\x00' * size)

            hole = Hole(self.heap_offset, size)
            self.heap_offset += size

        else:
            # divide
            base = self.repo[root]
            offs = self.repo_offset[root]
            assert 0 <= offs < offs + size <= base.size

            hole = Hole(base.addr + offs, size)
            offs += size
            self.repo_offset[root] = offs

        self.repo[lego] = hole
        self.repo_offset[lego] = 0

        return hole

    def get_hole(self, lego: Lego) -> Hole:
        return self.repo[lego]

    def has_hole(self, lego: Lego) -> bool:
        return lego in self.repo

    # filling
    def fill_hole(self, hole: Hole, data: bytes) -> None:
        stop = hole.addr + hole.size

        if hole.fill:
            # conservative check
            assert self.heap[hole.addr:stop] == data

        else:
            # conservative check
            assert len(data) == hole.size
            assert 0 <= hole.addr <= stop <= self.heap_offset

            self.heap[hole.addr:stop] = data
            hole.fill = True

            # also mark the sub-holes as filled
            for item in self.repo.values():
                if hole.covers(item):
                    item.fill = True

    # check
    def check(self) -> None:
        # make sure we do not overflow
        assert len(self.heap) == self.heap_offset

        # make sure that all assigned holes are properly filled
        for hole in self.repo.values():
            assert hole.fill

    # adjustment: ptr
    def add_ptr(self, ptr: Hole) -> None:
        self.ptrs.add(ptr)

    # adjustment: fd
    def add_fd(self, fd: Hole) -> None:
        self.fds.add(fd)

    # adjustment: prep
    def add_prep(self, syscall: Syscall, src: Hole, dst: Hole) -> None:
        if syscall not in self.prep:
            self.prep[syscall] = []

        self.prep[syscall].append((src, dst))


@dataclass
class Outcome(object):
    main: List[int]
    subs: List[List[int]]

    def json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    @classmethod
    def load(cls, path: str) -> 'Outcome':
        with open(path, 'r') as f:
            data = json.load(f)
            return Outcome(
                main=data['main'],
                subs=data['subs'],
            )
