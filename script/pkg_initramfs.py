import os
import shutil

from pkg import Package
from pkg_linux import Package_LINUX

from util import cd, prepdn, execute

import config


class Package_INITRAMFS(Package):

    def __init__(self) -> None:
        super(Package_INITRAMFS, self).__init__(
            'initramfs', 'initramfs-{}'.format(config.OPTION().shape),
            os.path.join(config.PROJ_PATH, 'kernel', 'initramfs')
        )
        self.flavor = config.OPTION().flavor
        self.intent = config.OPTION().intent

        linux = Package_LINUX()
        self.linux_build = os.path.join(linux.path_build)
        self.linux_store = os.path.join(linux.path_store)

    def _setup_impl(self, override: bool = False) -> None:
        with cd(self.path_build):
            execute([
                'cmake', os.path.join(self.path_src),
                '-G', 'Unix Makefiles',
                '-DCMAKE_INSTALL_PREFIX={}'.format(self.path_store),
                '-DCMAKE_BUILD_TYPE=Release',
                '-DLINUX_FLAVOR={}'.format(self.flavor),
                '-DLINUX_INTENT={}'.format(self.intent),
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

        # create directory layouts in initramfs
        path_initramfs = os.path.join(self.path_store, 'rootfs')
        prepdn(path_initramfs, override=True)

        path_initramfs_dev = os.path.join(path_initramfs, 'dev')
        path_initramfs_mod = os.path.join(path_initramfs, 'mod')

        os.makedirs(path_initramfs_dev)
        os.makedirs(path_initramfs_mod)

        # copy modules
        path_kernel_lib = os.path.join(self.linux_store, 'lib', 'modules')
        assert len(os.listdir(path_kernel_lib)) == 1
        kernel_version = os.listdir(path_kernel_lib)[0]

        path_mod = os.path.join(path_kernel_lib, kernel_version, 'kernel')
        for item in os.listdir(path_mod):
            shutil.copytree(
                os.path.join(path_mod, item),
                os.path.join(path_initramfs_mod, item)
            )

        # copy init
        shutil.copy2(
            os.path.join(self.path_store, 'bin', 'init'),
            os.path.join(path_initramfs, 'init')
        )

        # make an image
        with cd(path_initramfs):
            os.system(
                'find . | cpio -o --quiet -R 0:0 -H newc | gzip > ../initrd.img'
            )
