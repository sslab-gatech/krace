import os

from pkg import Package

from util import cd, execute

import config


class Package_LLVM(Package):

    def __init__(self) -> None:
        super(Package_LLVM, self).__init__(
            'llvm', 'llvm',
            os.path.join(config.PROJ_PATH, 'tool', 'llvm')
        )

    def _setup_impl(self, override: bool = False) -> None:
        with cd(self.path_build):
            execute([
                'cmake', os.path.join(self.path_src, 'llvm'),
                '-G', 'Unix Makefiles',
                '-DLLVM_ENABLE_PROJECTS={}'.format(';'.join([
                    'clang',
                    'clang-tools-extra',
                    'compiler-rt',
                    'lld',
                    'polly',
                ])),
                '-DCMAKE_INSTALL_PREFIX={}'.format(self.path_store),
                '-DCMAKE_BUILD_TYPE=Release',
                '-DBUILD_SHARED_LIBS=On',
                '-DLLVM_ENABLE_RTTI=On',
                '-DLLVM_ENABLE_EH=On',
                '-DLLVM_ENABLE_THREADS=On',
                '-DLLVM_ENABLE_CXX1Y=On',
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
