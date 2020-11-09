import os

from pkg import Package

from util import cd, execute

import config


class Package_XFSPROGS(Package):

    def __init__(self) -> None:
        super(Package_XFSPROGS, self).__init__(
            'xfsprogs', 'xfsprogs',
            os.path.join(config.PROJ_PATH, 'fs', 'xfs', 'xfsprogs')
        )

    def _setup_impl(self, override: bool = False) -> None:
        with cd(self.path_src):
            execute([
                'make', 'configure',
            ])

            execute([
                os.path.join(self.path_src, 'configure'),
                '--prefix={}'.format(self.path_store),
                '--with-crond-dir={}'.format(os.path.join(
                    self.path_store, 'etc', 'cron.d'
                )),
                '--with-systemd-unit-dir={}'.format(os.path.join(
                    self.path_store, 'lib', 'systemd', 'system'
                )),
            ])

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
                'make', 'install-dev',
            ])

            execute([
                'make', 'clean',
            ])
