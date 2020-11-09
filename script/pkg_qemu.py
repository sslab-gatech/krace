import os

from pkg import Package

from util import cd, execute

import config


class Package_QEMU(Package):

    def __init__(self) -> None:
        super(Package_QEMU, self).__init__(
            'qemu', 'qemu',
            os.path.join(config.PROJ_PATH, 'tool', 'qemu')
        )

    def _setup_impl(self, override: bool = False) -> None:
        with cd(self.path_build):
            execute([
                os.path.join(self.path_src, 'configure'),
                '--prefix={}'.format(self.path_store),
                '--enable-kvm',
                '--enable-virtfs',
                '--target-list=x86_64-softmmu',
            ])

    def _build_impl(self, override: bool = False) -> None:
        with cd(self.path_build):
            execute([
                'make', '-j{}'.format(config.NCPU),
            ])

    def _store_impl(self, override: bool = False) -> None:
        with cd(self.path_build):
            execute([
                'make', 'install',
            ])
