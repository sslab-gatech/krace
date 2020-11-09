from typing import cast, Dict, List, Set, Optional
from spec_basis import N_Kobj

from enum import Enum

from spec_const import SPEC_CHARSET, SPEC_RAND_PATH_SEG_MAX
from spec_random import SPEC_RANDOM
from spec_basis import Rand, Kobj, KindSend, Lego, Syscall, Program, \
    Executable, NodeType
from spec_pack import pack_str
from spec_lego_simple import LegoSimple
from spec_type_str import RandStr, KindSendStrRange
from util_bean import Bean, BeanRef


class PathMutationStrategy(Enum):
    CREATE_SEGMENT = 0  # create a completely new segment as path
    APPEND_SEGMENT = 1  # extend base (PathDir) with a new segment
    CHANGE_LAST_SEGMENT = 2  # replace the last segment, not changing type
    REMOVE_FIRST_SEGMENT = 3  # remove first segment, not changing type


class RandPath(Rand):
    dirp: Optional[BeanRef[LegoSimple]]
    comp: bool


class KobjPath(Kobj):
    pass


class KindSendPath(KindSend[RandPath]):
    segment: LegoSimple[RandStr, N_Kobj]
    pathsep: str
    mark: NodeType
    strategies: Dict[PathMutationStrategy, int]

    # default
    def default_segment(self) -> LegoSimple[RandStr, N_Kobj]:
        path_charset = list(SPEC_CHARSET)
        path_charset.remove('/')
        lego_segment = LegoSimple[RandStr, N_Kobj].build(
            kind_send=KindSendStrRange.build(
                char_set=path_charset,
                char_sep='',
                char_min=1,
                char_max=SPEC_RAND_PATH_SEG_MAX,
            )
        )
        return lego_segment

    def default_pathsep(self) -> str:
        return '/'

    def default_strategies(self) -> Dict[PathMutationStrategy, int]:
        return {
            PathMutationStrategy.CREATE_SEGMENT: 1,
            PathMutationStrategy.APPEND_SEGMENT: 1,
            PathMutationStrategy.CHANGE_LAST_SEGMENT: 1,
            PathMutationStrategy.REMOVE_FIRST_SEGMENT: 1,
        }

    # bean
    def validate(self) -> None:
        # at least one of the strategies has to be set
        assert len(self.strategies) > 0

    # debug
    def note(self) -> str:
        return self.mark.name

    # chain
    def link(self, ctxt: Syscall) -> None:
        # use None as the root so we do not associate that lego with anything
        self.segment.link(None, ctxt)

    # memory
    def length(self) -> Optional[int]:
        return None

    # builder
    def mk_rand(self) -> RandPath:
        return RandPath()

    # operations: engage and remove
    def engage_rand(self, rand: RandPath, prog: Program) -> None:
        # prep
        self.segment.engage(prog)
        prog.add_path_rand(self.mark, self.lego.bean)

        # init
        self._build(rand, prog)

    def remove_rand(self, rand: RandPath, prog: Program) -> None:
        # un-prep
        self.segment.remove(prog)
        prog.del_path_rand(self.mark, self.lego.bean)

    # operations: mutate and puzzle
    def mutate_rand(self, rand: RandPath, prog: Program) -> None:
        p = SPEC_RANDOM.random()

        if rand.dirp is None or rand.comp is False or p < 0.5:
            # [TOSS] re-build the path from scratch
            self._build(rand, prog)

        elif p < 0.75:
            # [TOSS] change component
            self.segment.mutate_rand(prog)

        else:
            # [TOSS] change directory
            dirp = cast(
                RandPath,
                prog.gen_path_rand(self.mark, self.lego.bean).rand
            ).dirp
            rand.dirp = None if dirp is None else BeanRef[LegoSimple](dirp.bean)

    def puzzle_rand(self, rand: RandPath, prog: Program) -> None:
        p = SPEC_RANDOM.random()

        if rand.comp is True and p < 0.5:
            # [DRAG] puzzle component
            self.segment.puzzle_rand(prog)

        else:
            # [DRAG] re-build path in a messy way
            k = SPEC_RANDOM.choice([i for i in PathMutationStrategy])
            alts = [i for i in NodeType if i != self.mark]
            mark = SPEC_RANDOM.choice(alts)
            self._make(k, mark, rand, prog)

    # operations: update
    def update_rand(self, rand: RandPath, prog: Program) -> None:
        if rand.dirp is None:
            return

        if rand.dirp.bean.rand is not None:
            return

        # only update when dirp does not exist anymore
        dirp = cast(
            RandPath,
            prog.gen_path_rand(self.mark, self.lego.bean).rand
        ).dirp
        rand.dirp = None if dirp is None else BeanRef[LegoSimple](dirp.bean)

    # operations: migrate
    def migrate_rand(
            self,
            rand: RandPath, orig: RandPath,
            ctxt: Dict[Bean, Bean], hist: Set['Lego']
    ) -> None:
        # first migrate the segment
        self.segment.migrate(
            cast(KindSendPath,
                 cast(LegoSimple, orig.lego.bean).kind_send).segment,
            ctxt, hist
        )

        # then migrate the rand value
        if orig.dirp is None:
            rand.dirp = None
        else:
            rand.dirp = BeanRef[LegoSimple](
                cast(LegoSimple, ctxt[orig.dirp.bean])
            )

        rand.comp = orig.comp

    # show
    def expo_rand(self, rand: RandPath) -> str:
        return self._result(rand)

    # blob
    def blob_size_rand(self, rand: RandPath) -> int:
        return len(self._result(rand)) + 1

    def blob_hole_rand(self, rand: RandPath, inst: Executable) -> None:
        # although the segment lego is embedded, we do not need to find
        # a specific hole in the heap for it
        pass

    def blob_data_rand(self, rand: RandPath, inst: Executable) -> bytes:
        return pack_str(self._result(rand))

    def blob_fill_rand(self, rand: RandPath, inst: Executable) -> None:
        # similar to the logic of blob_hole_rand(), we do not have a
        # hole for the segment lego, therefore, do not propogate the operation
        pass

    # relationship
    def rely_on_rand(self, rand: RandPath, prog: Program) -> Set[int]:
        if rand.dirp is None:
            return set()

        lego = rand.dirp.bean
        deps = lego.rely_on(prog)
        deps.add(prog.lego_index(lego))
        return deps

    # utils
    def _make_create_segment(self, mark: Optional[NodeType],
                             rand: RandPath, prog: Program) -> None:
        rand.dirp = None
        rand.comp = True

    def _make_append_segment(self, mark: Optional[NodeType],
                             rand: RandPath, prog: Program) -> None:
        dirp = prog.gen_path_rand(
            NodeType.DIR if mark is None else mark,
            self.lego.bean
        )
        rand.dirp = BeanRef[LegoSimple](cast(LegoSimple, dirp))
        rand.comp = True

    def _make_change_last_segment(self, mark: Optional[NodeType],
                                  rand: RandPath, prog: Program) -> None:
        dirp = cast(
            RandPath,
            prog.gen_path_rand(
                self.mark if mark is None else mark,
                self.lego.bean
            ).rand
        ).dirp
        rand.dirp = None if dirp is None else BeanRef[LegoSimple](dirp.bean)
        rand.comp = True

    def _make_remove_first_segment(self, mark: Optional[NodeType],
                                   rand: RandPath, prog: Program) -> None:
        dirp = cast(
            RandPath,
            prog.gen_path_rand(
                self.mark if mark is None else mark,
                self.lego.bean
            ).rand
        ).dirp
        rand.dirp = None if dirp is None else BeanRef[LegoSimple](dirp.bean)
        rand.comp = False

    def _make(self, k: PathMutationStrategy, mark: Optional[NodeType],
              rand: RandPath, prog: Program) -> None:
        if k == PathMutationStrategy.CREATE_SEGMENT:
            self._make_create_segment(mark, rand, prog)
        elif k == PathMutationStrategy.APPEND_SEGMENT:
            self._make_append_segment(mark, rand, prog)
        elif k == PathMutationStrategy.CHANGE_LAST_SEGMENT:
            self._make_change_last_segment(mark, rand, prog)
        elif k == PathMutationStrategy.REMOVE_FIRST_SEGMENT:
            self._make_remove_first_segment(mark, rand, prog)
        else:
            raise RuntimeError('Invalid path mutation strategy')

    def _build(self, rand: RandPath, prog: Program) -> None:
        needle = SPEC_RANDOM.randrange(sum(self.strategies.values()))

        cursor = 0
        for k, v in self.strategies.items():
            cursor += v
            if needle >= cursor:
                continue

            self._make(k, None, rand, prog)
            return

        raise RuntimeError('Path mutation strategy not specified')

    def _result_recursive(self, rand: RandPath, segs: List[str]) -> None:
        # fill in segments from begin to end
        if rand.dirp is not None:
            dirp_lego = rand.dirp.bean
            dirp_kind = cast(KindSendPath, dirp_lego.kind_send)
            dirp_rand = cast(RandPath, dirp_lego.rand)
            dirp_kind._result_recursive(dirp_rand, segs)
            assert dirp_kind.pathsep == self.pathsep

        if rand.comp:
            segs.append(cast(RandStr, self.segment.rand).data)
        elif len(segs) != 0:
            segs.pop(0)

    def _result(self, rand: RandPath) -> str:
        segs = []  # type: List[str]
        self._result_recursive(rand, segs)
        return self.pathsep.join(segs)


class RandPathExt(Rand):
    pick: BeanRef[Lego]


class KobjPathExt(Kobj):
    pass


class KindSendPathExt(KindSend[RandPathExt]):
    mark: NodeType

    # bean
    def validate(self) -> None:
        pass

    # debug
    def note(self) -> str:
        return self.mark.name

    # chain
    def link(self, ctxt: Syscall) -> None:
        pass

    # memory
    def length(self) -> Optional[int]:
        return None

    # builder
    def mk_rand(self) -> RandPathExt:
        return RandPathExt()

    # operations: engage and remove
    def engage_rand(self, rand: RandPathExt, prog: Program) -> None:
        # init
        rand.pick = BeanRef[Lego](
            prog.gen_path_rand(self.mark, self.lego.bean)
        )

    def remove_rand(self, rand: RandPathExt, prog: Program) -> None:
        pass

    # operations: mutate and puzzle
    def mutate_rand(self, rand: RandPathExt, prog: Program) -> None:
        p = SPEC_RANDOM.random()

        if p < 0.5 and not prog.lego_in_precall(rand.pick.bean):
            # [TOSS] mutate the underlying path
            rand.pick.bean.mutate_rand(prog)

        else:
            # [TOSS] choose another path
            rand.pick = BeanRef[Lego](
                prog.gen_path_rand(self.mark, self.lego.bean)
            )

    def puzzle_rand(self, rand: RandPathExt, prog: Program) -> None:
        p = SPEC_RANDOM.random()

        if p < 0.5 and not prog.lego_in_precall(rand.pick.bean):
            # [DRAG] puzzle the underlying path
            rand.pick.bean.puzzle_rand(prog)

        else:
            # [DRAG] choose another path not in the same type
            alts = [i for i in NodeType if i != self.mark]
            mark = SPEC_RANDOM.choice(alts)
            rand.pick = BeanRef[Lego](
                prog.gen_path_rand(mark, self.lego.bean)
            )

    # operations: update
    def update_rand(self, rand: RandPathExt, prog: Program) -> None:
        if rand.pick.bean.rand is not None:
            return

        # only update when pick does not exist anymore
        rand.pick = BeanRef[Lego](
            prog.gen_path_rand(self.mark, self.lego.bean)
        )

    # operations: migrate
    def migrate_rand(
            self,
            rand: RandPathExt, orig: RandPathExt,
            ctxt: Dict[Bean, Bean], hist: Set[Lego]
    ) -> None:
        rand.pick.bean = cast(Lego, ctxt[orig.pick.bean])

    # show
    def expo_rand(self, rand: RandPathExt) -> str:
        return rand.pick.bean.show()

    # blob
    def blob_size_rand(self, rand: RandPathExt) -> int:
        return rand.pick.bean.blob_size()

    def blob_hole_rand(self, rand: RandPathExt, inst: Executable) -> None:
        # although we depends on an existing RandPath, we do not require
        # it to be on the heap (although it will be on heap in most cases)
        pass

    def blob_data_rand(self, rand: RandPathExt, inst: Executable) -> bytes:
        return rand.pick.bean.blob_data(inst)

    def blob_fill_rand(self, rand: RandPathExt, inst: Executable) -> None:
        # similar to the logic of blob_hole_rand(), since we do not need
        # the picked lego to be on heap, we can simply pass here
        pass

    # relationship
    def rely_on_rand(self, rand: RandPathExt, prog: Program) -> Set[int]:
        lego = rand.pick.bean
        deps = lego.rely_on(prog)
        deps.add(prog.lego_index(lego))
        return deps
