from typing import cast, List, Dict, Set, Optional

from abc import ABC, abstractmethod
from enum import Enum

from spec_random import SPEC_RANDOM
from spec_basis import Rand, Kobj, KindSend, KindRecv, Lego, Syscall, Program, \
    Executable
from spec_pack import pack_int
from util_bean import Bean


class RandInt(Rand):
    data: int


class KobjInt(Kobj):
    pass


class KindSendInt(KindSend[RandInt], ABC):
    bits: int
    signed: bool

    def __init__(self) -> None:
        super().__init__()
        self.int_min = 0
        self.int_max = 0

    # bean
    def validate(self) -> None:
        assert self.bits in {8, 16, 32, 64}
        self.int_min = -(2 ** (self.bits - 1)) if self.signed else 0
        self.int_max = (2 ** (self.bits - (1 if self.signed else 0))) - 1

    # chain
    def link(self, ctxt: Syscall) -> None:
        pass

    # memory
    def length(self) -> Optional[int]:
        return self.bits // 8

    # builder
    def mk_rand(self) -> RandInt:
        return RandInt()

    # utils
    def sanitize(self, data: int) -> int:
        if data < self.int_min:
            return self.int_min
        if data > self.int_max:
            return self.int_max
        return data

    @abstractmethod
    def toss(self) -> int:
        raise RuntimeError('Method not implemented')

    def drag(self, data: int) -> int:
        p = SPEC_RANDOM.random()

        if p < 0.45:
            # [DRAG] inc/dec based on the existing value
            step = abs(data // 10)
            retv = data + SPEC_RANDOM.choice([
                1, step, data,
                -1, -step, -2 * data,
            ])

        elif p < 0.9:
            # [DRAG] choose from an extreme value (integer range-wise)
            retv = SPEC_RANDOM.choice([
                0,
                1, 4096,
                -1, -4096,
                self.int_min, self.int_min + 1, self.int_min + 4096,
                self.int_max, self.int_max - 1, self.int_max - 4096,
            ])

        else:
            # [DRAG] choose a random number within the integer range
            retv = SPEC_RANDOM.randint(self.int_min, self.int_max)

        # sanitize
        return self.sanitize(retv)

    # operations: engage and remove
    def engage_rand(self, rand: RandInt, prog: Program) -> None:
        # init
        rand.data = self.toss()

    def remove_rand(self, rand: RandInt, prog: Program) -> None:
        pass

    # operations: mutate and puzzle
    def mutate_rand(self, rand: RandInt, prog: Program) -> None:
        rand.data = self.toss()

    def puzzle_rand(self, rand: RandInt, prog: Program) -> None:
        rand.data = self.drag(rand.data)

    # operations: update
    def update_rand(self, rand: RandInt, prog: Program) -> None:
        pass

    # operations: migrate
    def migrate_rand(
            self,
            rand: RandInt, orig: RandInt,
            ctxt: Dict[Bean, Bean], hist: Set[Lego]
    ) -> None:
        rand.data = orig.data

    # show
    def expo_rand(self, rand: RandInt) -> str:
        return str(rand.data)

    # blob
    def blob_size_rand(self, rand: RandInt) -> int:
        return cast(int, self.length())

    def blob_hole_rand(self, rand: RandInt, inst: Executable) -> None:
        pass

    def blob_data_rand(self, rand: RandInt, inst: Executable) -> bytes:
        return pack_int(rand.data, self.bits, self.signed)

    def blob_fill_rand(self, rand: RandInt, inst: Executable) -> None:
        pass

    # relationship
    def rely_on_rand(self, rand: RandInt, prog: Program) -> Set[int]:
        return set()


class KindSendIntConst(KindSendInt):
    val_const: int

    # bean
    def validate(self) -> None:
        assert self.int_min <= self.val_const <= self.int_max

    # debug
    def note(self) -> str:
        return str(self.val_const)

    # utils
    def toss(self) -> int:
        return self.val_const

    def drag(self, data: int) -> int:
        p = SPEC_RANDOM.random()

        if p < 0.5:
            # [DRAG] inc/dec based on the given constant value
            step = abs(self.val_const // 10)
            retv = SPEC_RANDOM.choice([
                self.val_const + 1, self.val_const + step, self.val_const,
                self.val_const - 1, self.val_const - step, -2 * self.val_const,
            ])
            return self.sanitize(retv)

        else:
            # [DRAG] use parent strategy
            return super().drag(data)


class IntFlagOperation(Enum):
    AND = '&'
    OR = '|'
    XOR = '^'


class KindSendIntFlag(KindSendInt):
    name: str
    vals: Set[int]
    elem_min: int
    elem_max: int
    use_ops: List[IntFlagOperation]
    use_neg: bool

    def __init__(self) -> None:
        super().__init__()
        self.elem_set = []  # type: List[int]

    # defaults
    def default_elem_min(self) -> int:
        return 0

    def default_elem_max(self) -> int:
        return len(self.vals)

    def default_use_ops(self) -> List[IntFlagOperation]:
        return [IntFlagOperation.OR]

    def default_use_neg(self) -> bool:
        return False

    # bean
    def validate(self) -> None:
        elem_set = set(self.vals)
        if self.use_neg:
            elem_set.update({(~i) for i in self.vals})

        assert self.elem_min <= self.elem_max <= len(elem_set)
        self.elem_set.extend(sorted(elem_set))

    # debug
    def note(self) -> str:
        return self.name

    # utils
    def toss(self) -> int:
        num = SPEC_RANDOM.randint(self.elem_min, self.elem_max)
        if num == 0:
            return 0

        vas = SPEC_RANDOM.sample(self.elem_set, num)
        ops = [SPEC_RANDOM.choice(self.use_ops) for _ in range(num - 1)]

        res = vas[0]
        for i in range(1, num):
            if ops[i - 1] == IntFlagOperation.OR:
                res = res | vas[i]
            elif ops[i - 1] == IntFlagOperation.AND:
                res = res & vas[i]
            elif ops[i - 1] == IntFlagOperation.XOR:
                res = res ^ vas[i]
            else:
                raise RuntimeError('Invalid flag operation')

        return res

    def drag(self, data: int) -> int:
        p = SPEC_RANDOM.random()

        if p < 0.1:
            # [DRAG] use 0
            return 0

        elif p < 0.5:
            # [DRAG] use | with all flags
            res = 0
            for i in self.elem_set:
                res = res | i
            return res

        else:
            # [DRAG] use parent strategy
            return super().drag(data)


class KindSendIntRange(KindSendInt):
    val_min: int
    val_max: int

    # defaults
    def default_val_min(self) -> int:
        return cast(int, -(2 ** (self.bits - 1)) if self.signed else 0)

    def default_val_max(self) -> int:
        return cast(int, (2 ** (self.bits - (1 if self.signed else 0))) - 1)

    # bean
    def validate(self) -> None:
        assert self.int_min <= self.val_min <= self.val_max <= self.int_max

    # debug
    def note(self) -> str:
        min_repr = 'MIN' if self.val_min == self.int_min else str(self.val_min)
        max_repr = 'MAX' if self.val_max == self.int_max else str(self.val_max)
        return min_repr + '-' + max_repr

    # utils
    def toss(self) -> int:
        return SPEC_RANDOM.randint(self.val_min, self.val_max)

    def drag(self, data: int) -> int:
        p = SPEC_RANDOM.random()

        if p < 0.5:
            # [DRAG] choose from an extreme value (given range-wise)
            val_mid = (self.val_min + self.val_max) // 2
            step_min = abs(self.val_min // 10)
            step_max = abs(self.val_max // 10)
            retv = SPEC_RANDOM.choice([
                self.val_min, self.val_max, val_mid,
                self.val_min - 1, self.val_min - step_min,
                self.val_max - 1, self.val_max - step_max,
                self.val_min + 1, self.val_min + step_min,
                self.val_max + 1, self.val_max + step_max,
            ])
            return self.sanitize(retv)

        else:
            # [DRAG] use parent strategy
            return super().drag(data)


class KindRecvInt(KindRecv[KobjInt], ABC):
    bits: int
    signed: bool

    # bean
    def validate(self) -> None:
        assert self.bits in {8, 16, 32, 64}

    # memory
    def length(self) -> Optional[int]:
        return self.bits // 8

    # builder
    def mk_kobj(self) -> KobjInt:
        return KobjInt()

    # operations: engage and remove
    def engage_kobj(self, kobj: KobjInt, prog: Program) -> None:
        pass

    def remove_kobj(self, kobj: KobjInt, prog: Program) -> None:
        pass

    # show
    def expo_kobj(self, kobj: KobjInt) -> str:
        return str('-X-')

    # blob
    def blob_size_kobj(self, kobj: KobjInt) -> int:
        return cast(int, self.length())

    def blob_hole_kobj(self, kobj: KobjInt, inst: Executable) -> None:
        pass

    def blob_data_kobj(self, kobj: KobjInt, inst: Executable) -> bytes:
        return pack_int(0, self.bits, self.signed)

    def blob_fill_kobj(self, kobj: KobjInt, inst: Executable) -> None:
        pass

    # relationship
    def rely_on_kobj(self, kobj: KobjInt, prog: Program) -> Set[int]:
        return set()


class KindRecvIntData(KindRecvInt):

    # debug
    def note(self) -> str:
        return ''

    # chain
    def link(self, ctxt: Syscall) -> None:
        pass
