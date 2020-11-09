import os

from pkg import Package

from util import cd, execute

import config


class Package_GCC(Package):

    def __init__(self) -> None:
        super(Package_GCC, self).__init__(
            'gcc', 'gcc',
            os.path.join(config.PROJ_PATH, 'tool', 'gcc')
        )

    def _setup_impl(self, override: bool = False) -> None:
        with cd(self.path_src):
            execute([
                os.path.join('.', 'contrib', 'download_prerequisites'),
            ])

        with cd(self.path_build):
            execute([
                os.path.join(self.path_src, 'configure'),
                '--prefix={}'.format(self.path_store),
                '--enable-languages=c,c++',
                '--enable-shared',
                '--enable-lto',
                '--disable-multilib',
                '--disable-nls',
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
