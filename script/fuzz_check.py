from typing import Optional

import os
import sys
import logging
import traceback

from queue import Empty
from dataclasses import dataclass
from multiprocessing import Event, Queue, Process

from fuzz_stat import iter_seed_exec_inc, iter_seed_exec_dec
from dart_viz import VizRuntime

from util import disable_interrupt

import config


@dataclass
class ValidatorSync(object):
    event_interrupted: Event  # type: ignore
    queue_seed: Queue
    queue_retv: Queue


class ValidatorWorker(object):

    def __init__(self, iseq: int, sync: ValidatorSync) -> None:
        self.iseq = iseq
        self.sync = sync

    def _analyze(self, base: str) -> Optional[int]:
        runtime = VizRuntime()
        console = os.path.join(base, 'console')
        failure = False

        try:
            runtime.process(os.path.join(base, 'ledger'))
        except Exception as ex:
            failure = True
            with open(os.path.join(console + '-error'), 'w') as t:
                t.write(str(ex))
                t.write('\n-------- EXCEPTION --------\n')
                traceback.print_tb(sys.exc_info()[2], file=t)

        # save the console output
        if failure:
            with open(console, 'w') as t:
                t.write('\n'.join(runtime.records))
            return None

        # save the races
        runtime.dump_races(console + '-racer')

        # return the runtime states
        return len(runtime.races)

    def run(self) -> None:
        while not self.sync.event_interrupted.is_set():  # type: ignore
            # try to get seed
            try:
                path = self.sync.queue_seed.get(timeout=1)
            except Empty:
                continue

            # log start of validation
            sketch, digest, bucket, seqnum = path.split('/')[-4:]
            logging.info('[{}] processing {}-{}-{}-{}'.format(
                self.iseq, sketch, digest, bucket, seqnum
            ))

            # analyze the seed
            result = self._analyze(path)
            if result is None:
                logging.error('[{}] failed'.format(self.iseq))
            elif result != 0:
                logging.warning('[{}] race found: {}'.format(self.iseq, result))

            self.sync.queue_retv.put(result)


class ValidatorMaster(object):

    def __init__(self) -> None:
        self.sync = ValidatorSync(
            event_interrupted=Event(),
            queue_seed=Queue(),
            queue_retv=Queue(),
        )

    def launch(
            self,
            nproc: Optional[int] = None,
            nstep: Optional[int] = None,
            recency: bool = False,
    ) -> None:
        # set params properly
        if nproc is None:
            nproc = min(4, config.NCPU // 8) if nstep is None else 1

        # select iterator
        seed_iterator = iter_seed_exec_dec if recency else iter_seed_exec_inc

        # prepare the seed queue
        count = 0

        # iterate programs in sequence
        for pack in seed_iterator():
            base = pack.path

            # check if we have validated this execution
            path_error = os.path.join(base, 'console-error')
            path_racer = os.path.join(base, 'console-racer')
            if os.path.exists(path_error) or os.path.exists(path_racer):
                continue

            # send the seed to the queue
            self.sync.queue_seed.put(base)
            count += 1

            # early exit if we only need to execute a few things
            if nstep is not None and count == nstep:
                break

        # build the validation processes
        processes = [
            Process(
                target=validation_process,
                args=(i, self.sync)
            )
            for i in range(nproc)
        ]

        # start the fuzzing processes
        for p in processes:
            p.start()

        # wait for the results
        interrupted = False

        try:
            num_retv = 0
            while num_retv != count:
                self.sync.queue_retv.get()
                num_retv += 1

        except KeyboardInterrupt:
            logging.warning('Interrupted')
            interrupted = True

        # exit procedure
        self.sync.event_interrupted.set()  # type: ignore
        for i, p in enumerate(processes):
            if not p.is_alive():
                continue

            if not interrupted:
                p.join(10)
                if not p.is_alive():
                    continue

            logging.warning('killing instance {}'.format(i))
            p.kill()


def validation_process(iseq: int, sync: ValidatorSync) -> None:
    worker = ValidatorWorker(iseq, sync)
    with disable_interrupt():
        worker.run()
