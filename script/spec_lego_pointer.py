from typing import cast, Dict, Set, Optional

from spec_const import SPEC_PTR_SIZE
from spec_random import SPEC_RANDOM
from spec_basis import Rand, Kobj, Lego, Syscall, Program, Executable
from spec_pack import pack_ptr
from util_bean import Bean, BeanRef


class RandPointer(Rand):
    pick: bool


class KobjPointer(Kobj):
    pass


class LegoPointer(Lego[RandPointer, KobjPointer]):
    memv: Optional[BeanRef[Lego]]
    null: bool

    # defaults
    def default_null(self) -> bool:
        return True

    # bean
    def validate(self) -> None:
        if self.memv is None:
            assert self.null

    # debug
    def note(self) -> str:
        return 'None' if self.memv is None else \
            (self.memv.bean.dump() + '?' if self.null else '')

    # chain
    def link_impl(self, ctxt: Syscall) -> None:
        if self.memv is not None:
            # use None as root, as we may not know which is the actual root
            # of the pointed object, nor whether the root has been set or not.
            # Therefore, use None to allow any root, set, or unset
            self.memv.bean.link(None, ctxt)

    # memory
    def length(self) -> Optional[int]:
        return SPEC_PTR_SIZE

    # input/output
    def has_info_send(self) -> bool:
        # a null pointer means info sent to kernel
        if self.memv is None:
            return True

        # if the pointer refs to some heap object, the pointer has info to send
        return self.memv.bean.has_info_send()

    def has_info_recv(self) -> bool:
        # a null pointer cannot receive information
        if self.memv is None:
            return False

        # if this pointer does not refs heap, the pointer must have info recv-ed
        return not self.memv.bean.has_info_send()

    # builders
    def _mk_rand_impl(self) -> RandPointer:
        return RandPointer()

    def _mk_kobj_impl(self) -> KobjPointer:
        return KobjPointer()

    # operations: engage
    def engage_rand_impl(self, prog: Program) -> None:
        # prep
        if self.memv is not None:
            self.memv.bean.engage(prog)
            self.memv.bean.add_rdep_rand(self)

        # init
        if self.memv is None:
            cast(RandPointer, self.rand).pick = False
        elif not self.null:
            cast(RandPointer, self.rand).pick = True
        else:
            cast(RandPointer, self.rand).pick = (SPEC_RANDOM.random() < 0.95)

    def engage_kobj_impl(self, prog: Program) -> None:
        # prep
        assert self.memv is not None
        self.memv.bean.engage(prog)
        self.memv.bean.add_rdep_kobj(self)

    # operations: remove
    def remove_rand_impl(self, prog: Program) -> None:
        # un-prep
        if self.memv is not None:
            self.memv.bean.del_rdep_rand(self)
            self.memv.bean.remove(prog)

    def remove_kobj_impl(self, prog: Program) -> None:
        # un-prep
        assert self.memv is not None
        self.memv.bean.del_rdep_kobj(self)
        self.memv.bean.remove(prog)

    # operations: mutate and puzzle
    def mutate_rand_impl(self, prog: Program) -> None:
        rand = cast(RandPointer, self.rand)

        if self.memv is None:
            return
        elif not self.null:
            return
        elif not rand.pick:
            rand.pick = True
        else:
            p = SPEC_RANDOM.random()
            if p < 0.95:
                # [TOSS] change the underlying object
                self.memv.bean.mutate_rand(prog)
            else:
                # [TOSS] change to null
                rand.pick = False

    def puzzle_rand_impl(self, prog: Program) -> None:
        rand = cast(RandPointer, self.rand)

        if self.memv is None:
            return
        elif not rand.pick:
            rand.pick = True
        else:
            p = SPEC_RANDOM.random()
            if p < 0.95:
                # [DRAG] change the underlying object
                self.memv.bean.puzzle_rand(prog)
            else:
                # [DRAG] change to null
                rand.pick = False

    # operations: update
    def update_rand_impl(self, prog: Program) -> None:
        if self.memv is not None:
            self.memv.bean.update_rand(prog)

    # operations: migrate
    def migrate_impl(
            self, other: Lego, ctxt: Dict[Bean, Bean], hist: Set[Lego]
    ) -> None:
        lego = cast(LegoPointer, other)
        if self.memv is not None:
            self.memv.bean.migrate(
                cast(BeanRef[Lego], lego.memv).bean, ctxt, hist
            )

        if self.has_info_send():
            # will have the same pick chosen
            rand = cast(RandPointer, self.rand)
            rand.pick = cast(RandPointer, lego.rand).pick

    # show
    def expo(self) -> str:
        rand = cast(RandPointer, self.rand)

        if not rand.pick:
            return '<null>'
        else:
            return '/* {} */'.format(cast(BeanRef[Lego], self.memv).bean.show())

    # blob
    def blob_size(self) -> int:
        return SPEC_PTR_SIZE

    def blob_hole_impl(self, inst: Executable) -> None:
        if self.memv is not None:
            self.memv.bean.blob_hole(None, inst)

        # mark that whatever stored in the hole here is an offset
        # and needs to be adjusted
        inst.add_ptr(inst.get_hole(self))

    def blob_data(self, inst: Executable) -> bytes:
        rand = cast(RandPointer, self.rand)

        if not rand.pick:
            addr = 0
        else:
            addr = inst.get_hole(cast(BeanRef[Lego], self.memv).bean).addr

        return pack_ptr(addr)

    def blob_fill_impl(self, inst: Executable) -> None:
        if self.memv is not None:
            self.memv.bean.blob_fill(inst)

    # relationship
    def rely_on(self, prog: Program) -> Set[int]:
        if self.memv is None:
            return set()

        return self.memv.bean.rely_on(prog)
