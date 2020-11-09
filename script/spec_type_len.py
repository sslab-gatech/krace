from typing import cast, Dict, Set, Optional, Union

from spec_random import SPEC_RANDOM
from spec_basis import Rand, Kobj, KindSend, Lego, Syscall, Program, Executable
from spec_pack import pack_int
from spec_lego_simple import LegoSimple
from spec_lego_pointer import LegoPointer
from spec_lego_vector import RandVector
from spec_type_str import RandStr
from spec_type_buf import RandBuf
from util_bean import Bean, BeanRef


class RandLen(Rand):
    offset: Union[int, float]  # offset to the actual length


class KobjLen(Kobj):
    pass


class KindSendLen(KindSend[RandLen]):
    bits: int
    ptr: BeanRef[LegoPointer]

    # bean
    def validate(self) -> None:
        assert self.bits in {8, 16, 32, 64}

    # debug
    def note(self) -> str:
        return self.ptr.bean.dump()

    # chain
    def link(self, ctxt: Syscall) -> None:
        # use None as the root so we do not associate that lego with anything
        self.ptr.bean.link(None, ctxt)

    # memory
    def length(self) -> Optional[int]:
        return self.bits // 8

    # builder
    def mk_rand(self) -> RandLen:
        return RandLen()

    # operations: engage and remove
    def engage_rand(self, rand: RandLen, prog: Program) -> None:
        # prep
        self.ptr.bean.engage(prog)
        self.ptr.bean.add_rdep_rand(self.lego.bean)

        # init
        rand.offset = 0

    def remove_rand(self, rand: RandLen, prog: Program) -> None:
        # un-prep
        self.ptr.bean.del_rdep_rand(self.lego.bean)
        self.ptr.bean.remove(prog)

    # operations: mutate and puzzle
    def mutate_rand(self, rand: RandLen, prog: Program) -> None:
        # [TOSS] change the underlying pointer
        self.ptr.bean.mutate_rand(prog)

    def puzzle_rand(self, rand: RandLen, prog: Program) -> None:
        p = SPEC_RANDOM.random()

        if p < 0.1:
            # [DRAG] add an offset (absolute) to the length
            rand.offset = SPEC_RANDOM.choice([
                1, 8, 64, 512, 4096
            ])

        elif p < 0.2:
            # [DRAG] add an offset (relative) to the length
            rand.offset = SPEC_RANDOM.choice([
                0.1, 0.5, 0.9, 1.0,
            ])

        else:
            # [DRAG] change the underlying pointer
            self.ptr.bean.puzzle_rand(prog)

    # operations: update
    def update_rand(self, rand: RandLen, prog: Program) -> None:
        assert self.ptr.bean.rand is not None

    # operations: migrate
    def migrate_rand(
            self,
            rand: RandLen, orig: RandLen,
            ctxt: Dict[Bean, Bean], hist: Set['Lego']
    ) -> None:
        # first migrate the ptr
        self.ptr.bean.migrate(
            cast(KindSendLen,
                 cast(LegoSimple, orig.lego.bean).kind_send).ptr.bean,
            ctxt, hist
        )

        # then migrate the rand value
        rand.offset = orig.offset

    # utils
    def _measure(self, rand: RandLen) -> int:
        ptr = self.ptr.bean.rand
        assert ptr is not None

        # get the object size
        if not ptr.pick:
            # null pointer gets size 0
            return 0

        mem = cast(BeanRef[Lego], self.ptr.bean.memv)
        obj = mem.bean.rand

        if isinstance(obj, RandStr):
            size = len(obj.data) + 1
        elif isinstance(obj, RandBuf):
            size = len(obj.data)
        elif isinstance(obj, RandVector):
            size = len(obj.meta)
        else:
            raise RuntimeError('Invalid type for length measurement')

        # adjust for offset (only substraction allowed, stopped at 0)
        if isinstance(rand.offset, int):
            if size >= rand.offset:
                size -= rand.offset
        elif isinstance(rand.offset, float):
            size = int(size * (1 - rand.offset))
        else:
            raise RuntimeError('Invalid type for length offset')

        return size

    # expo
    def expo_rand(self, rand: RandLen) -> str:
        return str(self._measure(rand))

    # blob
    def blob_size_rand(self, rand: RandLen) -> int:
        return cast(int, self.length())

    def blob_hole_rand(self, rand: RandLen, inst: Executable) -> None:
        # although KindSendLen requires a ptr lego, it does not require
        # that the lego to be on heap (although the lego is indeed on
        # heap in almost all cases)
        pass

    def blob_data_rand(self, rand: RandLen, inst: Executable) -> bytes:
        return pack_int(self._measure(rand), self.bits)

    def blob_fill_rand(self, rand: RandLen, inst: Executable) -> None:
        # similar to the logic in blob_hole_rand(), the ptr lego may not
        # necessarily be on heap, therefore, do not call fill on it
        pass

    # relationship
    def rely_on_rand(self, rand: RandLen, prog: Program) -> Set[int]:
        return set()
