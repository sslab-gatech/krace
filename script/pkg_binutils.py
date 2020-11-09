import os

from pkg import Package

from util import cd, execute

import config


class Package_BINUTILS(Package):

    def __init__(self) -> None:
        super(Package_BINUTILS, self).__init__(
            'binutils', 'binutils',
            os.path.join(config.PROJ_PATH, 'tool', 'binutils')
        )

    def _setup_impl(self, override: bool = False) -> None:
        with cd(self.path_build):
            execute([
                os.path.join(self.path_src, 'configure'),
                '--prefix={}'.format(self.path_store),
                '--enable-ld=yes',
                '--disable-gdb',
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
