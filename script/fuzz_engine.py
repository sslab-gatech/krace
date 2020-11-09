from typing import cast, Dict, List, Set, FrozenSet, Tuple, Optional

import os
import json
import shutil
import pickle
import logging

from queue import Empty
from dataclasses import dataclass
from multiprocessing import Event, Queue, Lock, Process

from fs import FSWorker
from spec_basis import Program
from spec_random import SPEC_RANDOM
from fuzz_exec import FuzzUnit, FuzzExec, Seed, SeedBase

from util import prepdn, mkdir_seq, is_error_code, \
    disable_sigterm, disable_interrupt

import config


class GlobalStatus(object):

    def __init__(self) -> None:
        pass

    # merge (happens when we load runtime info from instance)
    def merge(self, other: 'GlobalStatus') -> None:
        pass


class Summary(object):

    def __init__(self) -> None:
        self.primes = set()  # type: Set[Seed]

    # seed addition
    def add(self, seeds: Set[Seed]) -> None:
        self.primes.update(seeds)

    # seed selection
    def pick_for_start(self) -> Seed:
        # TODO (select one seed with cov_cfg_edge_incr > 0 randomly)
        return SPEC_RANDOM.choice(sorted(self.primes))

    def pick_for_merge(self) -> Tuple[Seed, Seed]:
        # TODO (select two seeds with cov_cfg_edge_incr > 0 randomly)
        return self.pick_for_start(), self.pick_for_start()


@dataclass
class SyncPack(object):
    event_interrupted: Event  # type: ignore
    event_resume: Event  # type: ignore
    queue_update: Queue
    queue_seed_get: Queue
    queue_seed_put: Queue
    lock_runtime: Lock  # type: ignore


class FuzzBase(FuzzUnit):

    def __init__(self, fswork: FSWorker, sample: str) -> None:
        super().__init__(fswork, sample)

    # persistent summary
    def _path_summary(self) -> str:
        return os.path.join(self.wks_base, 'summary')

    def _load_summary(self) -> Summary:
        with open(self._path_summary(), 'rb') as f:
            return cast(Summary, pickle.load(f))

    def _save_summary(self, summary: Summary) -> None:
        with open(self._path_summary(), 'wb') as f:
            pickle.dump(summary, f)

    # persistent runtime
    def _path_runtime(self, iseq: Optional[int]) -> str:
        return os.path.join(self._path_instance(iseq), 'runtime')

    def _save_runtime(self, iseq: Optional[int], runtime: GlobalStatus) -> None:
        with open(self._path_runtime(iseq), 'wb') as f:
            pickle.dump(runtime, f)

    def _load_runtime(self, iseq: Optional[int]) -> GlobalStatus:
        with open(self._path_runtime(iseq), 'rb') as f:
            return cast(GlobalStatus, pickle.load(f))

    # helpers
    def run_once(self, iseq: int, seed: Seed, oneshot: bool) -> None:
        program = self._load_program(None, SeedBase.QUEUE, seed)
        runner = FuzzExec(iseq, self.fswork, self.sample, oneshot)
        result = runner.run(program)
        result.dump()


class FuzzMaster(FuzzBase):

    def __init__(self, fswork: FSWorker, sample: str, override: bool) -> None:
        super().__init__(fswork, sample)

        # prepare paths
        prepdn(self.wks_base, override=override)
        prepdn(self.wks_temp, override=override)

        for base in SeedBase:
            prepdn(self._path_program(None, base))

        prepdn(self.path_cov)

        # bootstrap the workspace and shmem if there is no runtime states
        if not os.path.exists(self._path_runtime(None)):
            self._bootstrap()

    def launch(self, nproc: Optional[int], nstep: Optional[int]) -> None:
        # set params properly
        if nproc is None:
            nproc = (config.NCPU // 2) if nstep is None else 1

        # block sigterm
        disable_sigterm()

        # restore execution states
        summary = self._load_summary()
        runtime = self._load_runtime(None)
        self._cov_recover()

        # set the refresh counter
        refresh = config.REFRESH_RATE

        # event: signals an interrupt is received (e.g., ctrl + c)
        event_interrupted = Event()

        # event: resume operation
        event_resumes = [Event() for _ in range(nproc)]

        # queue: queues the runtime status refreshing requests
        queue_update = Queue()  # type: Queue

        # queue: queues the seed get requests
        queue_seed_get = Queue()  # type: Queue

        # queue: queues the seed put responses
        queue_seed_puts = [Queue() for _ in range(nproc)]  # type: List[Queue]

        # lock: protects access to the global runtime
        lock_runtime = Lock()

        # assign a random seed for each of the fuzzer instance
        seeds = [summary.pick_for_start() for _ in range(nproc)]

        # build the fuzzing processes
        processes = [
            Process(
                target=fuzzing_process,
                args=(
                    self.fswork, self.sample, i, SyncPack(
                        event_interrupted,
                        event_resumes[i],
                        queue_update,
                        queue_seed_get,
                        queue_seed_puts[i],
                        lock_runtime,
                    ), seeds[i]
                )
            )
            for i in range(nproc)
        ]

        # start the fuzzing processes
        for p in processes:
            p.start()

        # kickstart every fuzzing instance
        for e in event_resumes:
            e.set()

        # main loop of the fuzz master
        while True:

            try:
                # check if there are pending requests for seeds
                while True:
                    try:
                        iseq = queue_seed_get.get(block=False)
                        queue_seed_puts[iseq].put(summary.pick_for_merge())
                    except Empty:
                        break

                # wait for an update from the workers
                try:
                    iseq = queue_update.get(timeout=1)
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

                # update fuzzing progress/states (with SIGINT disabled)
                with disable_interrupt():
                    runtime.merge(self._load_runtime(iseq))

                    # update the runtime with lock acquired
                    lock_runtime.acquire()
                    self._save_runtime(None, runtime)
                    lock_runtime.release()

                    # transfer interesting instances from worker
                    self._transfer(iseq, summary)
                    self._save_summary(summary)

                    # resume the worker instance
                    event_resumes[iseq].set()

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
                logging.warning('master fuzzing loop finished')
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

    def _bootstrap(self) -> None:
        # use the bootstrap sequence as seed
        program = Program(config.VIRTEX_THREAD_NUM)
        program.bootstrap(self.spec.precall_sequence())
        path = self._save_program(None, SeedBase.PRIME, program)

        sketch, digest = program.summary()
        seed = Seed(sketch, digest, int(os.path.basename(path)))

        # init the persistent states for runtime
        runtime = GlobalStatus()
        self._save_runtime(None, runtime)

        # init the persistent states for summary
        summary = Summary()
        summary.add({seed})

        # NOTE: both cov metrics are set to 1 purposely
        self._save_summary(summary)

        # initialize the coverage bitmaps
        self._cov_initialie()

    # extract primitives
    def _extract_primitives(self, prog: Program, path: str) -> Set[Seed]:
        # get return values
        with open(os.path.join(path, 'outcome')) as t:
            retv = json.load(t)['subs']

        # check pairings thread by thread
        assert len(prog.thread_subs) == len(retv)
        for p_sub, r_sub in zip(prog.thread_subs, retv):
            assert len(p_sub) == len(r_sub)

        # map retv to syscalls
        linear = {}  # type: Dict[int, int]
        for i in range(prog.syscalls_start, len(prog.syscalls)):
            syscall = prog.syscalls[i]
            isub, isys = prog.syscall_index(syscall)
            linear[i] = retv[isub][isys]

        # deps and rdeps relationship
        circles = set()  # type: Set[FrozenSet[int]]
        for i in range(prog.syscalls_start, len(prog.syscalls)):
            # ignore failed syscalls
            if is_error_code(linear[i]):
                continue

            syscall = prog.syscalls[i]
            deps = syscall.rely(prog)

            # all its deps must not fail as well
            passed = True
            for d in deps:
                if d >= prog.syscalls_start and is_error_code(linear[d]):
                    passed = False
                    break

            if not passed:
                continue

            # construct the circle
            merged = {i}

            expire = set()  # type: Set[FrozenSet[int]]
            for c in circles:
                if len(c.intersection(deps)) != 0:
                    merged.update(c)
                    expire.add(c)

            for c in expire:
                circles.remove(c)

            circles.add(frozenset(merged))

        # extraction loop
        seeds = set()  # type: Set[Seed]
        for c in circles:
            spath = os.path.dirname(path)
            with open(os.path.join(spath, 'program'), 'rb') as f:
                instance = cast(Program, pickle.load(f))

            o = 0
            for i in range(prog.syscalls_start, len(prog.syscalls)):
                if i not in c:
                    instance.del_syscall(i - o)
                    o += 1

            # save the primitive
            ppath = self._save_program(None, SeedBase.PRIME, instance)

            sketch, digest = instance.summary()
            seeds.add(Seed(sketch, digest, int(os.path.basename(ppath))))

        return seeds

    # transfer of instance states
    def _transfer(self, iseq: int, summary: Summary) -> None:
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

                            # extract primitives
                            summary.add(self._extract_primitives(p, rpack))

                            # migrate the contents in the result pack
                            rpath = mkdir_seq(spath)
                            for fn in os.listdir(rpack):
                                shutil.copy2(os.path.join(rpack, fn), rpath)

            # done with the migration, remove all
            shutil.rmtree(path)


class FuzzWorker(FuzzBase):

    def __init__(
            self, fswork: FSWorker, sample: str, iseq: int, sync: SyncPack
    ) -> None:
        super().__init__(fswork, sample)
        self.iseq = iseq
        self.sync = sync

        # prep
        path_private = self._path_instance(iseq)
        prepdn(path_private)

        # private logger
        self.logger = logging.getLogger('worker-{}'.format(self.iseq))

        handler = logging.FileHandler(os.path.join(path_private, 'console'))
        handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
        handler.setLevel(logging.DEBUG)

        self.logger.addHandler(handler)
        self.logger.propagate = False

    def run(self, seed: Seed) -> None:
        logging.debug('instance {} started'.format(self.iseq))

        # re-seed rng for this fuzzing instance
        SPEC_RANDOM.seed()

        # load the seed
        program = self._load_program(None, SeedBase.PRIME, seed)

        # initial sync
        runtime = self._sync()

        # if interrupted, return immediately
        if runtime is None:
            return

        # main worker loop
        self._evolve(runtime, program)

    def _sync(self) -> Optional[GlobalStatus]:
        while not self.sync.event_interrupted.is_set():  # type: ignore
            # wait for resumption
            if not self.sync.event_resume.wait(timeout=10):  # type: ignore
                continue

            # if we got the event, clear it first
            self.sync.event_resume.clear()  # type: ignore

            # take the latest runtime
            self.sync.lock_runtime.acquire()  # type: ignore
            runtime = self._load_runtime(None)
            self.sync.lock_runtime.release()  # type: ignore

            return runtime

        return None

    def _report(self, runtime: GlobalStatus) -> Optional[GlobalStatus]:
        # save the updated runtime after finding a new seed
        self._save_runtime(self.iseq, runtime)

        # inform the master
        self.sync.queue_update.put(self.iseq)

        # sync the latest runtime back
        return self._sync()

    def _evolve_rep_loop(
            self, runtime: GlobalStatus, program: Program
    ) -> bool:
        useful = False
        epoch = 0
        stall = 0

        while not self.sync.event_interrupted.is_set():  # type: ignore
            # log event
            self.logger.info('\t\trep {} - {}'.format(epoch, stall))
            epoch += 1

            # execute
            runner = FuzzExec(
                self.iseq, self.fswork, self.sample, False,
                staging=self._path_instance(self.iseq), staging_check=False
            )
            result = runner.run(program)

            # save unexpected errors
            check = False

            if result.error is not None:
                rpath = self._save_result(
                    self.iseq, SeedBase.DEBUG, program, result
                )
                logging.critical('unexpected error: {}'.format(rpath))
                self.logger.info('\t\t\t[x] exception')

                check = True
                useful = True

            # save crashes
            elif result.feedback.has_proper_exit == 0:
                rpath = self._save_result(
                    self.iseq, SeedBase.CRASH, program, result
                )
                logging.critical('found a crash: {}'.format(rpath))
                self.logger.info('\t\t\t[*] crash')

                check = True
                useful = True

            # save checker signals
            elif result.feedback.has_warning_or_error != 0:
                rpath = self._save_result(
                    self.iseq, SeedBase.ERROR, program, result
                )
                logging.critical('found a check: {}'.format(rpath))
                self.logger.info('\t\t\t[*] check')

                check = True
                useful = True

            # nothing wired happened, check if this is a new seed
            elif result.feedback.cov_cfg_edge_incr != 0 or \
                    result.feedback.cov_dfg_edge_incr != 0 or \
                    result.feedback.cov_alias_inst_incr != 0:
                rpath = self._save_result(
                    self.iseq, SeedBase.QUEUE, program, result
                )
                self.logger.info('\t\t\t[^] seed')

                stall = 0  # give it a few more trials
                useful = True

            # nothing interesting, stalled
            else:
                stall += 1
                self.logger.info('\t\t\t[-] covered')

                if stall == config.TTL_REP_LOOP:
                    break

                # nothing else to do
                continue

            # break the loop if there is any errors raised
            if check:
                break

            # upon reaching here, rpath cannot be None
            assert rpath is not None
            shutil.move(
                os.path.join(self._path_instance(self.iseq), 'ledger'),
                os.path.join(rpath, 'ledger')
            )

        # inform upper level on whether this loop is useful
        return useful

    def _evolve_mod_loop(
            self, runtime: GlobalStatus, program: Program, skip: bool
    ) -> bool:
        useful = False
        epoch = 0
        stall = 0

        while not self.sync.event_interrupted.is_set():  # type: ignore
            # log event
            self.logger.info('\tmod {} - {}'.format(epoch, stall))
            epoch += 1

            # execute
            if skip:
                skip = False
            else:
                # nothing to mutate for the initial seed
                if program.num_syscall() == 0:
                    break

                program.mod_syscall(None)

            # inner loop
            inner = self._evolve_rep_loop(runtime, program)

            # if anything useful happened, inform the master
            if inner:
                package = self._report(runtime)
                if package is None:
                    # master requested stop, break loop
                    break
                runtime = package

                useful = True
                stall = 0  # give it a few more trials
                continue

            # stalled
            stall += 1
            if stall == config.TTL_MOD_LOOP:
                break

        # inform upper level on whether this loop is useful
        return useful

    def _evolve_ext_loop(
            self, runtime: GlobalStatus, program: Program, skip: bool
    ) -> bool:
        useful = False
        epoch = 0
        stall = 0

        while not self.sync.event_interrupted.is_set():  # type: ignore
            # log event
            self.logger.info('ext {} - {}'.format(epoch, stall))
            epoch += 1

            # execute
            if skip:
                skip = False
            else:
                # try syscall addition / deletion
                if epoch % 2 == 0:
                    program.add_syscall(self.spec.syscall_generate())
                else:
                    program.del_syscall(None)

            # inner loop
            inner = self._evolve_mod_loop(runtime, program, True)
            if inner:
                useful = True
                stall = 0  # give it a few more trials
                continue

            # stalled
            stall += 1
            if stall == config.TTL_EXT_LOOP:
                break

        # inform upper level on whether this ext_loop is useful
        return useful

    def _evolve_merge_loop(
            self, runtime: GlobalStatus, seed1: Seed, seed2: Seed
    ) -> Program:
        program = self._load_program(None, SeedBase.PRIME, seed1)
        another = self._load_program(None, SeedBase.PRIME, seed2)
        program.merge(another)
        return program

    def _evolve(self, runtime: GlobalStatus, program: Program) -> None:
        while not self.sync.event_interrupted.is_set():  # type: ignore
            self._evolve_ext_loop(runtime, program, True)

            # on exit of the ext_loop, we start to combined seeds
            self.sync.queue_seed_get.put(self.iseq)
            while not self.sync.event_interrupted.is_set():  # type: ignore
                # wait for the master to distribute the seed pair
                try:
                    seed1, seed2 = self.sync.queue_seed_put.get(timeout=1)
                except Empty:
                    continue

                # start to merging the seeds
                program = self._evolve_merge_loop(runtime, seed1, seed2)
                break


def fuzzing_process(
        fswork: FSWorker, sample: str, iseq: int, sync: SyncPack, seed: Seed
) -> None:
    worker = FuzzWorker(fswork, sample, iseq, sync)
    with disable_interrupt():
        worker.run(seed)
