from typing import cast, Dict, Set, Optional, Generic
from spec_basis import T_Rand, T_Kobj

from spec_basis import KindSend, KindRecv, Lego, Syscall, Program, Executable
from util_bean import Bean, BeanRef


class LegoSimple(Lego[T_Rand, T_Kobj], Generic[T_Rand, T_Kobj]):
    kind_send: Optional[KindSend[T_Rand]]
    kind_recv: Optional[KindRecv[T_Kobj]]

    # defaults
    def default_kind_send(self) -> Optional[KindSend[T_Rand]]:
        return None

    def default_kind_recv(self) -> Optional[KindRecv[T_Kobj]]:
        return None

    # bean
    def validate(self) -> None:
        # lego must at least be a sender or a receiver
        assert self.kind_send is not None or self.kind_recv is not None

    # debug
    def note(self) -> str:
        return '{}|{}'.format(
            '-' if self.kind_send is None else self.kind_send.dump(),
            '-' if self.kind_recv is None else self.kind_recv.dump(),
        )

    # chain
    def link_impl(self, ctxt: Syscall) -> None:
        if self.kind_send is not None:
            self.kind_send.lego = BeanRef[Lego](self)
            self.kind_send.link(ctxt)

        if self.kind_recv is not None:
            self.kind_recv.lego = BeanRef[Lego](self)
            self.kind_recv.link(ctxt)

    # memory
    def length(self) -> Optional[int]:
        if self.kind_send is None:
            assert self.kind_recv is not None
            return self.kind_recv.length()

        if self.kind_recv is None:
            return self.kind_send.length()

        len_send = self.kind_send.length()
        len_recv = self.kind_recv.length()

        if len_send is None:
            assert len_recv is None
        else:
            assert len_recv is not None and len_send == len_recv

        return len_send

    # input/output
    def has_info_send(self) -> bool:
        return self.kind_send is not None

    def has_info_recv(self) -> bool:
        return self.kind_recv is not None

    # builders
    def _mk_rand_impl(self) -> T_Rand:
        return cast(KindSend[T_Rand], self.kind_send).mk_rand()

    def _mk_kobj_impl(self) -> T_Kobj:
        return cast(KindRecv[T_Kobj], self.kind_recv).mk_kobj()

    # operations: engage
    def engage_rand_impl(self, prog: Program) -> None:
        # prep
        cast(KindSend[T_Rand], self.kind_send) \
            .engage_rand(cast(T_Rand, self.rand), prog)

    def engage_kobj_impl(self, prog: Program) -> None:
        # prep
        cast(KindRecv[T_Kobj], self.kind_recv) \
            .engage_kobj(cast(T_Kobj, self.kobj), prog)

    # operations: remove
    def remove_rand_impl(self, prog: Program) -> None:
        # un-prep
        cast(KindSend[T_Rand], self.kind_send) \
            .remove_rand(cast(T_Rand, self.rand), prog)

    def remove_kobj_impl(self, prog: Program) -> None:
        # un-prep
        cast(KindRecv[T_Kobj], self.kind_recv) \
            .remove_kobj(cast(T_Kobj, self.kobj), prog)

    # operations: mutate and puzzle
    def mutate_rand_impl(self, prog: Program) -> None:
        cast(KindSend[T_Rand], self.kind_send) \
            .mutate_rand(cast(T_Rand, self.rand), prog)

    def puzzle_rand_impl(self, prog: Program) -> None:
        cast(KindSend[T_Rand], self.kind_send) \
            .puzzle_rand(cast(T_Rand, self.rand), prog)

    # operations: update
    def update_rand_impl(self, prog: Program) -> None:
        cast(KindSend[T_Rand], self.kind_send) \
            .update_rand(cast(T_Rand, self.rand), prog)

    # operations: migrate
    def migrate_impl(
            self, other: Lego, ctxt: Dict[Bean, Bean], hist: Set[Lego]
    ) -> None:
        lego = cast(LegoSimple, other)
        if self.has_info_send():
            cast(KindSend[T_Rand], self.kind_send).migrate_rand(
                cast(T_Rand, self.rand), cast(T_Rand, lego.rand), ctxt, hist
            )

    # show
    def expo(self) -> str:
        if self.has_info_send():
            return cast(KindSend[T_Rand], self.kind_send) \
                .expo_rand(cast(T_Rand, self.rand))

        else:
            # ASSERT: self.has_info_recv()
            return cast(KindRecv[T_Kobj], self.kind_recv) \
                .expo_kobj(cast(T_Kobj, self.kobj))

    # blob
    def blob_size(self) -> int:
        if self.has_info_send():
            return cast(KindSend[T_Rand], self.kind_send) \
                .blob_size_rand(cast(T_Rand, self.rand))

        else:
            # ASSERT: self.has_info_recv()
            return cast(KindRecv[T_Kobj], self.kind_recv) \
                .blob_size_kobj(cast(T_Kobj, self.kobj))

    def blob_hole_impl(self, inst: Executable) -> None:
        if self.has_info_send():
            return cast(KindSend[T_Rand], self.kind_send) \
                .blob_hole_rand(cast(T_Rand, self.rand), inst)

        else:
            # ASSERT: self.has_info_recv()
            return cast(KindRecv[T_Kobj], self.kind_recv) \
                .blob_hole_kobj(cast(T_Kobj, self.kobj), inst)

    def blob_data(self, inst: Executable) -> bytes:
        if self.has_info_send():
            return cast(KindSend[T_Rand], self.kind_send) \
                .blob_data_rand(cast(T_Rand, self.rand), inst)

        else:
            # ASSERT: self.has_info_recv()
            return cast(KindRecv[T_Kobj], self.kind_recv) \
                .blob_data_kobj(cast(T_Kobj, self.kobj), inst)

    def blob_fill_impl(self, inst: Executable) -> None:
        if self.has_info_send():
            return cast(KindSend[T_Rand], self.kind_send) \
                .blob_fill_rand(cast(T_Rand, self.rand), inst)

        else:
            # ASSERT: self.has_info_recv()
            return cast(KindRecv[T_Kobj], self.kind_recv) \
                .blob_fill_kobj(cast(T_Kobj, self.kobj), inst)

    # relationship
    def rely_on(self, prog: Program) -> Set[int]:
        if self.has_info_send():
            return cast(KindSend[T_Rand], self.kind_send) \
                .rely_on_rand(cast(T_Rand, self.rand), prog)

        else:
            # ASSERT: self.has_info_recv()
            return cast(KindRecv[T_Kobj], self.kind_recv) \
                .rely_on_kobj(cast(T_Kobj, self.kobj), prog)
