from typing import cast, Dict, Set, Optional

import spec_const

from spec_random import SPEC_RANDOM
from spec_basis import Rand, Kobj, KindSend, KindRecv, Lego, Syscall, Program, \
    Executable, NodeType
from spec_pack import pack_int
from util_bean import Bean, BeanRef


class RandFd(Rand):
    val: int


class KobjFd(Kobj):
    pass


class KindSendFd(KindSend[RandFd]):
    bits: int
    mark: NodeType
    val_const: Optional[int]

    def __init__(self) -> None:
        super().__init__()
        self.int_min = 0
        self.int_max = 0

    # defaults
    def default_bits(self) -> int:
        return 32

    def default_val_const(self) -> Optional[int]:
        return None

    # bean
    def validate(self) -> None:
        assert self.bits in {8, 16, 32, 64}
        self.int_min = spec_const.SPEC_FD_LIMIT_MIN
        self.int_max = spec_const.SPEC_FD_LIMIT_MAX

    # debug
    def note(self) -> str:
        return self.mark.name

    # chain
    def link(self, ctxt: Syscall) -> None:
        pass

    # memory
    def length(self) -> Optional[int]:
        return self.bits // 8

    # builder
    def mk_rand(self) -> RandFd:
        return RandFd()

    # utils
    def sanitize(self, data: int) -> int:
        if data < self.int_min:
            return self.int_min
        if data > self.int_max:
            return self.int_max
        return data

    # operations: engage and remove
    def engage_rand(self, rand: RandFd, prog: Program) -> None:
        # prep
        prog.add_fd_rand(self.mark, self.lego.bean)

        # init
        rand.val = self.toss()

    def remove_rand(self, rand: RandFd, prog: Program) -> None:
        # un-prep
        prog.del_fd_rand(self.mark, self.lego.bean)

    # operations: mutate and puzzle
    def mutate_rand(self, rand: RandFd, prog: Program) -> None:
        rand.val = self.toss()

    def puzzle_rand(self, rand: RandFd, prog: Program) -> None:
        rand.val = self.drag(rand.val)

    # operations: update
    def update_rand(self, rand: RandFd, prog: Program) -> None:
        pass

    # operations: migrate
    def migrate_rand(
            self,
            rand: RandFd, orig: RandFd,
            ctxt: Dict[Bean, Bean], hist: Set[Lego]
    ) -> None:
        rand.val = orig.val

    # show
    def expo_rand(self, rand: RandFd) -> str:
        return str(rand.val)

    # blob
    def blob_size_rand(self, rand: RandFd) -> int:
        return cast(int, self.length())

    def blob_hole_rand(self, rand: RandFd, inst: Executable) -> None:
        inst.add_fd(inst.get_hole(self.lego.bean))

    def blob_data_rand(self, rand: RandFd, inst: Executable) -> bytes:
        return pack_int(rand.val, self.bits)

    def blob_fill_rand(self, rand: RandFd, inst: Executable) -> None:
        pass

    # relationship
    def rely_on_rand(self, rand: RandFd, prog: Program) -> Set[int]:
        return set()

    # utils
    def toss(self) -> int:
        if self.val_const is None:
            return SPEC_RANDOM.randint(self.int_min, self.int_max)
        else:
            return self.val_const

    def drag(self, data: int) -> int:
        p = SPEC_RANDOM.random()

        if p < 0.25:
            # [DRAG] choose from an extreme value
            retv = SPEC_RANDOM.choice([
                spec_const.SPEC_FD_LIMIT_MIN,
                spec_const.SPEC_FD_LIMIT_MAX,
            ])

        elif p < 0.75:
            # [DRAG] inc/dec based on the existing value
            step = abs(data // 10)
            retv = data + SPEC_RANDOM.choice([
                1, step,
                -1, -step,
                data
            ])

        else:
            # [DRAG] choose a random number within the fd range
            retv = SPEC_RANDOM.randint(
                spec_const.SPEC_FD_LIMIT_MIN, spec_const.SPEC_FD_LIMIT_MAX
            )

        return self.sanitize(retv)


class KindRecvFd(KindRecv[KobjFd]):
    bits: int
    mark: NodeType

    # defaults
    def default_bits(self) -> int:
        return 32

    # bean
    def validate(self) -> None:
        assert self.bits in {8, 16, 32, 64}

    # debug
    def note(self) -> str:
        return self.mark.name

    # chain
    def link(self, ctxt: Syscall) -> None:
        pass

    # memory
    def length(self) -> Optional[int]:
        return self.bits // 8

    # builder
    def mk_kobj(self) -> KobjFd:
        return KobjFd()

    # operations: engage and remove
    def engage_kobj(self, kobj: KobjFd, prog: Program) -> None:
        # prep
        prog.add_fd_kobj(self.mark, self.lego.bean)

    def remove_kobj(self, kobj: KobjFd, prog: Program) -> None:
        # un-prep
        prog.del_fd_kobj(self.mark, self.lego.bean)

    # show
    def expo_kobj(self, kobj: KobjFd) -> str:
        return str('-X-')

    # blob
    def blob_size_kobj(self, kobj: KobjFd) -> int:
        return cast(int, self.length())

    def blob_hole_kobj(self, kobj: KobjFd, inst: Executable) -> None:
        inst.add_fd(inst.get_hole(self.lego.bean))

    def blob_data_kobj(self, kobj: KobjFd, inst: Executable) -> bytes:
        return pack_int(0, self.bits)

    def blob_fill_kobj(self, kobj: KobjFd, inst: Executable) -> None:
        pass

    # relationship
    def rely_on_kobj(self, kobj: KobjFd, prog: Program) -> Set[int]:
        return set()


class RandFdExt(Rand):
    pick: BeanRef[Lego]


class KobjFdExt(Kobj):
    pass


class KindSendFdExt(KindSend[RandFdExt]):
    bits: int
    mark: NodeType

    # defaults
    def default_bits(self) -> int:
        return 32

    # bean
    def validate(self) -> None:
        assert self.bits in {8, 16, 32, 64}

    # debug
    def note(self) -> str:
        return self.mark.name

    # chain
    def link(self, ctxt: Syscall) -> None:
        pass

    # memory
    def length(self) -> Optional[int]:
        return self.bits // 8

    # builder
    def mk_rand(self) -> RandFdExt:
        return RandFdExt()

    # operations: engage and remove
    def engage_rand(self, rand: RandFdExt, prog: Program) -> None:
        # init
        rand.pick = BeanRef[Lego](
            prog.gen_fd_rand(self.mark, self.lego.bean)
        )

    def remove_rand(self, rand: RandFdExt, prog: Program) -> None:
        pass

    # operations: mutate and puzzle
    def mutate_rand(self, rand: RandFdExt, prog: Program) -> None:
        p = SPEC_RANDOM.random()

        if p < 0.5 and not prog.lego_in_precall(rand.pick.bean):
            # [TOSS] mutate the underlying fd
            rand.pick.bean.mutate_rand(prog)

        else:
            # [TOSS] choose another fd
            rand.pick = BeanRef[Lego](
                prog.gen_fd_rand(self.mark, self.lego.bean)
            )

    def puzzle_rand(self, rand: RandFdExt, prog: Program) -> None:
        p = SPEC_RANDOM.random()

        if p < 0.5 and not prog.lego_in_precall(rand.pick.bean):
            # [DRAG] puzzle the underlying fd
            rand.pick.bean.puzzle_rand(prog)

        else:
            # [DRAG] choose another fd not in the same type
            alts = [i for i in NodeType if i != self.mark]
            mark = SPEC_RANDOM.choice(alts)
            rand.pick = BeanRef[Lego](
                prog.gen_fd_rand(mark, self.lego.bean)
            )

    # operations: update
    def update_rand(self, rand: RandFdExt, prog: Program) -> None:
        if rand.pick.bean.rand is not None:
            return

        # only update when pick does not exist anymore
        rand.pick = BeanRef[Lego](
            prog.gen_fd_rand(self.mark, self.lego.bean)
        )

    # operations: migrate
    def migrate_rand(
            self,
            rand: RandFdExt, orig: RandFdExt,
            ctxt: Dict[Bean, Bean], hist: Set[Lego]
    ) -> None:
        rand.pick.bean = cast(Lego, ctxt[orig.pick.bean])

    # show
    def expo_rand(self, rand: RandFdExt) -> str:
        pick = cast(RandFd, rand.pick.bean.rand)
        return str(pick.val)

    # blob
    def blob_size_rand(self, rand: RandFdExt) -> int:
        return cast(int, self.length())

    def blob_hole_rand(self, rand: RandFdExt, inst: Executable) -> None:
        # although we depends on an existing RandFd, we do not require
        # it to be on the heap (although it will be on heap in most cases)
        inst.add_fd(inst.get_hole(self.lego.bean))

    def blob_data_rand(self, rand: RandFdExt, inst: Executable) -> bytes:
        pick = cast(RandFd, rand.pick.bean.rand)
        return pack_int(pick.val, self.bits)

    def blob_fill_rand(self, rand: RandFdExt, inst: Executable) -> None:
        # similar to the logic of blob_hole_rand(), since we do not need
        # the picked lego to be on heap, we can simply pass here
        pass

    # relationship
    def rely_on_rand(self, rand: RandFdExt, prog: Program) -> Set[int]:
        return {prog.lego_index(rand.pick.bean)}


class RandFdRes(Rand):
    pick: BeanRef[Lego]


class KobjFdRes(Kobj):
    pass


class KindSendFdRes(KindSend[RandFdRes]):
    bits: int
    mark: NodeType

    # defaults
    def default_bits(self) -> int:
        return 32

    # bean
    def validate(self) -> None:
        assert self.bits in {8, 16, 32, 64}

    # debug
    def note(self) -> str:
        return self.mark.name

    # chain
    def link(self, ctxt: Syscall) -> None:
        pass

    # memory
    def length(self) -> Optional[int]:
        return self.bits // 8

    # builder
    def mk_rand(self) -> RandFdRes:
        return RandFdRes()

    # operations: engage and remove
    def engage_rand(self, rand: RandFdRes, prog: Program) -> None:
        # init
        rand.pick = BeanRef[Lego](
            prog.gen_fd_kobj(self.mark, self.lego.bean)
        )

    def remove_rand(self, rand: RandFdRes, prog: Program) -> None:
        pass

    # operations: mutate and puzzle
    def mutate_rand(self, rand: RandFdRes, prog: Program) -> None:
        # [TOSS] choose another fd
        rand.pick = BeanRef[Lego](
            prog.gen_fd_kobj(self.mark, self.lego.bean)
        )

    def puzzle_rand(self, rand: RandFdRes, prog: Program) -> None:
        # [DRAG] choose another fd not in the same type
        alts = [i for i in NodeType if i != self.mark]
        mark = SPEC_RANDOM.choice(alts)
        rand.pick = BeanRef[Lego](
            prog.gen_fd_kobj(mark, self.lego.bean)
        )

    # operations: update
    def update_rand(self, rand: RandFdRes, prog: Program) -> None:
        if rand.pick.bean.kobj is not None:
            return

        # only update when pick does not exist anymore
        rand.pick = BeanRef[Lego](
            prog.gen_fd_kobj(self.mark, self.lego.bean)
        )

    # operations: migrate
    def migrate_rand(
            self,
            rand: RandFdRes, orig: RandFdRes,
            ctxt: Dict[Bean, Bean], hist: Set[Lego]
    ) -> None:
        rand.pick.bean = cast(Lego, ctxt[orig.pick.bean])

    # show
    def expo_rand(self, rand: RandFdRes) -> str:
        return '|RES: {}|'.format(
            cast(BeanRef[Syscall], rand.pick.bean.ctxt).bean.name
        )

    # blob
    def blob_size_rand(self, rand: RandFdRes) -> int:
        return cast(int, self.length())

    def blob_hole_rand(self, rand: RandFdRes, inst: Executable) -> None:
        # the picked kobj has to have a hole (so that we can do the prep step
        # in which the content is copied over from the picked kobj hole
        rand.pick.bean.blob_hole(None, inst)

    def blob_data_rand(self, rand: RandFdRes, inst: Executable) -> bytes:
        inst.add_prep(
            cast(BeanRef[Syscall], self.lego.bean.ctxt).bean,
            inst.get_hole(rand.pick.bean),
            inst.get_hole(self.lego.bean),
        )

        return pack_int(0, self.bits)

    def blob_fill_rand(self, rand: RandFdRes, inst: Executable) -> None:
        # similar to the blob_hole_rand(), we need the picked blob to exist
        rand.pick.bean.blob_fill(inst)

    # relationship
    def rely_on_rand(self, rand: RandFdRes, prog: Program) -> Set[int]:
        lego = rand.pick.bean
        deps = lego.rely_on(prog)
        deps.add(prog.lego_index(lego))
        return deps
