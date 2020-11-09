from typing import List

import os
import shutil
import struct
import logging

from abc import ABC, abstractmethod

from emu import create_emulator

from util import ascii_encode, prepfn, execute, dump_execute_outputs

import config

FS_SAMPLES = {
    'empty': '000'
}


class FSConfig(ABC):

    def __init__(self, tag: str, size: int) -> None:
        self.tag = tag
        self.size = size


class FSWorker(ABC):

    def __init__(self, name: str, conf: FSConfig) -> None:
        # basic
        self.name = name
        self.conf = conf

        # derived
        self.path_work = os.path.join(config.STUDIO_WORKS, self.name)

    # fs image configs
    @abstractmethod
    def mkfs(self, path: str) -> None:
        raise RuntimeError('Method not implemented')

    @abstractmethod
    def pack_mount(self) -> bytes:
        raise RuntimeError('Method not implemented')

    def _pack_mount_info(
            self, opts: str, main: List[str], deps: List[str], names: List[str]
    ) -> bytes:
        # prepare the package
        data = struct.pack(
            '@64s1024sQQQ',
            ascii_encode(self.name),
            ascii_encode(opts),
            len(main),
            len(deps),
            len(names),
        )

        # pack main
        for d in main:
            data += struct.pack('128s', ascii_encode(d))

        for i in range(config.LINUX_MOD_MAIN_MAX - len(main)):
            data += struct.pack('128s', b'')

        # pack deps
        for d in deps:
            data += struct.pack('128s', ascii_encode(d))

        for i in range(config.LINUX_MOD_DEPS_MAX - len(deps)):
            data += struct.pack('128s', b'')

        # pack names
        for d in names:
            data += struct.pack('128s', ascii_encode(d))

        for i in range(config.LINUX_MOD_MAIN_MAX - len(names)):
            data += struct.pack('128s', b'')

        return data

    # sample creation
    def path_sample(self, sample: str) -> str:
        return os.path.join(
            os.path.join(self.path_work, 'samples'),
            '{}-{}.img'.format(self.conf.tag, sample)
        )

    def _sample_empty_bytecode(self) -> bytes:
        return b''

    def _mk_sample(self, sample: str) -> None:
        # get path
        path = self.path_sample(sample)
        prepfn(path, True)

        # create empty disk
        execute([
            'dd',
            'if=/dev/zero', 'of={}'.format(path),
            'bs=1024', 'count={}'.format(self.conf.size * 1024),
        ])

        # initialize the fs image
        self.mkfs(path)

        # prepare the emulator
        with create_emulator(oneoff=True) as emulator:
            # copy over the image
            shutil.copy2(
                path,
                os.path.join(emulator.session_tmp, config.VIRTEX_DISK_IMG_NAME)
            )

            # prepare the shmem
            with open(emulator.session_shm, 'r+b') as f:
                # seek to the location for machine 0
                f.seek(config.INSTMEM_OFFSET(
                    0
                ) + config.INSTMEM_OFFSET_METADATA)
                f.write(struct.pack(
                    '@c7sQ',
                    ascii_encode('p'),
                    ascii_encode('prep'),
                    0,
                ))

                # mount options
                f.write(self.pack_mount())

                # prep code
                f.write(struct.pack('4s', ascii_encode(FS_SAMPLES[sample])))

                # prep instruction
                if sample == 'empty':
                    bytecode = self._sample_empty_bytecode()

                else:
                    raise RuntimeError('Unknown prepare method')

                f.write(bytecode)

            # launch
            stdout, stderr = emulator.launch()
            dump_execute_outputs(stdout, stderr)

            # check exit status
            with open(emulator.session_shm, 'rb') as f:
                f.seek(config.INSTMEM_OFFSET(
                    0
                ) + config.INSTMEM_OFFSET_METADATA + 8)
                status = struct.unpack('Q', f.read(8))[0]

                if status == 0:
                    logging.error('emulator does not exit correctly')

    def prep(self, override: bool = False) -> None:
        for sample in FS_SAMPLES:
            path = self.path_sample(sample)
            if os.path.exists(path) and not override:
                logging.info('Image {} existed, do nothing'.format(path))
                continue

            self._mk_sample(sample)
