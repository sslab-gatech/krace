import os

from fs import FSConfig, FSWorker
from pkg_e2fsprogs import Package_E2FSPROGS

from util import execute, envldpaths


class FSConfig_EXT4(FSConfig):

    def __init__(self, tag: str, size: int) -> None:
        super(FSConfig_EXT4, self).__init__(tag, size)


FS_CONFIGS_EXT4 = {
    '000': FSConfig_EXT4(
        '000', 64
    )
}


class FSWorker_EXT4(FSWorker):

    def __init__(self, conf: FSConfig_EXT4) -> None:
        super(FSWorker_EXT4, self).__init__('ext4', conf)

    def mkfs(self, path: str) -> None:
        progs = Package_E2FSPROGS()

        with envldpaths(os.path.join(progs.path_store, 'lib')):
            execute([
                os.path.join(progs.path_store, 'sbin', 'mkfs.ext4'),
                path,
            ])

    def _get_mount_opts(self) -> str:
        return ''

    def pack_mount(self) -> bytes:
        opts = self._get_mount_opts()
        assert len(opts) + 1 < 1024

        # extract module dependencies
        deps = [
            '/mod/lib/crc16.ko',
            '/mod/fs/mbcache.ko',
        ]
        main = [
            '/mod/fs/jbd2/jbd2.ko',
            '/mod/fs/ext4/ext4.ko',
        ]
        names = [
            'ext4',
            'jbd2',
        ]

        return self._pack_mount_info(opts, main, deps, names)
