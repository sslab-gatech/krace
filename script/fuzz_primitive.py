#!/usr/bin/env python3

from typing import List, Dict, Tuple

import os
import sys
import json
import pickle
import logging

from argparse import ArgumentParser

from fuzz_exec import Seed
from fuzz_stat import iter_seed_exec_inc
from spec_basis import Syscall, Program

from util import enable_coloring_in_logging


def collect_syscall_primitives_from_probe() -> None:
    progs = {}  # type: Dict[str, Program]
    seed_succ = {}  # type: Dict[Tuple[Seed, int, int], Syscall]
    seed_fail = {}  # type: Dict[int, Dict[Tuple[Seed, int, int], Syscall]]

    for pack in iter_seed_exec_inc():
        base = os.path.dirname(pack.path)
        if base not in progs:
            with open(os.path.join(base, 'program'), 'rb') as f:
                progs[base] = pickle.load(f)

        prog = progs[base]
        with open(os.path.join(pack.path, 'outcome')) as t:
            retv = json.load(t)['subs']

        assert len(prog.thread_subs) == len(retv)
        i_sub = 0
        for p_sub, r_sub in zip(prog.thread_subs, retv):
            assert len(p_sub) == len(r_sub)
            i_sys = 0
            for s, r in zip(p_sub, r_sub):
                key = (pack.seed, i_sub, i_sys)

                # failed executions
                if -4096 < r < 0:
                    if r not in seed_fail:
                        seed_fail[r] = {}

                    if key in seed_fail[r]:
                        continue
                    seed_fail[r][key] = s

                # succeed executions
                else:
                    if key in seed_succ:
                        continue
                    seed_succ[key] = s

                # show the progress
                logging.info('{} = {}'.format(s.show(), r))
                i_sys += 1
            i_sub += 1


def main(argv: List[str]) -> int:
    # prepare parser
    parser = ArgumentParser()

    # logging configs
    parser.add_argument(
        '-v', '--verbose', action='count', default=1,
        help='Verbosity level, can be specified multiple times, default to 1',
    )

    # commands
    subs = parser.add_subparsers(dest='cmd')

    # parse
    sub_show = subs.add_parser('parse')
    sub_show.add_argument('type', choices={'p'})

    # handle args
    args = parser.parse_args(argv)

    # prepare logs
    enable_coloring_in_logging()
    logging.basicConfig(
        format='%(asctime)s %(levelname)s %(message)s',
        level=logging.WARNING - (logging.DEBUG - logging.NOTSET) * args.verbose
    )

    # run action
    if args.cmd == 'parse':
        if args.type == 'p':
            collect_syscall_primitives_from_probe()

    else:
        parser.print_help()
        return -1

    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
