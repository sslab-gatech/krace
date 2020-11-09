import os

from pkg import Package

from util import cd, execute

import config


class Package_MUSL(Package):

    def __init__(self) -> None:
        super(Package_MUSL, self).__init__(
            'musl', 'musl',
            os.path.join(config.PROJ_PATH, 'tool', 'musl')
        )

    def _setup_impl(self, override: bool = False) -> None:
        with cd(self.path_build):
            execute([
                os.path.join(self.path_src, 'configure'),
                '--prefix={}'.format(self.path_store),
                '--exec-prefix={}'.format(self.path_store),
                '--syslibdir={}'.format(self.path_store),
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
