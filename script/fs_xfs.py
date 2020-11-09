from typing import List

import os

from fs import FSConfig, FSWorker
from pkg_xfsprogs import Package_XFSPROGS

from util import execute, envldpaths


class FSConfig_XFS(FSConfig):

    def __init__(self, tag: str, size: int) -> None:
        super(FSConfig_XFS, self).__init__(tag, size)


FS_CONFIGS_XFS = {
    '000': FSConfig_XFS(
        '000', 64
    )
}


class FSWorker_XFS(FSWorker):

    def __init__(self, conf: FSConfig_XFS) -> None:
        super(FSWorker_XFS, self).__init__('xfs', conf)

    def mkfs(self, path: str) -> None:
        progs = Package_XFSPROGS()

        with envldpaths(os.path.join(progs.path_store, 'lib')):
            execute([
                os.path.join(progs.path_store, 'sbin', 'mkfs.xfs'),
                path,
            ])

    def _get_mount_opts(self) -> str:
        return ''

    def pack_mount(self) -> bytes:
        opts = self._get_mount_opts()
        assert len(opts) + 1 < 1024

        # extract module dependencies
        deps = []  # type: List[str]
        main = [
            '/mod/fs/xfs/xfs.ko',
        ]
        names = [
            'xfs',
        ]

        return self._pack_mount_info(opts, main, deps, names)
