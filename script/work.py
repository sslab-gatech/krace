from typing import List, Optional

import sys
import logging

from argparse import ArgumentParser

from fs import FSWorker
from fs_ext4 import FS_CONFIGS_EXT4, FSWorker_EXT4
from fs_btrfs import FS_CONFIGS_BTRFS, FSWorker_BTRFS
from fs_xfs import FS_CONFIGS_XFS, FSWorker_XFS

from util import enable_coloring_in_logging

import config


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
        '-c', '--clean', action='store_true',
        help='Clean existing files',
    )

    # tag selection
    parser.add_argument(
        '-t', '--tag',
        default='000',
        help='Tag of the filesystem configuration (default to 000)',
    )

    # action selection
    subs = parser.add_subparsers(dest='cmd')
    subs.add_parser(
        'prep',
        help='Prepare samples',
    )

    # parse
    args = parser.parse_args(argv)

    # prepare logs
    enable_coloring_in_logging()
    logging.basicConfig(
        format='%(asctime)s %(levelname)s %(message)s',
        level=logging.WARNING - (logging.DEBUG - logging.NOTSET) * args.verbose
    )

    # prepare options
    cmd = args.cmd
    config.OPTION().action = '-'.join(['work', cmd])

    # construct the instance
    fswork = None  # type: Optional[FSWorker]

    fsname = config.OPTION().flavor
    if fsname == 'ext4':
        fswork = FSWorker_EXT4(FS_CONFIGS_EXT4[args.tag])

    elif fsname == 'btrfs':
        fswork = FSWorker_BTRFS(FS_CONFIGS_BTRFS[args.tag])

    elif fsname == 'xfs':
        fswork = FSWorker_XFS(FS_CONFIGS_XFS[args.tag])

    else:
        parser.print_help()
        return -1

    try:
        if cmd == 'prep':
            fswork.prep(args.clean)

    except Exception as ex:
        logging.error('Unexpected error: {}'.format(ex))
        return -2

    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
