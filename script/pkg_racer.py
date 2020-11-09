import os

from pkg import Package

from util import cd, execute

import config


class Package_Racer(Package):

    def __init__(self) -> None:
        super(Package_Racer, self).__init__(
            'racer', 'racer',
            os.path.join(config.PROJ_PATH, 'pass')
        )

    def _setup_impl(self, override: bool = False) -> None:
        with cd(self.path_build):
            execute([
                'cmake', os.path.join(self.path_src),
                '-G', 'Unix Makefiles',
                '-DCMAKE_INSTALL_PREFIX={}'.format(self.path_store),
                '-DCMAKE_BUILD_TYPE=Release',
                self.path_src,
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
