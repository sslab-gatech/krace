from typing import cast, BinaryIO, NamedTuple, Optional

import os
import sys
import json
import shutil
import struct
import pickle
import traceback

from enum import Enum
from dataclasses import dataclass, asdict

from fs import FSWorker
from emu import create_emulator, attach_emulator, Emulator
from spec_basis import Program, Outcome
from spec_factory import Spec
from dart_viz import VizRuntime

from util import touch, prepdn, mkdir_seq, ascii_encode, dump_execute_outputs

import config


@dataclass
class Feedback(object):
    # states
    has_proper_exit: int
    has_warning_or_error: int

    # coverage
    cov_cfg_edge_incr: int
    cov_dfg_edge_incr: int
    cov_alias_inst_incr: int

    def json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    @classmethod
    def load(cls, path: str) -> 'Feedback':
        with open(path, 'r') as f:
            data = json.load(f)
            return Feedback(
                has_proper_exit=data['has_proper_exit'],
                has_warning_or_error=data['has_warning_or_error'],
                cov_cfg_edge_incr=data['cov_cfg_edge_incr'],
                cov_dfg_edge_incr=data['cov_dfg_edge_incr'],
                cov_alias_inst_incr=data['cov_alias_inst_incr'],
            )

    def merge(self, feedback: 'Feedback') -> None:
        # states
        self.has_proper_exit &= feedback.has_proper_exit
        self.has_warning_or_error &= feedback.has_warning_or_error

        # coverage
        self.cov_cfg_edge_incr += feedback.cov_cfg_edge_incr
        self.cov_dfg_edge_incr += feedback.cov_dfg_edge_incr
        self.cov_alias_inst_incr += feedback.cov_alias_inst_incr


@dataclass
class ResultPack(object):
    error: Optional[Exception]
    stdout: str
    stderr: str
    strace: str
    rtrace: bytes
    outcome: Outcome
    readable: str
    feedback: Feedback

    def dump(self) -> None:
        dump_execute_outputs(
            self.stdout,
            self.stderr,
            strace=self.strace,
            rtrace='[... {} ...]'.format(len(self.rtrace)),
            outcome=self.outcome.json(),
            readable=self.readable,
            feedback=self.feedback.json()
        )

    def save(self, path: str) -> None:
        with open(os.path.join(path, 'stdout'), 'w') as f:
            f.write(self.stdout)

        with open(os.path.join(path, 'stderr'), 'w') as f:
            f.write(self.stderr)

        with open(os.path.join(path, 'strace'), 'w') as f:
            f.write(self.strace)

        with open(os.path.join(path, 'rtrace'), 'wb') as b:
            b.write(self.rtrace)

        with open(os.path.join(path, 'outcome'), 'w') as f:
            f.write(self.outcome.json())

        with open(os.path.join(path, 'readable'), 'w') as f:
            f.write(self.readable)

        with open(os.path.join(path, 'feedback'), 'w') as f:
            f.write(self.feedback.json())


class ExecResolver(object):

    @classmethod
    def process_wks(cls, f: BinaryIO) -> Feedback:
        pack = struct.unpack('QQQQQ', f.read(40))
        return Feedback(
            has_proper_exit=pack[0],
            has_warning_or_error=pack[1],
            cov_cfg_edge_incr=pack[2],
            cov_dfg_edge_incr=pack[3],
            cov_alias_inst_incr=pack[4],
        )

    # a naive way to find signals in stdout
    @classmethod
    def has_bug_signal(cls, stdout: str) -> bool:
        signals = [
            # generic
            'BUG',
            'ERROR', 'WARNING',
            '====', '----',

            # lockdep: see kernel/locking/lockdep.c
            '*** DEADLOCK ***'
        ]

        for l in stdout.splitlines():
            # filter out uninteresting cases
            if '[racer]: Stopping the guest system' in l:
                # reached to the end of racer, ignore the rest of the messages
                # NOTE: some regression in the kernel will cause bugs like
                #       sched: Unexpected reschedule of offline CPU#1!
                # we are not interested in these bugs
                break

            if 'WARNING: stack going in the wrong direction?' in l:
                continue

            # now the actual checking
            for s in signals:
                if s in l:
                    return True

        # no signals found
        return False


class FuzzExec(object):

    def __init__(
            self, iseq: int, fswork: FSWorker, sample: str, oneshot: bool,
            staging: Optional[str] = None, staging_check: bool = False,
            analyze: bool = False, analyze_fast: bool = False
    ) -> None:
        # basics
        self.iseq = iseq
        self.fswork = fswork
        self.sample = sample
        self.oneshot = oneshot

        # staging
        self.staging = staging
        self.staging_check = staging_check

        # analyze
        self.analyze = analyze
        self.analyze_fast = analyze_fast

    def run(self, program: Program) -> ResultPack:
        with create_emulator(self.oneshot) as emu:
            # pass the instance id via kernel boot parameters
            emu.boot_args.append('dart_instance={}'.format(self.iseq))

            # execute
            result = self._run_execute(emu, program)

            # analyze
            if self.analyze:
                self._run_analyze(emu, result)

            # staging
            if self.staging_check and not result.feedback.has_proper_exit:
                self._run_analyze(emu, result)

            if self.staging is not None:
                path_ledger = os.path.join(emu.session_tmp, 'ledger')
                if os.path.exists(path_ledger):
                    os.rename(
                        os.path.join(emu.session_tmp, 'ledger'),
                        os.path.join(self.staging, 'ledger')
                    )

            # return with the result pack
            return result

    def _run_execute(self, emu: Emulator, program: Program) -> ResultPack:
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
                ascii_encode('f'),
                ascii_encode('fuzz'),
                0,
            ))
            f.write(self.fswork.pack_mount())

            # put the bytecode
            f.seek(config.INSTMEM_OFFSET(
                self.iseq
            ) + config.INSTMEM_OFFSET_BYTECODE)

            inst, mach = program.gen_bytecode()
            f.write(mach)

        # launch
        stdout, stderr = emu.launch()

        # outputs
        with open(emu.session_shm, 'rb') as f:
            # get the strace
            f.seek((config.INSTMEM_OFFSET(
                self.iseq
            ) + config.INSTMEM_OFFSET_STRACE))

            length = struct.unpack('Q', f.read(8))[0]
            strace = f.read(length).decode('charmap')

            # analyze the rtinfo
            f.seek(config.INSTMEM_OFFSET(
                self.iseq
            ) + config.INSTMEM_OFFSET_RTINFO)

            feedback = ExecResolver.process_wks(f)

            # get the rtrace
            f.seek(config.INSTMEM_OFFSET(
                self.iseq
            ) + config.INSTMEM_OFFSET_RTRACE)

            length = struct.unpack('Q', f.read(8))[0]
            rtrace = f.read(length * 4 * 8)

            # inspect the outcome
            f.seek(config.INSTMEM_OFFSET(
                self.iseq
            ) + config.INSTMEM_OFFSET_BYTECODE)

            offs = len(mach) - len(inst.heap)
            outcome = program.inspect(inst, f.read(len(mach))[offs:])

        # check bug signals in stdout
        if ExecResolver.has_bug_signal(stdout):
            feedback.has_warning_or_error = 1

        # put everything in the result pack
        readable = program.gen_readable()
        return ResultPack(
            error=None,
            stdout=stdout,
            stderr=stderr,
            strace=strace,
            rtrace=rtrace,
            outcome=outcome,
            readable=readable,
            feedback=feedback,
        )

    def _run_analyze(self, emu: Emulator, result: ResultPack) -> None:
        # prepare the holding directory
        path = os.path.join(config.VALIDATION_WORKER_PATH, str(self.iseq))
        prepdn(path, override=True)

        # save the result pack
        result.save(path)

        # copy over the raw ledger (or copy from memory)
        path_ledger = os.path.join(emu.session_tmp, 'ledger')

        if not os.path.exists(path_ledger):
            result.error = RuntimeError(
                'ledger does not exist, program crashed or hanged', ''
            )

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
                    with open(path_ledger, 'wb') as b:
                        b.write(struct.pack('QQ', l_cnt, l_len))
                        b.write(f.read(l_len))

                    cursor = -1
                    break

                # if no ledger found, there is nothing we can do
                if cursor != -1:
                    with open(path_ledger, 'wb') as b:
                        b.write(struct.pack('QQ', 0, 0))

        # run the offline validation
        shutil.copy2(path_ledger, path)

        # if analyze_fast is set, skip analysis if execution succeeds
        if self.analyze_fast and result.error is None:
            return

        # do the very expensive validation
        runtime = VizRuntime()

        try:
            runtime.process(path_ledger)
        except AssertionError as ex:
            with open(os.path.join(path, 'error'), 'w') as t:
                t.write('\n-------- EXCEPTION --------\n')
                traceback.print_tb(sys.exc_info()[2], file=t)

            if result.error is None:
                result.error = ex

        # save the console output
        console = '\n'.join(runtime.records)
        with open(os.path.join(path, 'console'), 'w') as t:
            t.write(console)

        # if validation failed, save the whole package to error dir
        if result.error is not None:
            prepdn(config.VALIDATION_FAILED_PATH)
            path_rescue = mkdir_seq(config.VALIDATION_FAILED_PATH)
            for item in os.listdir(path):
                shutil.copy2(os.path.join(path, item), path_rescue)


class Seed(NamedTuple):
    sketch: str
    digest: str
    bucket: int


class SeedBase(Enum):
    DEBUG = 1
    CRASH = 2
    ERROR = 3
    QUEUE = 4
    PRIME = 5


class FuzzUnit(object):

    def __init__(self, fswork: FSWorker, sample: str) -> None:
        # basics
        self.fswork = fswork
        self.sample = sample

        # deps
        self.spec = Spec.formulate()

        # dirs
        self.wks_base = os.path.join(
            config.STUDIO_BATCH,
            config.OPTION().label
        )
        self.wks_temp = os.path.join(
            config.VIRTEX_TMP_DIR,
            'racer-fuzzing-{}'.format(config.OPTION().label)
        )

        # paths: coverage
        self.path_cov = os.path.join(self.wks_base, 'coverage')
        self.path_cov_cfg_edge = os.path.join(self.path_cov, 'cfg_edge')
        self.path_cov_dfg_edge = os.path.join(self.path_cov, 'dfg_edge')
        self.path_cov_alias_inst = os.path.join(self.path_cov, 'alias_inst')

    # instance path
    def _path_instance(self, iseq: Optional[int]) -> str:
        if iseq is None:
            return self.wks_base
        else:
            return os.path.join(self.wks_temp, str(iseq))

    # persistent program
    def _path_program(self, iseq: Optional[int], base: SeedBase) -> str:
        return os.path.join(self._path_instance(iseq), base.name.lower())

    def _save_program(
            self, iseq: Optional[int], base: SeedBase, program: Program
    ) -> str:
        sketch, digest = program.summary()

        # locate the program directory
        padir = os.path.join(self._path_program(iseq, base), sketch, digest)
        prepdn(padir)

        # check if this program is already persisted
        for bucket in os.listdir(padir):
            prog = self._load_program(
                iseq, base, Seed(sketch, digest, int(bucket))
            )
            if not prog.gen_synopsis().match(program.gen_synopsis()):
                continue

            if not prog.gen_bytecode()[1] == program.gen_bytecode()[1]:
                continue

            return os.path.join(padir, bucket)

        # create the sub-directory
        path = mkdir_seq(padir)
        with open(os.path.join(path, 'program'), 'wb') as f:
            pickle.dump(program, f)

        return path

    def _load_program(
            self, iseq: Optional[int], base: SeedBase, seed: Seed
    ) -> Program:
        path = os.path.join(
            self._path_program(iseq, base),
            seed.sketch, seed.digest, str(seed.bucket)
        )
        with open(os.path.join(path, 'program'), 'rb') as f:
            return cast(Program, pickle.load(f))

    # persistent execution
    def _save_result(
            self, iseq: Optional[int], base: SeedBase, program: Program,
            result: ResultPack
    ) -> str:
        spath = self._save_program(iseq, base, program)
        rpath = mkdir_seq(spath)
        result.save(rpath)
        return rpath

    # persistent states
    def _cov_initialie(self) -> None:
        # init the coverage bitmaps (all empty)
        touch(self.path_cov_cfg_edge, config.BITMAP_COV_CFG_EDGE_SIZE)
        touch(self.path_cov_dfg_edge, config.BITMAP_COV_DFG_EDGE_SIZE)
        touch(self.path_cov_alias_inst, config.BITMAP_COV_ALIAS_INST_SIZE)

    def _cov_recover(self) -> None:
        # load the coverage bitmaps
        with attach_emulator() as emulator:
            # create an empty ivshmem file
            if os.path.exists(emulator.session_shm):
                os.unlink(emulator.session_shm)

            touch(emulator.session_shm, config.IVSHMEM_SIZE)

            # load the saved coverage
            with open(emulator.session_shm, 'r+b') as f:
                f.seek(config.IVSHMEM_OFFSET_COV_CFG_EDGE)
                with open(self.path_cov_cfg_edge, 'rb') as g:
                    f.write(g.read(config.BITMAP_COV_CFG_EDGE_SIZE))

                f.seek(config.IVSHMEM_OFFSET_COV_DFG_EDGE)
                with open(self.path_cov_dfg_edge, 'rb') as g:
                    f.write(g.read(config.BITMAP_COV_DFG_EDGE_SIZE))

                f.seek(config.IVSHMEM_OFFSET_COV_ALIAS_INST)
                with open(self.path_cov_alias_inst, 'rb') as g:
                    f.write(g.read(config.BITMAP_COV_ALIAS_INST_SIZE))

    def _cov_checkpoint(self) -> None:
        # save the coverage bitmaps
        with attach_emulator() as emulator:
            with open(emulator.session_shm, 'rb') as f:
                f.seek(config.IVSHMEM_OFFSET_COV_CFG_EDGE)
                with open(self.path_cov_cfg_edge, 'wb') as g:
                    g.write(f.read(config.BITMAP_COV_CFG_EDGE_SIZE))

                f.seek(config.IVSHMEM_OFFSET_COV_DFG_EDGE)
                with open(self.path_cov_dfg_edge, 'wb') as g:
                    g.write(f.read(config.BITMAP_COV_DFG_EDGE_SIZE))

                f.seek(config.IVSHMEM_OFFSET_COV_ALIAS_INST)
                with open(self.path_cov_alias_inst, 'wb') as g:
                    g.write(f.read(config.BITMAP_COV_ALIAS_INST_SIZE))
