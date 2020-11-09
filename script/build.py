from typing import List, Optional

import sys
import logging

from argparse import ArgumentParser

from pkg import Package

from pkg_binutils import Package_BINUTILS
from pkg_gcc import Package_GCC
from pkg_llvm import Package_LLVM

from pkg_qemu import Package_QEMU

from pkg_musl import Package_MUSL
from pkg_initramfs import Package_INITRAMFS

from pkg_linux import Package_LINUX

from pkg_e2fsprogs import Package_E2FSPROGS
from pkg_btrfsprogs import Package_BTRFSPROGS
from pkg_xfsprogs import Package_XFSPROGS

from pkg_racer import Package_Racer

from util import enable_coloring_in_logging


def main(argv: List[str]) -> int:
    # setup argument parser
    parser = ArgumentParser()

    # logging configs
    parser.add_argument(
        '-v', '--verbose', action='count', default=1,
        help='Verbosity level, can be specified multiple times, default to 1',
    )

    # override flag
    parser.add_argument(
        '-c', '--clean', action='count', default=0,
        help='Cleaning level, 0 - no clean, 1 - clean build, >1 - clean setup',
    )

    # action selection
    subs = parser.add_subparsers(dest='cmd')

    subs.add_parser(
        'binutils',
        help='Package binutils',
    )

    subs.add_parser(
        'gcc',
        help='Package gcc',
    )

    subs.add_parser(
        'llvm',
        help='Package llvm',
    )

    subs.add_parser(
        'qemu',
        help='Package qemu',
    )

    subs.add_parser(
        'e2fsprogs',
        help='Package e2fs-progs',
    )

    subs.add_parser(
        'btrfsprogs',
        help='Package btrfs-progs',
    )

    subs.add_parser(
        'xfsprogs',
        help='Package xfs-progs',
    )

    subs.add_parser(
        'musl',
        help='Package musl',
    )

    subs.add_parser(
        'linux',
        help='Package linux',
    )

    subs.add_parser(
        'initramfs',
        help='Package initramfs',
    )

    subs.add_parser(
        'racer',
        help='Package racer',
    )

    # parse
    args = parser.parse_args(argv)

    # prepare logs
    enable_coloring_in_logging()
    logging.basicConfig(
        format='%(asctime)s %(levelname)s %(message)s',
        level=logging.WARNING - (logging.DEBUG - logging.NOTSET) * args.verbose
    )

    # construct the instance
    instance = None  # type: Optional[Package]

    if args.cmd == 'binutils':
        instance = Package_BINUTILS()

    elif args.cmd == 'gcc':
        instance = Package_GCC()

    elif args.cmd == 'llvm':
        instance = Package_LLVM()

    elif args.cmd == 'qemu':
        instance = Package_QEMU()

    elif args.cmd == 'musl':
        instance = Package_MUSL()

    elif args.cmd == 'linux':
        instance = Package_LINUX()

    elif args.cmd == 'initramfs':
        instance = Package_INITRAMFS()

    elif args.cmd == 'e2fsprogs':
        instance = Package_E2FSPROGS()

    elif args.cmd == 'btrfsprogs':
        instance = Package_BTRFSPROGS()

    elif args.cmd == 'xfsprogs':
        instance = Package_XFSPROGS()

    elif args.cmd == 'racer':
        instance = Package_Racer()

    else:
        parser.print_help()
        return -1

    try:
        instance.make(args.clean)
    except Exception as ex:
        logging.error('Unexpected error: {}'.format(ex))
        return -2

    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
