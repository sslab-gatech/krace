import os

from pkg import Package

from util import cd, execute

import config


class Package_E2FSPROGS(Package):

    def __init__(self) -> None:
        super(Package_E2FSPROGS, self).__init__(
            'e2fsprogs', 'e2fsprogs',
            os.path.join(config.PROJ_PATH, 'fs', 'ext4', 'e2fsprogs')
        )

    def _setup_impl(self, override: bool = False) -> None:
        with cd(self.path_build):
            execute([
                os.path.join(self.path_src, 'configure'),
                '--prefix={}'.format(self.path_store),
                '--enable-elf-shlibs',
                '--enable-libuuid',
                '--enable-libblkid',
                '--with-udev-rules-dir={}'.format(os.path.join(
                    self.path_store, 'lib', 'udev', 'rules.d'
                )),
                '--with-crond-dir={}'.format(os.path.join(
                    self.path_store, 'etc', 'cron.d'
                )),
                '--with-systemd-unit-dir={}'.format(os.path.join(
                    self.path_store, 'lib', 'systemd', 'system'
                )),
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
