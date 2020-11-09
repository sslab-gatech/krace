import os

from pkg import Package

from util import cd, inplace_replace, execute

import config


class Package_BTRFSPROGS(Package):

    def __init__(self) -> None:
        super(Package_BTRFSPROGS, self).__init__(
            'btrfs-progs', 'btrfs-progs',
            os.path.join(config.PROJ_PATH, 'fs', 'btrfs', 'btrfs-progs')
        )

    def _setup_impl(self, override: bool = False) -> None:
        with cd(self.path_src):
            # TODO: disable installation of udev rules to root fs
            inplace_replace(
                os.path.join('configure.ac'),
                'UDEVDIR="$(${PKG_CONFIG} udev --variable=udevdir)"',
                os.path.join(self.path_store, 'lib', 'udev'),
            )

            execute([
                os.path.join(self.path_src, 'autogen.sh'),
            ])

            execute([
                os.path.join(self.path_src, 'configure'),
                '--prefix={}'.format(self.path_store),
                '--disable-convert',
                '--disable-documentation',
            ])

            # TODO: revert the changes
            inplace_replace(
                os.path.join('configure.ac'),
                os.path.join(self.path_store, 'lib', 'udev'),
                'UDEVDIR="$(${PKG_CONFIG} udev --variable=udevdir)"',
            )

    def _build_impl(self, override: bool = False) -> None:
        with cd(self.path_src):
            execute([
                'make', '-j{}'.format(config.NCPU),
            ])

    def _store_impl(self, override: bool = False) -> None:
        with cd(self.path_src):
            execute([
                'make', 'install',
            ])

            execute([
                'make', 'clean-all', 'clean-gen',
            ])
