from typing import List, Dict, Set, Optional

from abc import ABC, abstractmethod

from spec_const import SPEC_PAGE_SIZE, SPEC_CHARSET, SPEC_RAND_SIZE_MAX
from spec_random import SPEC_RANDOM
from spec_basis import Rand, Kobj, KindSend, KindRecv, Lego, Syscall, Program, \
    Executable
from spec_pack import pack_str
from util_bean import Bean


class RandStr(Rand):
    data: str


class KobjStr(Kobj):
    pass


class KindSendStr(KindSend[RandStr], ABC):
    fix_size: Optional[int]  # maximum length of the string, including the NULL

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
    def mk_rand(self) -> RandStr:
        return RandStr()

    # utils
    def sanitize(self, data: str) -> str:
        if self.fix_size is not None:
            data = data[:self.fix_size - 1]
        return data

    @abstractmethod
    def toss(self) -> str:
        raise RuntimeError('Method not implemented')

    def drag(self, data: str) -> str:
        size = len(data)
        limit = SPEC_PAGE_SIZE + SPEC_RANDOM.randint(-1024, 1024) \
            if self.fix_size is None else self.fix_size

        p = SPEC_RANDOM.random()

        if size == 0:
            # [DRAG] randomly cook up a string if currently empty
            retv = ''.join([
                SPEC_RANDOM.choice(SPEC_CHARSET)
                for _ in range(SPEC_RANDOM.randrange(limit))
            ])

        elif p < 0.2:
            # [DRAG] insert NULL at random places
            pivot = SPEC_RANDOM.randrange(size)
            retv = data[:pivot] + '\0' + data[pivot + 1:]

        elif p < 0.3:
            # [DRAG] repeat the existing data n times
            retv = data * SPEC_RANDOM.randint(1, 3)

        elif p < 0.45:
            # [DRAG] add a char randomly
            stuff = SPEC_RANDOM.randrange(size)
            for _ in range(stuff):
                pivot = SPEC_RANDOM.randrange(size)
                achar = SPEC_RANDOM.choice(SPEC_CHARSET)
                data = data[:pivot] + achar + data[pivot:]
                size += 1
            retv = data

        elif p < 0.6:
            # [DRAG] del a char randomly
            strip = SPEC_RANDOM.randrange(size)
            for _ in range(strip):
                pivot = SPEC_RANDOM.randrange(size)
                data = data[:pivot] + data[pivot + 1:]
                size -= 1
            retv = data

        elif p < 0.75:
            # [DRAG] mod a char randomly
            place = SPEC_RANDOM.randrange(size)
            for _ in range(place):
                pivot = SPEC_RANDOM.randrange(size)
                achar = SPEC_RANDOM.choice(SPEC_CHARSET)
                data = data[:pivot] + achar + data[pivot + 1:]
            retv = data

        elif p < 0.9:
            # [DRAG] repeat a special char up to the limit
            retv = SPEC_RANDOM.choice([
                '', '\0', '\0' * SPEC_RANDOM.randrange(limit),
            ])

        else:
            # [DRAG] randomly cook up a string
            retv = ''.join([
                SPEC_RANDOM.choice(SPEC_CHARSET)
                for _ in range(SPEC_RANDOM.randrange(limit))
            ])

        # sanitize
        return self.sanitize(retv)

    # operations: engage and remove
    def engage_rand(self, rand: RandStr, prog: Program) -> None:
        # init
        rand.data = self.toss()

    def remove_rand(self, rand: RandStr, prog: Program) -> None:
        pass

    # operations: mutate and puzzle
    def mutate_rand(self, rand: RandStr, prog: Program) -> None:
        rand.data = self.toss()

    def puzzle_rand(self, rand: RandStr, prog: Program) -> None:
        rand.data = self.drag(rand.data)

    # operations: update
    def update_rand(self, rand: RandStr, prog: Program) -> None:
        pass

    # operations: migrate
    def migrate_rand(
            self,
            rand: RandStr, orig: RandStr,
            ctxt: Dict[Bean, Bean], hist: Set[Lego]
    ) -> None:
        rand.data = orig.data

    # show
    def expo_rand(self, rand: RandStr) -> str:
        size = len(rand.data)
        return '"{}...str {} bytes..."'.format(
            rand.data[:4] if size >= 4 else rand.data, size
        )

    # blob
    def blob_size_rand(self, rand: RandStr) -> int:
        return len(rand.data) + 1

    def blob_hole_rand(self, rand: RandStr, inst: Executable) -> None:
        pass

    def blob_data_rand(self, rand: RandStr, inst: Executable) -> bytes:
        return pack_str(rand.data)

    def blob_fill_rand(self, rand: RandStr, inst: Executable) -> None:
        pass

    # relationship
    def rely_on_rand(self, rand: RandStr, prog: Program) -> Set[int]:
        return set()


class KindSendStrConst(KindSendStr):
    val_const: str

    # debug
    def note(self) -> str:
        return str(self.val_const)

    # utils
    def toss(self) -> str:
        return self.val_const

    def drag(self, data: str) -> str:
        return super().drag(data)


class KindSendStrRange(KindSendStr):
    char_set: List[str]
    char_sep: str
    char_min: int
    char_max: int

    # defaults
    def default_char_set(self) -> List[str]:
        return list(SPEC_CHARSET)

    def default_char_sep(self) -> str:
        return ''

    def default_char_min(self) -> int:
        return 0

    def default_char_max(self) -> int:
        return SPEC_RAND_SIZE_MAX

    # bean
    def validate(self) -> None:
        assert self.char_sep not in self.char_set
        assert 0 <= self.char_min <= self.char_max

    # debug
    def note(self) -> str:
        return '{}-{}'.format(str(self.char_min), str(self.char_max))

    # utils
    def toss(self) -> str:
        return self.char_sep.join([
            SPEC_RANDOM.choice(self.char_set)
            for _ in range(SPEC_RANDOM.randint(self.char_min, self.char_max))
        ])

    def drag(self, data: str) -> str:
        p = SPEC_RANDOM.random()

        if p < 0.5:
            # [DRAG] choose from an extreme value (given range-wise)
            char_mid = (self.char_min + self.char_max) // 2
            step_min = self.char_min // 10
            step_max = self.char_max // 10

            num = SPEC_RANDOM.choice([
                1, self.char_min, self.char_max, char_mid,
                max(0, self.char_min - 1), max(0, self.char_min - step_min),
                max(0, self.char_max - 1), max(0, self.char_max - step_max),
                self.char_min + 1, self.char_min + step_min,
                self.char_max + 1, self.char_max + step_max,
            ])

            retv = self.char_sep.join([
                SPEC_RANDOM.choice(self.char_set)
                for _ in range(num)
            ])
            return self.sanitize(retv)

        else:
            # [DRAG] use parent strategy
            return super().drag(data)


class KindRecvStr(KindRecv[KobjStr], ABC):
    fix_size: Optional[int]

    # defaults
    def default_fix_size(self) -> Optional[int]:
        return None

    # memory
    def length(self) -> Optional[int]:
        return self.fix_size

    # builder
    def mk_kobj(self) -> KobjStr:
        return KobjStr()

    # operations: engage and remove
    def engage_kobj(self, kobj: KobjStr, prog: Program) -> None:
        pass

    def remove_kobj(self, kobj: KobjStr, prog: Program) -> None:
        pass

    # show
    def expo_kobj(self, kobj: KobjStr) -> str:
        return '"...str {} bytes..."'.format(self.length())

    # blob
    def blob_size_kobj(self, kobj: KobjStr) -> int:
        size = self.length()
        assert size is not None
        return size

    def blob_hole_kobj(self, kobj: KobjStr, inst: Executable) -> None:
        pass

    def blob_data_kobj(self, kobj: KobjStr, inst: Executable) -> bytes:
        return b'\x00' * self.blob_size_kobj(kobj)

    def blob_fill_kobj(self, kobj: KobjStr, inst: Executable) -> None:
        pass

    # relationship
    def rely_on_kobj(self, kobj: KobjStr, prog: Program) -> Set[int]:
        return set()


class KindRecvStrData(KindRecvStr):

    # debug
    def note(self) -> str:
        return ''

    # chain
    def link(self, ctxt: Syscall) -> None:
        pass
