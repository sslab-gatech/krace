from typing import List, Optional

import sys
import logging

from argparse import ArgumentParser

from fs import FSWorker
from fs_ext4 import FS_CONFIGS_EXT4, FSWorker_EXT4
from fs_btrfs import FS_CONFIGS_BTRFS, FSWorker_BTRFS
from fs_xfs import FS_CONFIGS_XFS, FSWorker_XFS
from fuzz_check import ValidatorMaster
from fuzz_probe import ProbeMaster
from fuzz_engine import FuzzMaster, FuzzBase, Seed

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
        '-t', '--tag', default='000',
        help='Tag of the filesystem configuration (default to 000)',
    )

    # img selection
    parser.add_argument(
        '-i', '--img', default='empty',
        help='Filesystem image (default to empty)',
    )

    # actions
    subs = parser.add_subparsers(dest='cmd')

    # launch
    sub_launch = subs.add_parser(
        'launch',
        help='Launch fuzzer',
    )

    # launch: overall setting
    sub_launch.add_argument(
        '-p', '--nproc', type=int, default=None,
        help='Number of procs for fuzzing'
    )
    sub_launch.add_argument(
        '-s', '--nstep', type=int, default=None,
        help='Number of steps for fuzzing'
    )

    # launch: action selection
    sub_launch.add_argument(
        '-t', '--trial', default=None,
        help='Trial run on one seed instead of start fuzzing'
    )

    # probe
    sub_probe = subs.add_parser(
        'probe',
        help='Probe seeds'
    )

    # probe: overall setting
    sub_probe.add_argument(
        '-p', '--nproc', type=int, default=None,
        help='Number of procs for fuzzing'
    )
    sub_probe.add_argument(
        '-s', '--nstep', type=int, default=None,
        help='Number of steps for fuzzing'
    )

    # validate
    sub_validate = subs.add_parser(
        'validate',
        help='Validate seeds'
    )

    # validate: baseline selection
    sub_validate.add_argument(
        '-f', '--flavor', default=config.OPTION().flavor,
        help='Flavor of the fuzzing session',
    )
    sub_validate.add_argument(
        '-i', '--intent', default='dart-dev',
        help='Intent of the fuzzing session',
    )
    sub_validate.add_argument(
        '-a', '--action', default='fuzz-launch',
        help='Action of the fuzzing session',
    )

    # validate: overall setting
    sub_validate.add_argument(
        '-p', '--nproc', type=int, default=None,
        help='Number of procs for fuzzing'
    )
    sub_validate.add_argument(
        '-s', '--nstep', type=int, default=None,
        help='Number of steps for validation'
    )

    # validate: action selection
    sub_validate.add_argument(
        '-r', '--recency', action='store_true',
        help='Process the seeds in recency order (default: discovery order)'
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
    config.OPTION().action = '-'.join(['fuzz', cmd])

    # construct the filesystem instance
    fswork = None  # type: Optional[FSWorker]

    fsname = config.OPTION().flavor
    if fsname == 'ext4':
        fswork = FSWorker_EXT4(FS_CONFIGS_EXT4[args.tag])

    elif fsname == 'btrfs':
        fswork = FSWorker_BTRFS(FS_CONFIGS_BTRFS[args.tag])

    elif fsname == 'xfs':
        fswork = FSWorker_XFS(FS_CONFIGS_XFS[args.tag])

    else:
        logging.error('Invalid filesystem: {}'.format(fsname))
        parser.print_help()
        return -1

    # choose action
    if cmd == 'launch':
        if args.trial is not None:
            # trial run, only invoke the worker
            toks = args.trial.split(':')
            worker = FuzzBase(fswork, args.img)
            worker.run_once(0, Seed(toks[0], toks[1], int(toks[2])), args.clean)

        else:
            # actual run, invoke the master
            fuzzer = FuzzMaster(fswork, args.img, args.clean)
            fuzzer.launch(args.nproc, args.nstep)

    elif cmd == 'probe':
        prober = ProbeMaster(fswork, args.img, args.clean)
        prober.launch(args.nproc, args.nstep)

    elif cmd == 'validate':
        config.OPTION().tag = '-'.join([args.flavor, args.intent, args.action])
        validator = ValidatorMaster()
        validator.launch(args.nproc, args.nstep, args.recency)

    else:
        parser.print_help()
        return -1

    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
