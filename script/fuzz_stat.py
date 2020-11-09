#!/usr/bin/env python3

from typing import cast, NamedTuple, Iterator, Dict, Set, List, Tuple, Optional

import re
import os
import sys
import time
import pickle

from dataclasses import dataclass
from argparse import ArgumentParser

from spec_basis import Syscall, Program
from fuzz_engine import Seed

import config


class SeedExecPack(NamedTuple):
    seed: Seed
    rseq: int
    path: str
    ctime: float


@dataclass
class PrimitivePack(object):
    prog: Program
    ctime: float


@dataclass
class StraceRecord(object):
    tseq: int
    name: str
    retv: int
    line: str

    def is_error(self) -> bool:
        return -4096 < self.retv < 0


class StraceLedger(object):

    def __init__(self) -> None:
        self.ledger = {}  # type: Dict[int, List[StraceRecord]]

    def add_record(self, record: StraceRecord) -> None:
        if record.tseq not in self.ledger:
            self.ledger[record.tseq] = []

        self.ledger[record.tseq].append(record)

    @classmethod
    def _check(cls, trace: List[StraceRecord], given: List[Syscall]) -> bool:
        if len(trace) != len(given):
            return False

        for record, syscall in zip(trace, given):
            if record.name != syscall.name.split('$')[0]:
                return False

        return True

    def validate(self, program: Program) -> bool:
        if not StraceLedger._check(self.ledger[0], program.thread_main):
            return False

        i = 1
        for thread in program.thread_subs:
            if len(thread) == 0:
                continue

            if not StraceLedger._check(self.ledger[i], thread):
                return False

            i += 1

        return True

    def link(self, program: Program) -> Dict[Syscall, StraceRecord]:
        result = {}  # type: Dict[Syscall, StraceRecord]

        i = 1
        for thread in program.thread_subs:
            if len(thread) == 0:
                continue

            for syscall, record in zip(thread, self.ledger[i]):
                result[syscall] = record

            i += 1

        return result


# parsers
def parse_strace(base: str) -> StraceLedger:
    re_head = re.compile(r'^\[strace: *(\d+?)\] (->|<-) (\w+?)\(')
    re_tail = re.compile(r'\) = (-?\d+|<fd: -?\d+>)$')

    records = []  # type: List[StraceRecord]
    tseqset = set()  # type: Set[int]

    with open(os.path.join(base, 'strace'), 'r') as f:
        r = None  # type: Optional[StraceRecord]
        for l in f:
            counted = False

            # check if head is present
            if r is None:
                m = re_head.search(l)
                assert m is not None
                r = StraceRecord(
                    tseq=int(m.group(1)) if m.group(2) == '<-' else 0,
                    name=m.group(3),
                    retv=0,
                    line=l,
                )
                counted = True

            # check if tail is present
            if r is not None:
                m = re_tail.search(l)
                if m is None:
                    r.line += l
                    continue

                retv = m.group(1)
                if 'fd' in retv:
                    r.retv = int(retv[5:-1])
                else:
                    r.retv = int(retv)

                if not counted:
                    r.line += l

                # only record those with return value
                if r.tseq != 0:
                    records.append(r)
                    tseqset.add(r.tseq)

                r = None

    # sort the records by thread id
    tseqord = sorted(tseqset)
    for r in records:
        r.tseq = tseqord.index(r.tseq)

    # build the ledger
    ledger = StraceLedger()

    for r in records:
        ledger.add_record(r)

    return ledger


# iterator
def iter_seed_exec() -> Iterator[SeedExecPack]:
    stamp = time.time()

    path = os.path.join(
        config.STUDIO_BATCH, config.OPTION().tag, 'queue'
    )
    for sketch in os.listdir(path):
        _p1 = os.path.join(path, sketch)
        for digest in os.listdir(_p1):
            _p2 = os.path.join(_p1, digest)
            for bucket in os.listdir(_p2):
                seed = Seed(sketch, digest, int(bucket))

                path_seed = os.path.join(path, sketch, digest, bucket)
                for res in os.listdir(path_seed):
                    if res == 'program':
                        continue

                    path_exec = os.path.join(path_seed, res)
                    ctime = os.path.getctime(path_exec)
                    if stamp - ctime < 5:
                        continue

                    yield SeedExecPack(
                        seed, int(res), path_exec, ctime
                    )


def iter_seed_exec_inc() -> Iterator[SeedExecPack]:
    packs = [i for i in iter_seed_exec()]
    for i in sorted(packs, key=lambda x: x.ctime):
        yield i


def iter_seed_exec_dec() -> Iterator[SeedExecPack]:
    packs = [i for i in iter_seed_exec()]
    for i in sorted(packs, key=lambda x: x.ctime, reverse=True):
        yield i


def iter_syscall_strace() -> Iterator[Tuple[str, Syscall, StraceRecord]]:
    progs = {}  # type: Dict[str, Program]
    for pack in iter_seed_exec_inc():
        base = os.path.dirname(pack.path)
        if base not in progs:
            with open(os.path.join(base, 'program'), 'rb') as f:
                progs[base] = pickle.load(f)

        prog = progs[base]
        ledger = parse_strace(pack.path)
        assert ledger.validate(prog)

        strace = ledger.link(prog)
        for syscall, record in strace.items():
            yield pack.path, syscall, record


def iter_primitive() -> Iterator[PrimitivePack]:
    stamp = time.time()

    base = os.path.join(
        config.STUDIO_BATCH, config.OPTION().tag, 'prime'
    )
    for sketch in os.listdir(base):
        _p1 = os.path.join(base, sketch)
        for digest in os.listdir(_p1):
            _p2 = os.path.join(_p1, digest)
            for bucket in os.listdir(_p2):
                path = os.path.join(_p2, bucket, 'program')

                ctime = os.path.getctime(path)
                if stamp - ctime < 5:
                    continue

                with open(path, 'rb') as f:
                    yield PrimitivePack(
                        cast(Program, pickle.load(f)), ctime
                    )


def iter_primitive_inc() -> Iterator[PrimitivePack]:
    packs = [i for i in iter_primitive()]
    for i in sorted(packs, key=lambda x: x.ctime):
        yield i


def iter_primitive_dec() -> Iterator[PrimitivePack]:
    packs = [i for i in iter_primitive()]
    for i in sorted(packs, key=lambda x: x.ctime, reverse=True):
        yield i


# actions
def show_execution_evolution() -> None:
    i = 0
    for pack in iter_seed_exec_inc():
        print('---------------- {} ----------------'.format(i))

        with open(os.path.join(pack.path, 'readable'), 'r') as f:
            print(f.read())

        i += 1


def show_primitive_evolution() -> None:
    i = 0
    for pack in iter_primitive_inc():
        print('---------------- {} ----------------'.format(i))
        print(pack.prog.gen_readable())

        i += 1


def show_syscall_stats() -> None:
    stats = {}  # type: Dict[str, Tuple[int, int]]

    # collect stats
    for _, syscall, record in iter_syscall_strace():
        if syscall.name not in stats:
            stats[syscall.name] = (0, 0)

        num_error, num_total = stats[syscall.name]
        stats[syscall.name] = (
            num_error + (1 if record.is_error() else 0), num_total + 1
        )

    # show stats
    for k in sorted(stats.keys()):
        num_error, num_total = stats[k]
        print('{}: {} / {} ({:2.0f}%)'.format(
            k, num_error, num_total, num_error / num_total * 100
        ))


def find_in_program(needle: str) -> None:
    regex = re.compile(needle)

    for pack in iter_seed_exec_inc():
        with open(os.path.join(pack.path, 'readable'), 'r') as f:
            if regex.search(f.read()) is not None:
                print(pack.path)


def find_in_strace(needle: str) -> None:
    regex = re.compile(needle)

    for pack in iter_seed_exec_inc():
        with open(os.path.join(pack.path, 'strace'), 'r') as f:
            if regex.search(f.read()) is not None:
                print(pack.path)


def list_syscall_strace(name: str) -> None:
    for path, syscall, record in iter_syscall_strace():
        if syscall.name == name:
            print('- {} -'.format(path))
            print(syscall.dump())  # the spec
            print(syscall.show())  # the program rand results
            print(record.line.strip())  # the actual strace record


def main(argv: List[str]) -> int:
    # prepare parser
    parser = ArgumentParser()

    subs = parser.add_subparsers(dest='cmd')

    # show
    sub_show = subs.add_parser('show')
    sub_show.add_argument('type', choices={'e', 'p', 's'})

    # list
    sub_list = subs.add_parser('list')
    sub_list.add_argument('type', choices={'s'})
    sub_list.add_argument('item')

    # find
    sub_find = subs.add_parser('find')
    sub_find.add_argument('type', choices={'p', 's'})
    sub_find.add_argument('item')

    # view
    sub_view = subs.add_parser('view')
    sub_view.add_argument('type', choices={'l'})
    sub_view.add_argument('base')
    sub_view.add_argument('seed', type=int)

    # handle args
    args = parser.parse_args(argv)

    # run action
    if args.cmd == 'show':
        if args.type == 'e':
            show_execution_evolution()

        elif args.type == 'p':
            show_primitive_evolution()

        elif args.type == 's':
            show_syscall_stats()

    elif args.cmd == 'list':
        if args.type == 's':
            list_syscall_strace(args.item)

    elif args.cmd == 'find':
        if args.type == 'p':
            find_in_program(args.item)

        elif args.type == 's':
            find_in_strace(args.item)

    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
