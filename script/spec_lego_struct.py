from typing import cast, List, Dict, Set, Optional

from spec_random import SPEC_RANDOM
from spec_basis import Rand, Kobj, Lego, Field, Syscall, Program, Executable
from util_bean import Bean


class RandStruct(Rand):
    pass


class KobjStruct(Kobj):
    pass


class LegoStruct(Lego[RandStruct, KobjStruct]):
    size: int
    fields: List[Field]

    # bean
    def validate(self) -> None:
        assert self.size != 0

        names = set()  # type: Set[str]
        sizes = 0
        has_send = self.fields[0].lego.has_info_send()

        for field in self.fields:
            # for duplication check
            names.add(field.name)

            # for size check
            sizes += field.size

            # for flow check
            assert has_send == field.lego.has_info_send()

        assert len(names) == len(self.fields)
        assert self.size == sizes

    # debug
    def note(self) -> str:
        return ', '.join([i.dump() for i in self.fields])

    # chain
    def link_impl(self, ctxt: Syscall) -> None:
        for field in self.fields:
            field.lego.link(self, ctxt)

    # memory
    def length(self) -> Optional[int]:
        return self.size

    # input/output
    def has_info_send(self) -> bool:
        # given all fields are sync-ed in send, pick first one
        return self.fields[0].lego.has_info_send()

    def has_info_recv(self) -> bool:
        # mark the struct as recv only if all fields are recv
        for field in self.fields:
            if not field.lego.has_info_recv():
                return False

        return True

    # builders
    def _mk_rand_impl(self) -> RandStruct:
        return RandStruct()

    def _mk_kobj_impl(self) -> KobjStruct:
        return KobjStruct()

    # operations: engage
    def engage_rand_impl(self, prog: Program) -> None:
        # prep
        for field in self.fields:
            field.lego.engage(prog)

    def engage_kobj_impl(self, prog: Program) -> None:
        # prep
        for field in self.fields:
            field.lego.engage(prog)

    # operations: remove
    def remove_rand_impl(self, prog: Program) -> None:
        # un-prep
        for field in self.fields:
            field.lego.remove(prog)

    def remove_kobj_impl(self, prog: Program) -> None:
        # un-prep
        for field in self.fields:
            field.lego.remove(prog)

    # operations: mutate and puzzle
    def mutate_rand_impl(self, prog: Program) -> None:
        p = SPEC_RANDOM.random()

        if p < 0.8:
            # [TOSS] change only one field
            SPEC_RANDOM.choice(self.fields).lego.mutate_rand(prog)

        else:
            # [TOSS] change multiple fields at once
            num = SPEC_RANDOM.randint(1, len(self.fields))
            for item in SPEC_RANDOM.sample(self.fields, num):
                item.lego.mutate_rand(prog)

    def puzzle_rand_impl(self, prog: Program) -> None:
        p = SPEC_RANDOM.random()

        if p < 0.8:
            # [DRAG] change only one field
            SPEC_RANDOM.choice(self.fields).lego.puzzle_rand(prog)

        else:
            # [DRAG] change multiple fields at once
            num = SPEC_RANDOM.randint(1, len(self.fields))
            for item in SPEC_RANDOM.sample(self.fields, num):
                item.lego.puzzle_rand(prog)

    # operations: update
    def update_rand_impl(self, prog: Program) -> None:
        for field in self.fields:
            field.lego.update_rand(prog)

    # operations: migrate
    def migrate_impl(
            self, other: Lego, ctxt: Dict[Bean, Bean], hist: Set[Lego]
    ) -> None:
        lego = cast(LegoStruct, other)
        for f1, f2 in zip(self.fields, lego.fields):
            f1.lego.migrate(f2.lego, ctxt, hist)

    # show
    def expo(self) -> str:
        caps = 4
        subs = []  # type: List[str]

        for field in self.fields:
            if caps == 0:
                subs.append('...')
                break

            subs.append('{}={}'.format(field.name, field.lego.show()))
            caps -= 1

        return '[{}]'.format(', '.join(subs))

    # blob
    def blob_size(self) -> int:
        size = 0

        for field in self.fields:
            size += field.lego.blob_size()

        return size

    def blob_hole_impl(self, inst: Executable) -> None:
        for field in self.fields:
            field.lego.blob_hole(self, inst)

    def blob_data(self, inst: Executable) -> bytes:
        data = b''

        for field in self.fields:
            data += field.lego.blob_data(inst)

        return data

    def blob_fill_impl(self, inst: Executable) -> None:
        for field in self.fields:
            field.lego.blob_fill(inst)

    # relationship
    def rely_on(self, prog: Program) -> Set[int]:
        deps = set()  # type: Set[int]
        for field in self.fields:
            deps.update(field.lego.rely_on(prog))

        return deps
