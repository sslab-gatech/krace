from typing import List, Tuple, Optional, Iterator

import os
import uuid
import shutil

from contextlib import contextmanager

from pkg_qemu import Package_QEMU
from pkg_linux import Package_LINUX
from pkg_initramfs import Package_INITRAMFS

from util import execute0, prepdn, touch

import config


class Emulator(object):

    def __init__(self) -> None:
        # qemu
        qemu = Package_QEMU()
        self.path_qemu = os.path.join(
            qemu.path_store, 'bin', 'qemu-system-x86_64'
        )

        # linux
        linux = Package_LINUX()
        self.path_kernel = os.path.join(linux.path_store, 'bin', 'bzImage')

        # initramfs
        initramfs = Package_INITRAMFS()
        self.path_initrd = os.path.join(initramfs.path_store, 'initrd.img')

        # session
        self.session_sid = uuid.uuid4()

        self.session_shm = os.path.join(
            config.VIRTEX_SHM_DIR,
            'racer-ivshmem-{}'.format(config.OPTION().label),
        )

        self.session_tmp = os.path.join(
            config.VIRTEX_TMP_DIR,
            'racer-fsshare-{}'.format(config.OPTION().label),
            self.session_sid.hex
        )

        # arguments
        self.qemu_args_machine = [
            '-enable-kvm',
            '-smp', str(config.VIRTEX_SMP),
            '-m', '{}M'.format(config.VIRTEX_MEM_SIZE),
        ]

        self.qemu_args_ivshmem = [
            '-object', ','.join([
                'memory-backend-file',
                'size={}M'.format(config.IVSHMEM_SIZE // (1 << 20)),
                'share',
                'mem-path={}'.format(self.session_shm),
                'id=ivshmem',
            ]),
            '-device', ','.join([
                'ivshmem-plain',
                'memdev=ivshmem',
            ]),
        ]

        self.qemu_args_fsshare = [
            '-fsdev', ','.join([
                'local',
                'security_model=mapped-file',
                'id=fsdev9p',
                'path={}'.format(self.session_tmp),
            ]),
            '-device', ','.join([
                'virtio-9p-pci',
                'fsdev=fsdev9p',
                'id=fs9p',
                'mount_tag=fsshare',
            ]),
        ]

        self.qemu_args_pvpanic = [
            '-device', 'pvpanic',
            '-no-reboot',
        ]

        self.qemu_args_monitor = [
            '-nographic',
            '-serial', 'mon:stdio',
        ]

        self.boot_args = [
            'console=ttyS0',
            'earlyprintk=ttyS0',
        ]

    @staticmethod
    def _run(qemu_path: str, qemu_args: List[str],
             boot_kernel: str, boot_initrd: str, boot_args: List[str],
             timeout: Optional[int] = None) -> Tuple[str, str]:
        return execute0([
            qemu_path,
            '-kernel', boot_kernel,
            '-initrd', boot_initrd,
            '-append', ' '.join(boot_args),
            *qemu_args,
        ], timeout=timeout, timeout_allowed=True)

    def virtex_set_up(self, oneoff: bool) -> None:
        if oneoff:
            # create the ivshmem shm
            if os.path.exists(self.session_shm):
                os.unlink(self.session_shm)

            touch(self.session_shm, config.IVSHMEM_SIZE)

        # create the fsshare dir
        prepdn(self.session_tmp)
        os.chmod(self.session_tmp, 0o777)

    def virtex_tear_down(self, oneoff: bool) -> None:
        # destroy the ivshmem shm
        if oneoff and os.path.exists(self.session_shm):
            os.unlink(self.session_shm)

        # destroy the fsshare dir
        if os.path.exists(self.session_tmp):
            shutil.rmtree(self.session_tmp)

    def launch(self) -> Tuple[str, str]:
        qemu_args = \
            self.qemu_args_machine + \
            self.qemu_args_ivshmem + \
            self.qemu_args_fsshare + \
            self.qemu_args_pvpanic + \
            self.qemu_args_monitor

        boot_args = self.boot_args

        return Emulator._run(
            self.path_qemu, qemu_args,
            self.path_kernel, self.path_initrd, boot_args,
            timeout=config.VIRTEX_TIMEOUT
        )


@contextmanager
def create_emulator(oneoff: bool = False) -> Iterator[Emulator]:
    emulator = Emulator()
    emulator.virtex_set_up(oneoff)
    try:
        yield emulator
    finally:
        emulator.virtex_tear_down(oneoff)


@contextmanager
def attach_emulator() -> Iterator[Emulator]:
    emulator = Emulator()
    try:
        yield emulator
    finally:
        pass
