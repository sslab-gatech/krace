#!/usr/bin/env python3

from typing import List

import os
import sys
import shutil
import logging

from argparse import ArgumentParser

from fuzz_stat import iter_seed_exec_inc

from util import enable_coloring_in_logging, prepfn

import config

STORAGE_BASE = '/home/changseok/racer'


def move_files() -> None:
    base = os.path.join(config.STUDIO_BATCH, config.OPTION().tag)

    for pack in iter_seed_exec_inc():
        path_racer = os.path.join(pack.path, 'console-racer')
        path_ledger = os.path.join(pack.path, 'ledger')
        if os.path.exists(path_racer) and not os.path.islink(path_ledger):
            path_rel = os.path.relpath(path_ledger, base)
            path_new = os.path.join(STORAGE_BASE, path_rel)

            # copy things over
            if not os.path.exists(path_new):
                prepfn(path_new)
                shutil.copy2(path_ledger, path_new)

            # build the symlink
            os.unlink(path_ledger)
            os.symlink(path_new, path_ledger)

            # done
            logging.info('Moved: {}'.format(path_rel))


def main(argv: List[str]) -> int:
    # prepare parser
    parser = ArgumentParser()

    # logging configs
    parser.add_argument(
        '-v', '--verbose', action='count', default=1,
        help='Verbosity level, can be specified multiple times, default to 1',
    )

    subs = parser.add_subparsers(dest='cmd')
    subs.add_parser('move')

    # handle args
    args = parser.parse_args(argv)

    # prepare logs
    enable_coloring_in_logging()
    logging.basicConfig(
        format='%(asctime)s %(levelname)s %(message)s',
        level=logging.WARNING - (logging.DEBUG - logging.NOTSET) * args.verbose
    )

    # run action
    if args.cmd == 'move':
        move_files()

    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
