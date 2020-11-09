from typing import cast, List, Dict, Set, Optional

from spec_random import SPEC_RANDOM
from spec_basis import Rand, Kobj, Lego, Syscall, Program, Executable
from util_bean import Bean


class RandVector(Rand):
    meta: List[int]


class KobjVector(Kobj):
    pass


class LegoVector(Lego[RandVector, KobjVector]):
    cell_min: int
    cell_max: int
    cells: List[Lego]

    # defaults
    def default_cell_min(self) -> int:
        return 0

    def default_cell_max(self) -> int:
        return len(self.cells)

    # bean
    def validate(self) -> None:
        assert len(self.cells) > 0
        assert 0 <= self.cell_min <= self.cell_max <= len(self.cells)

        has_send = self.cells[0].has_info_send()
        has_recv = self.cells[0].has_info_recv()

        for cell in self.cells:
            # for flow check
            assert has_send == cell.has_info_send()
            assert has_recv == cell.has_info_recv()

    # debug
    def note(self) -> str:
        return '{} x {}-{}'.format(
            self.cells[0].dump(), str(self.cell_min), str(self.cell_max)
        )

    # chain
    def link_impl(self, ctxt: Syscall) -> None:
        for cell in self.cells:
            cell.link(self, ctxt)

    # memory
    def length(self) -> Optional[int]:
        if self.cell_min != self.cell_max:
            return None

        size = self.cells[0].length()
        if size is None:
            return None

        for cell in self.cells:
            if cell.length() != size:
                return None

        return size * self.cell_min

    # input/output
    def has_info_send(self) -> bool:
        # given all cells are sync-ed in send and recv, pick first one
        return self.cells[0].has_info_send()

    def has_info_recv(self) -> bool:
        # given all cells are sync-ed in send and recv, pick first one
        return self.cells[0].has_info_recv()

    # builders
    def _mk_rand_impl(self) -> RandVector:
        return RandVector()

    def _mk_kobj_impl(self) -> KobjVector:
        return KobjVector()

    # operations: engage
    def engage_rand_impl(self, prog: Program) -> None:
        # prep
        for cell in self.cells:
            cell.engage(prog)

        # init
        size = SPEC_RANDOM.randint(self.cell_min, self.cell_max)
        cast(RandVector, self.rand).meta = SPEC_RANDOM.sample(
            list(range(len(self.cells))), size
        )
        SPEC_RANDOM.shuffle(cast(RandVector, self.rand).meta)

    def engage_kobj_impl(self, prog: Program) -> None:
        # prep
        for cell in self.cells:
            cell.engage(prog)

    # operations: remove
    def remove_rand_impl(self, prog: Program) -> None:
        # un-prep
        for cell in self.cells:
            cell.remove(prog)

    def remove_kobj_impl(self, prog: Program) -> None:
        # un-prep
        for cell in self.cells:
            cell.remove(prog)

    # operations: mutate and puzzle
    def mutate_rand_impl(self, prog: Program) -> None:
        rand = cast(RandVector, self.rand)

        size = len(rand.meta)
        p = SPEC_RANDOM.random()

        if p < 0.25:
            # [TOSS] re-order the elements in the vector
            SPEC_RANDOM.shuffle(rand.meta)

        elif (size == self.cell_min) or \
                ((p < 0.5) and (size != self.cell_max)):
            # [TOSS] add more elements to vector
            inc = SPEC_RANDOM.randint(1, self.cell_max - size)
            add = SPEC_RANDOM.sample(
                sorted(set(range(len(self.cells))).difference(rand.meta)), inc
            )
            SPEC_RANDOM.shuffle(add)
            rand.meta.extend(add)

        elif (size == self.cell_max) or \
                ((p < 0.75) and (size != self.cell_min)):
            # [TOSS] remove elements from vector
            dec = SPEC_RANDOM.randint(self.cell_min, size - 1)
            rand.meta = SPEC_RANDOM.sample(rand.meta, dec)

        else:
            # [TOSS] mutate a subset of elements
            nop = SPEC_RANDOM.randrange(size)
            mod = SPEC_RANDOM.sample(rand.meta, nop)

            for i in mod:
                self.cells[i].mutate_rand(prog)

    def puzzle_rand_impl(self, prog: Program) -> None:
        rand = cast(RandVector, self.rand)

        size = len(rand.meta)
        if size == 0:
            return

        p = SPEC_RANDOM.random()

        if size != 0 and p < 0.8:
            # [DRAG] change one element
            pick = SPEC_RANDOM.choice(rand.meta)
            self.cells[pick].puzzle_rand(prog)

        else:
            # [DRAG] change multiple elements
            nop = SPEC_RANDOM.randrange(size)
            mod = SPEC_RANDOM.sample(rand.meta, nop)

            for i in mod:
                self.cells[i].puzzle_rand(prog)

    # operations: update
    def update_rand_impl(self, prog: Program) -> None:
        for cell in self.cells:
            cell.update_rand(prog)

    # operations: migrate
    def migrate_impl(
            self, other: Lego, ctxt: Dict[Bean, Bean], hist: Set[Lego]
    ) -> None:
        lego = cast(LegoVector, other)
        for l1, l2 in zip(self.cells, lego.cells):
            l1.migrate(l2, ctxt, hist)

        if self.has_info_send():
            # will have the same index chosen
            rand = cast(RandVector, self.rand)
            rand.meta.clear()
            rand.meta.extend(cast(RandVector, lego.rand).meta)

    # show
    def expo(self) -> str:
        caps = 4
        subs = []  # type: List[str]

        if self.has_info_send():
            rand = cast(RandVector, self.rand)
            for idx in rand.meta:
                if caps == 0:
                    subs.append('...')
                    break

                subs.append(self.cells[idx].show())
                caps -= 1

        return '[{}]'.format(', '.join(subs))

    # blob
    def blob_size(self) -> int:
        size = 0

        if self.has_info_send():
            rand = cast(RandVector, self.rand)
            for idx in rand.meta:
                size += self.cells[idx].blob_size()

        else:
            # ASSERT: self.has_info_recv()
            for cell in self.cells:
                size += cell.blob_size()

        return size

    def blob_hole_impl(self, inst: Executable) -> None:
        if self.has_info_send():
            rand = cast(RandVector, self.rand)
            for idx in rand.meta:
                self.cells[idx].blob_hole(self, inst)

        else:
            # ASSERT: self.has_info_recv()
            for cell in self.cells:
                cell.blob_hole(self, inst)

    def blob_data(self, inst: Executable) -> bytes:
        data = b''

        if self.has_info_send():
            rand = cast(RandVector, self.rand)
            for idx in rand.meta:
                data += self.cells[idx].blob_data(inst)

        else:
            # ASSERT: self.has_info_recv()
            for cell in self.cells:
                data += cell.blob_data(inst)

        return data

    def blob_fill_impl(self, inst: Executable) -> None:
        if self.has_info_send():
            rand = cast(RandVector, self.rand)
            for idx in rand.meta:
                self.cells[idx].blob_fill(inst)

        else:
            # ASSERT: self.has_info_recv()
            for cell in self.cells:
                cell.blob_fill(inst)

    # relationship
    def rely_on(self, prog: Program) -> Set[int]:
        deps = set()  # type: Set[int]

        if self.has_info_send():
            rand = cast(RandVector, self.rand)
            for idx in rand.meta:
                deps.update(self.cells[idx].rely_on(prog))

        else:
            # ASSERT: self.has_info_recv()
            for cell in self.cells:
                deps.update(cell.rely_on(prog))

        return deps
