from typing import List, Tuple, Set, NamedTuple, Optional

import re
import os
import sys
import shutil
import struct
import logging
import traceback

from enum import Enum
from argparse import ArgumentParser

from fs import FSWorker
from fs_ext4 import FS_CONFIGS_EXT4, FSWorker_EXT4
from fs_btrfs import FS_CONFIGS_BTRFS, FSWorker_BTRFS
from fs_xfs import FS_CONFIGS_XFS, FSWorker_XFS
from emu import Emulator, create_emulator, attach_emulator
from fuzz_exec import ExecResolver
from dart_viz import VizRuntime

from util import prepdn, touch, ascii_encode, enable_coloring_in_logging

import config


class TestID(Enum):
    PLAIN = 0


class TestCase(NamedTuple):
    tid: TestID
    args: Tuple[bytes, ...]

    def name(self) -> str:
        return '{}-{}'.format(self.tid.value, self.tid.name)

    def pack(self) -> bytes:
        meta = struct.pack('QQ', self.tid.value, len(self.args))
        data = b''.join(self.args)
        return meta + data


TEST_CASES = [
    TestCase(TestID.PLAIN, ())
]


class TestExec(object):

    def __init__(
            self, iseq: int, fswork: FSWorker, sample: str, fast: bool = False
    ) -> None:
        # basics
        self.iseq = iseq
        self.fswork = fswork
        self.sample = sample
        self.fast = fast

    def run_once(self, case: TestCase, seqn: Optional[int] = None) -> bool:
        logging.info('[{}] Running test case {}'.format(
            self.iseq, case.name() if seqn is None else '{} [{}]'.format(
                case.name(), seqn
            )
        ))

        base = os.path.join(config.TEST_RESULT_PATH, case.name())
        prepdn(base, override=True)

        with create_emulator(False) as emu:
            # pass the instance id via kernel boot parameters
            emu.boot_args.append('dart_instance={}'.format(self.iseq))

            # execute
            if self._run_execute(emu, base, case) and self.fast:
                return True

            # analyze
            runtime = self._run_analyze(emu, base)

            '''
            # keep running until error
            if runtime is None:
                return False

            return len(runtime.races) == 0
            '''

            # TODO (temporary code)
            # save unexpected states
            if runtime is None or len(runtime.races) != 0:
                repo = os.path.join(config.TEST_RESULT_PATH, 'rs')
                prepdn(repo)

                # copy files
                pdst = os.path.join(repo, str(seqn))
                shutil.copytree(base, pdst)

                # report
                if runtime is None:
                    logging.error('Analysis failed: {}'.format(pdst))
                else:
                    logging.warning('Data race detected: {}'.format(pdst))

            return True

    def run_rept(self, case: TestCase, repn: Optional[int] = None) -> None:
        i = 0
        while True:
            if not self.run_once(case, i):
                logging.warning('Test failed')
                break

            i += 1
            if repn is not None and i == repn:
                logging.info('All test runs passed')
                break

    def _run_execute(self, emu: Emulator, base: str, case: TestCase) -> bool:
        # copy over the image
        shutil.copy2(
            self.fswork.path_sample(self.sample),
            os.path.join(emu.session_tmp, config.VIRTEX_DISK_IMG_NAME)
        )

        # inputs
        with open(emu.session_shm, 'r+b') as f:
            # put the metadata
            f.seek(config.INSTMEM_OFFSET(
                self.iseq
            ) + config.INSTMEM_OFFSET_METADATA)

            f.write(struct.pack(
                '@c7sQ',
                ascii_encode('t'),
                ascii_encode('test'),
                0,
            ))

            # put the mount options
            f.write(self.fswork.pack_mount())

            # put the test case info
            f.write(case.pack())

        # launch
        stdout, stderr = emu.launch()

        # outputs
        with open(emu.session_shm, 'rb') as f:
            # analyze the rtinfo
            f.seek(config.INSTMEM_OFFSET(
                self.iseq
            ) + config.INSTMEM_OFFSET_RTINFO)

            feedback = ExecResolver.process_wks(f)

        # save the results
        with open(os.path.join(base, 'stdout'), 'w') as t:
            t.write(stdout)

        with open(os.path.join(base, 'stderr'), 'w') as t:
            t.write(stderr)

        # result
        return feedback.has_proper_exit == 1

    def _run_analyze(self, emu: Emulator, base: str) -> Optional[VizRuntime]:
        ledger_src = os.path.join(emu.session_tmp, 'ledger')
        ledger_dst = os.path.join(base, 'ledger')

        # copy over the raw ledger (or copy from memory)
        if os.path.exists(ledger_src):
            shutil.copy2(ledger_src, ledger_dst)

        else:
            logging.warning('unable to find ledger on disk')

            # try to steal from memory
            with open(emu.session_shm, 'rb') as f:
                f.seek(config.IVSHMEM_OFFSET_HEADER +
                       config.IVSHMEM_OFFSET_RESERVED)

                length = struct.unpack('Q', f.read(8))[0]
                resmax = \
                    config.IVSHMEM_OFFSET_INSTANCES - \
                    config.IVSHMEM_OFFSET_RESERVED

                # seek to the correct ledger instance
                cursor = 0
                while cursor < min(length, resmax):
                    l_seq, l_cnt, l_len = \
                        struct.unpack('QQQ', f.read(24))

                    cursor += 24
                    if l_seq != self.iseq:
                        cursor += l_len
                        continue

                    # migrate the ledger
                    with open(ledger_dst, 'wb') as b:
                        b.write(struct.pack('QQ', l_cnt, l_len))
                        b.write(f.read(l_len))

                    cursor = -1
                    break

                # if no ledger found, there is nothing we can do
                if cursor != -1:
                    logging.error('unable to find ledger in memory')
                    return None

        # do the very expensive validation
        runtime = VizRuntime()
        console = os.path.join(base, 'console')
        failure = False

        try:
            runtime.process(ledger_dst)
        except Exception as ex:
            failure = True
            with open(os.path.join(console + '-error'), 'w') as t:
                t.write(str(ex))
                t.write('\n-------- EXCEPTION --------\n')
                traceback.print_tb(sys.exc_info()[2], file=t)

        # save the console output
        with open(console, 'w') as t:
            t.write('\n'.join(runtime.records))

        # save the races
        runtime.dump_races(console + '-racer')

        # return the runtime states
        return None if failure else runtime


class TestRunner(object):

    def __init__(self, fswork: FSWorker, sample: str, override: bool) -> None:
        # basic
        self.fswork = fswork
        self.sample = sample

        # prepare paths
        prepdn(config.TEST_RESULT_PATH, override=override)

    def run(
            self,
            cases: List[TestCase],
            repn: Optional[int] = None,
            fast: bool = False
    ) -> None:
        # initialize the shared stuff
        with attach_emulator() as emulator:
            # create an empty ivshmem file
            if os.path.exists(emulator.session_shm):
                os.unlink(emulator.session_shm)

            touch(emulator.session_shm, config.IVSHMEM_SIZE)

        # run the workers
        worker = TestExec(0, self.fswork, self.sample, fast)
        for case in cases:
            worker.run_rept(case, repn)


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

    # test selection
    parser.add_argument(
        '-s', '--select', action='append', default=None,
        help='Test case selection'
    )

    # nrun mode
    parser.add_argument(
        '-n', '--num', type=int, default=None,
        help='Number of runs'
    )

    # fast mode
    parser.add_argument(
        '-f', '--fast', action='store_true',
        help='Fast mode (do not analyze on proper exit)'
    )

    subs = parser.add_subparsers(dest='cmd')
    subs.add_parser(
        'test',
        help='Test execution',
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
    config.OPTION().action = '-'.join(['exec', cmd])

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

    # filter test cases
    choices = set()  # type: Set[TestCase]
    if args.select is None:
        choices.update(TEST_CASES)
    else:
        for pattern in args.select:
            matcher = re.compile(pattern)
            for case in TEST_CASES:
                if matcher.match(case.tid.name) is not None:
                    choices.add(case)

    # sort the cases
    cases = sorted(choices, key=lambda i: i.tid)
    logging.info('Test cases selected: {}'.format(len(cases)))

    # choose action
    if cmd == 'test':
        runner = TestRunner(fswork, args.img, args.clean)
        runner.run(cases, args.num, args.fast)

    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
