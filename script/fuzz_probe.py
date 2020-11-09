from typing import cast, List, Set, Tuple, Optional

import os
import shutil
import pickle
import logging

from queue import Empty
from dataclasses import dataclass
from multiprocessing import Event, Queue, Process

from fs import FSWorker
from spec_basis import Syscall, Program
from fuzz_exec import FuzzUnit, FuzzExec, Seed, SeedBase

from util import prepdn, mkdir_seq, disable_interrupt, disable_sigterm

import config


class ProbeRuntime(object):

    def __init__(self) -> None:
        self.handle = 0

    def save(self, path: str) -> None:
        with open(path, 'wb') as f:
            pickle.dump(self, f)

    @classmethod
    def load(cls, path: str) -> 'ProbeRuntime':
        with open(path, 'rb') as f:
            return cast(ProbeRuntime, pickle.load(f))


@dataclass
class ProbeSync(object):
    event_interrupted: Event  # type: ignore
    queue_send: Queue
    queue_recv: Queue


class ProbeBase(FuzzUnit):

    def __init__(self, fswork: FSWorker, sample: str) -> None:
        super().__init__(fswork, sample)


class ProbeMaster(ProbeBase):

    def __init__(self, fswork: FSWorker, sample: str, override: bool) -> None:
        super().__init__(fswork, sample)

        # prepare paths
        prepdn(self.wks_base, override=override)
        prepdn(self.wks_temp, override=override)

        for base in SeedBase:
            prepdn(self._path_program(None, base))

        prepdn(self.path_cov)

        # bootstrap the workspace and shmem if there is no runtime states
        if not os.path.exists(self._path_runtime()):
            self._bootstrap()

    # paths
    def _path_runtime(self) -> str:
        return os.path.join(self.wks_base, 'progress')

    def _load_runtime(self) -> ProbeRuntime:
        return ProbeRuntime.load(self._path_runtime())

    def _save_runtime(self, runtime: ProbeRuntime) -> None:
        runtime.save(self._path_runtime())

    # bootstrap
    def _bootstrap(self) -> None:
        # use the bootstrap sequence as seed
        program = Program(config.VIRTEX_THREAD_NUM)
        program.bootstrap(self.spec.precall_sequence())
        self._save_program(None, SeedBase.QUEUE, program)

        # init the persistent states for runtime
        runtime = ProbeRuntime()
        self._save_runtime(runtime)

        # initialize the coverage bitmaps
        self._cov_initialie()

    # transfer of instance states
    def _transfer(self, iseq: int) -> None:
        for base in SeedBase:
            path = self._path_program(iseq, base)
            if not os.path.exists(path):
                continue

            for sketch in os.listdir(path):
                _p1 = os.path.join(path, sketch)
                for digest in os.listdir(_p1):
                    _p2 = os.path.join(_p1, digest)
                    for bucket in os.listdir(_p2):
                        seed = Seed(sketch, digest, int(bucket))

                        # save the program
                        p = self._load_program(iseq, base, seed)
                        spath = self._save_program(None, base, p)

                        # save the results
                        opath = os.path.join(_p2, bucket)
                        for res in os.listdir(opath):
                            if res == 'program':
                                continue

                            rpack = os.path.join(opath, res)

                            # migrate the contents in the result pack
                            rpath = mkdir_seq(spath)
                            for fn in os.listdir(rpack):
                                shutil.copy2(os.path.join(rpack, fn), rpath)

            # done with the migration, remove all
            shutil.rmtree(path)

    # main
    def launch(self, nproc: Optional[int], nstep: Optional[int]) -> None:
        # set params properly
        if nproc is None:
            nproc = (config.NCPU // 2) if nstep is None else 1

        # recover the progress
        self._cov_recover()
        runtime = self._load_runtime()

        # track every workers process
        barrier = set()  # type: Set[int]

        # set the refresh counter
        refresh = config.REFRESH_RATE

        # block sigterm
        disable_sigterm()

        # event: signals an interrupt is reveived (e.g., ctrl + c)
        event_interrupted = Event()

        # queue: queues the seed get requests
        queue_send = Queue()  # type: Queue[Tuple[int, int]]

        # queue: queues the seed put responses
        queue_recv = [Queue() for _ in range(nproc)]  # type: List[Queue[bool]]

        # build the probing processes
        processes = [
            Process(
                target=probing_process,
                args=(
                    self.fswork, self.sample, i, ProbeSync(
                        event_interrupted,
                        queue_send,
                        queue_recv[i],
                    ), runtime.handle
                )
            )
            for i in range(nproc)
        ]

        # start the probing processes
        for p in processes:
            p.start()

        # main loop of the probe master
        while True:

            try:
                # wait for an update from the workers
                try:
                    iseq, sidx = queue_send.get(timeout=1)
                except Empty:
                    # check if any child process is dead
                    dead = 0
                    for p in processes:
                        if not p.is_alive():
                            dead += 1

                    if dead == 0:
                        continue

                    # if unexpected death observed, break the loop
                    event_interrupted.set()
                    logging.warning('unexpected death of worker instances')
                    break

                # barrier on syscall probing advances
                if sidx < 0:
                    barrier.add(iseq)
                    sidx = -(sidx + 1)

                    # release when all have arrived
                    if len(barrier) == nproc:
                        barrier.clear()
                        runtime.handle += 1
                        self._save_runtime(runtime)

                    # if others are still working on this, do not release
                    queue_recv[iseq].put(runtime.handle > sidx)

                    # resume loop immediately
                    continue

                # update probing states (with SIGINT disabled)
                with disable_interrupt():
                    # transfer interesting instances from worker
                    self._transfer(iseq)

                    # resume the worker
                    queue_recv[iseq].put(True)

                # logging
                logging.info('received seed from instance {}'.format(iseq))

                # checkpoint when refresh is needed (checkpoint is IO intensive)
                refresh -= 1
                if refresh == 0:
                    with disable_interrupt():
                        self._cov_checkpoint()
                    refresh = config.REFRESH_RATE

                # abort if we limit the execution by nstep
                if nstep is not None:
                    nstep -= 1
                    if nstep == 0:
                        event_interrupted.set()
                        break

            except KeyboardInterrupt:
                logging.warning('user interrupted, finishing...')
                event_interrupted.set()
                logging.warning('master probing loop finished')
                break

        # on breaking the main loop, checkpoint first
        with disable_interrupt():
            self._cov_checkpoint()

        # exit procedure
        limit = 3
        for i, p in enumerate(processes):
            if not p.is_alive():
                continue

            if limit == 0:
                break

            p.join(10)
            if p.is_alive():
                limit -= 1
                logging.warning('countdown: {} seconds'.format(limit * 10))

        for i, p in enumerate(processes):
            if p.is_alive():
                logging.warning('killing instance {}'.format(i))
                p.kill()


class ProbeWorker(ProbeBase):

    def __init__(
            self, fswork: FSWorker, sample: str, iseq: int, sync: ProbeSync
    ) -> None:
        super().__init__(fswork, sample)
        self.iseq = iseq
        self.sync = sync

        # prepare paths
        prepdn(self._path_instance(self.iseq), True)

        # collect and sort syscalls
        syscalls = []  # type: List[Syscall]
        for group in self.spec.Syscalls:
            for k, v in group.opts.items():
                if v == 0:
                    continue
                syscalls.append(k)

        self.syscalls = sorted(syscalls, key=lambda i: (i.snum, i.name))

        # private logger
        self.logger = logging.getLogger('worker-{}'.format(self.iseq))

        handler = logging.FileHandler(os.path.join(
            self._path_instance(iseq), 'console'
        ))
        handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
        handler.setLevel(logging.DEBUG)

        self.logger.addHandler(handler)
        self.logger.propagate = False

    # steps
    def _prepare(self, sidx: int) -> Program:
        # create the program
        program = Program(config.VIRTEX_THREAD_NUM)
        program.bootstrap(self.spec.precall_sequence())

        if sidx != 0:
            item = self.syscalls[sidx - 1].clone()
            self.logger.info('probing [{} / {}]: {}-{}'.format(
                sidx, len(self.syscalls), item.snum, item.name
            ))

            # ready the syscall
            item.link()
            item.check()

            # add it to the program
            program.add_syscall(item, 0)

        return program

    def _refresh(self, program: Program) -> None:
        program.mod_all_syscalls()

    def _execute(self, program: Program) -> bool:
        # launch
        runner = FuzzExec(self.iseq, self.fswork, self.sample, False)
        result = runner.run(program)

        # save unexpected errors
        if result.error is not None:
            rpath = self._save_result(
                self.iseq, SeedBase.DEBUG, program, result
            )
            logging.critical('unexpected error: {}'.format(rpath))
            return True

        # save crashes
        if result.feedback.has_proper_exit == 0:
            rpath = self._save_result(
                self.iseq, SeedBase.CRASH, program, result
            )
            logging.critical('found a crash: {}'.format(rpath))
            return True

        # save checker signals
        if result.feedback.has_warning_or_error != 0:
            rpath = self._save_result(
                self.iseq, SeedBase.ERROR, program, result
            )
            logging.critical('found a check: {}'.format(rpath))
            return True

        # nothing wired happened, check if this is a new seed
        if result.feedback.cov_cfg_edge_incr != 0 or \
                result.feedback.cov_dfg_edge_incr != 0 or \
                result.feedback.cov_alias_inst_incr != 0:
            self._save_result(
                self.iseq, SeedBase.QUEUE, program, result
            )
            return True

        # nothing interesting found
        return False

    # evolve logic
    def _evolve_rep_loop(self, program: Program) -> bool:
        stall = 0

        while not self.sync.event_interrupted.is_set():  # type: ignore
            useful = self._execute(program)
            if useful:
                return True

            stall += 1
            if stall == config.TTL_REP_LOOP:
                return False

        return False

    def _evolve_mod_loop(self, program: Program) -> bool:
        stall = 0

        while not self.sync.event_interrupted.is_set():  # type: ignore
            useful = self._evolve_rep_loop(program)
            if useful:
                return True

            stall += 1
            if stall == config.TTL_MOD_LOOP:
                return False

            self._refresh(program)

        return False

    def _send_and_wait(self, sidx: int) -> Optional[bool]:
        # send
        self.sync.queue_send.put((self.iseq, sidx))

        # wait
        while not self.sync.event_interrupted.is_set():  # type: ignore
            try:
                return cast(bool, self.sync.queue_recv.get(timeout=1))
            except Empty:
                continue

        # on interrupt received
        return None

    def run(self, base: int) -> None:
        sidx = base

        while not self.sync.event_interrupted.is_set():  # type: ignore
            # termination condition
            if sidx > len(self.syscalls):
                break

            # modify and probe this syscall
            program = self._prepare(sidx)
            while self._evolve_mod_loop(program):
                # notify master on seed discovery (break if interrupted)
                if self._send_and_wait(sidx) is None:
                    break

            # notify master that we are moving forward
            advance = self._send_and_wait(-(sidx + 1))
            if advance is None:
                break

            # master decides whether we should advance to next syscall
            if advance:
                sidx += 1


def probing_process(
        fswork: FSWorker, sample: str, iseq: int, sync: ProbeSync, base: int
) -> None:
    worker = ProbeWorker(fswork, sample, iseq, sync)
    with disable_interrupt():
        worker.run(base)
