import os

from fs import FSConfig, FSWorker

from pkg_linux import Package_LINUX
from pkg_btrfsprogs import Package_BTRFSPROGS

from util import execute, envldpaths


class FSConfig_BTRFS(FSConfig):

    def __init__(self, tag: str, size: int) -> None:
        super(FSConfig_BTRFS, self).__init__(tag, size)


FS_CONFIGS_BTRFS = {
    '000': FSConfig_BTRFS(
        '000', 128
    )
}


class FSWorker_BTRFS(FSWorker):

    def __init__(self, conf: FSConfig_BTRFS) -> None:
        super(FSWorker_BTRFS, self).__init__('btrfs', conf)

    def mkfs(self, path: str) -> None:
        progs = Package_BTRFSPROGS()

        with envldpaths(os.path.join(progs.path_store, 'lib')):
            execute([
                os.path.join(progs.path_store, 'bin', 'mkfs.btrfs'),
                path,
            ])

    def _get_mount_opts(self) -> str:
        return 'autodefrag,check_int,check_int_data,compress'

    def pack_mount(self) -> bytes:
        opts = self._get_mount_opts()
        assert len(opts) + 1 < 1024

        # extract module dependencies
        deps = Package_LINUX().module_order(['kernel/fs/btrfs/btrfs.ko'])
        main = [
            '/mod/fs/btrfs/btrfs.ko'
        ]
        names = [
            'btrfs'
        ]

        return self._pack_mount_info(opts, main, deps, names)
