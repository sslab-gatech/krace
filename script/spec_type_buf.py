from typing import List, Dict, Set, Optional

from abc import ABC, abstractmethod

from spec_const import SPEC_PAGE_SIZE, SPEC_BYTESET, SPEC_RAND_SIZE_MAX
from spec_random import SPEC_RANDOM
from spec_basis import Rand, Kobj, KindSend, KindRecv, Lego, Syscall, Program, \
    Executable
from util_bean import Bean


class RandBuf(Rand):
    data: bytes


class KobjBuf(Kobj):
    pass


class KindSendBuf(KindSend[RandBuf], ABC):
    fix_size: Optional[int]

    def __init__(self) -> None:
        super().__init__()
        self.int_min = 0
        self.int_max = 0

    # defaults
    def default_fix_size(self) -> Optional[int]:
        return None

    # bean
    def validate(self) -> None:
        assert self.fix_size is None or 0 <= self.fix_size

    # chain
    def link(self, ctxt: Syscall) -> None:
        pass

    # memory
    def length(self) -> Optional[int]:
        return self.fix_size

    # builder
    def mk_rand(self) -> RandBuf:
        return RandBuf()

    # utils
    def sanitize(self, data: bytes) -> bytes:
        if self.fix_size is not None:
            data = data[:self.fix_size]
        return data

    @abstractmethod
    def toss(self) -> bytes:
        raise RuntimeError('Method not implemented')

    def drag(self, data: bytes) -> bytes:
        size = len(data)
        limit = SPEC_PAGE_SIZE + SPEC_RANDOM.randint(-1024, 1024) \
            if self.fix_size is None else self.fix_size

        p = SPEC_RANDOM.random()

        if size == 0:
            # [DRAG] randomly cook up a buffer if currently empty
            retv = b''.join([
                SPEC_RANDOM.choice(SPEC_BYTESET)
                for _ in range(SPEC_RANDOM.randrange(limit))
            ])

        elif p < 0.2:
            # [DRAG] insert NULL at random places
            pivot = SPEC_RANDOM.randrange(size)
            retv = data[:pivot] + b'\x00' + data[pivot + 1:]

        elif p < 0.3:
            # [DRAG] repeat the existing data n times
            retv = data * SPEC_RANDOM.randint(1, 3)

        elif p < 0.45:
            # [DRAG] add a byte randomly
            stuff = SPEC_RANDOM.randrange(size)
            for _ in range(stuff):
                pivot = SPEC_RANDOM.randrange(size)
                abyte = SPEC_RANDOM.choice(SPEC_BYTESET)
                data = data[:pivot] + abyte + data[pivot:]
                size += 1
            retv = data

        elif p < 0.6:
            # [DRAG] del a byte randomly
            strip = SPEC_RANDOM.randrange(size)
            for _ in range(strip):
                pivot = SPEC_RANDOM.randrange(size)
                data = data[:pivot] + data[pivot + 1:]
                size -= 1
            retv = data

        elif p < 0.75:
            # [DRAG] mod a byte randomly
            place = SPEC_RANDOM.randrange(size)
            for _ in range(place):
                pivot = SPEC_RANDOM.randrange(size)
                abyte = SPEC_RANDOM.choice(SPEC_BYTESET)
                data = data[:pivot] + abyte + data[pivot + 1:]
            retv = data

        elif p < 0.9:
            # [DRAG] repeat a special byte up to the limit
            retv = SPEC_RANDOM.choice([
                b'', b'\x00', b'\x00' * SPEC_RANDOM.randrange(limit),
            ])

        else:
            # [DRAG] randomly cook up a byte
            retv = b''.join([
                SPEC_RANDOM.choice(SPEC_BYTESET)
                for _ in range(SPEC_RANDOM.randrange(limit))
            ])

        # sanitize
        return self.sanitize(retv)

    # operations: engage and remove
    def engage_rand(self, rand: RandBuf, prog: Program) -> None:
        # init
        rand.data = self.toss()

    def remove_rand(self, rand: RandBuf, prog: Program) -> None:
        pass

    # operations: mutate and puzzle
    def mutate_rand(self, rand: RandBuf, prog: Program) -> None:
        rand.data = self.toss()

    def puzzle_rand(self, rand: RandBuf, prog: Program) -> None:
        rand.data = self.drag(rand.data)

    # operations: update
    def update_rand(self, rand: RandBuf, prog: Program) -> None:
        pass

    # operations:  migrate
    def migrate_rand(
            self,
            rand: RandBuf, orig: RandBuf,
            ctxt: Dict[Bean, Bean], hist: Set[Lego]
    ) -> None:
        rand.data = orig.data

    # show
    def expo_rand(self, rand: RandBuf) -> str:
        size = len(rand.data)
        return '[{}...buf {} bytes...]'.format(
            rand.data[:4].hex() if size >= 4 else rand.data.hex(), size
        )

    # blob
    def blob_size_rand(self, rand: RandBuf) -> int:
        return len(rand.data)

    def blob_hole_rand(self, rand: RandBuf, inst: Executable) -> None:
        pass

    def blob_data_rand(self, rand: RandBuf, inst: Executable) -> bytes:
        return rand.data

    def blob_fill_rand(self, rand: RandBuf, inst: Executable) -> None:
        pass

    # relationship
    def rely_on_rand(self, rand: RandBuf, prog: Program) -> Set[int]:
        return set()


class KindSendBufConst(KindSendBuf):
    val_const: bytes

    # debug
    def note(self) -> str:
        return self.val_const.hex()

    # utils
    def toss(self) -> bytes:
        return self.val_const

    def drag(self, data: bytes) -> bytes:
        return super().drag(data)


class KindSendBufRange(KindSendBuf):
    byte_set: List[bytes]
    byte_sep: bytes
    byte_min: int
    byte_max: int

    # defaults
    def default_byte_set(self) -> List[bytes]:
        return list(SPEC_BYTESET)

    def default_byte_sep(self) -> bytes:
        return b''

    def default_byte_min(self) -> int:
        return 0

    def default_byte_max(self) -> int:
        return SPEC_RAND_SIZE_MAX

    # bean
    def validate(self) -> None:
        assert self.byte_sep not in self.byte_set
        assert 0 <= self.byte_min <= self.byte_max

    # debug
    def note(self) -> str:
        return '{}-{}'.format(str(self.byte_min), str(self.byte_max))

    # utils
    def toss(self) -> bytes:
        return self.byte_sep.join([
            SPEC_RANDOM.choice(self.byte_set)
            for _ in range(SPEC_RANDOM.randint(
                self.byte_min, self.byte_max
            ))
        ])

    def drag(self, data: bytes) -> bytes:
        p = SPEC_RANDOM.random()

        if p < 0.5:
            # [DRAG] choose from an extreme value (given range-wise)
            byte_mid = (self.byte_min + self.byte_max) // 2
            step_min = self.byte_min // 10
            step_max = self.byte_max // 10

            num = SPEC_RANDOM.choice([
                1, self.byte_min, self.byte_max, byte_mid,
                max(0, self.byte_min - 1), max(0, self.byte_min - step_min),
                max(0, self.byte_max - 1), max(0, self.byte_max - step_max),
                self.byte_min + 1, self.byte_min + step_min,
                self.byte_max + 1, self.byte_max + step_max,
            ])

            retv = self.byte_sep.join([
                SPEC_RANDOM.choice(self.byte_set)
                for _ in range(num)
            ])
            return self.sanitize(retv)

        else:
            # [DRAG] use parent strategy
            return super().drag(data)


class KindRecvBuf(KindRecv[KobjBuf], ABC):
    fix_size: Optional[int]

    # defaults
    def default_fix_size(self) -> Optional[int]:
        return None

    # memory
    def length(self) -> Optional[int]:
        return self.fix_size

    # builder
    def mk_kobj(self) -> KobjBuf:
        return KobjBuf()

    # operations: engage and remove
    def engage_kobj(self, kobj: KobjBuf, prog: Program) -> None:
        pass

    def remove_kobj(self, kobj: KobjBuf, prog: Program) -> None:
        pass

    # show
    def expo_kobj(self, kobj: KobjBuf) -> str:
        return '[...buf {} bytes...]'.format(self.length())

    # blob
    def blob_size_kobj(self, kobj: KobjBuf) -> int:
        size = self.length()
        assert size is not None
        return size

    def blob_hole_kobj(self, kobj: KobjBuf, inst: Executable) -> None:
        pass

    def blob_data_kobj(self, kobj: KobjBuf, inst: Executable) -> bytes:
        return b'\x00' * self.blob_size_kobj(kobj)

    def blob_fill_kobj(self, kobj: KobjBuf, inst: Executable) -> None:
        pass

    # relationship
    def rely_on_kobj(self, kobj: KobjBuf, prog: Program) -> Set[int]:
        return set()


class KindRecvBufData(KindRecvBuf):

    # debug
    def note(self) -> str:
        return ''

    # chain
    def link(self, ctxt: Syscall) -> None:
        pass
