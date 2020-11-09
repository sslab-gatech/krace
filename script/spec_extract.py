from typing import cast, Any, Set, Dict, List, Tuple, Union, Optional

import re
import os
import json

from sortedcontainers import SortedDict  # type: ignore

from pkg_llvm import Package_LLVM
from pkg_musl import Package_MUSL
from pkg_linux import Package_LINUX

from util import cd, prepdn, execute0, envldpaths


class Extractor(object):

    def __init__(self) -> None:
        # find packages
        llvm = Package_LLVM()
        self.clang = os.path.join(llvm.path_store, 'bin', 'clang')
        self.clang_libs = os.path.join(llvm.path_store, 'lib')

        musl = Package_MUSL()
        self.musl_inc = os.path.join(musl.path_store, 'include')
        self.musl_lib = os.path.join(musl.path_store, 'lib')

        linux = Package_LINUX()
        self.build = os.path.join(linux.path_build)

        # load the compilation template
        with open(os.path.join(linux.path_build, 'compile_template.json')) as f:
            self.template = json.load(f)

        # prepare the info directory
        self.path_info = os.path.join(linux.path_store, 'info')

    def _prep(self,
              name: str,
              hdrs: List[str],
              body: Optional[str] = None) -> Tuple[Set[str], Dict[str, str]]:
        # generate a test program
        prep_prog = os.path.join(self.path_info, 'prep-{}.c'.format(name))
        with open(prep_prog, 'w') as f:
            for i in hdrs:
                f.write('#include <{}>\n'.format(i))
            if body is not None:
                f.write(body)

        # try to compile the test program
        with cd(self.build):
            outs, _ = execute0(
                [self.clang] + self.template + [
                    '-dM', '-E', prep_prog
                ]
            )

        # extract the macros
        defs = set()  # type: Set[str]
        vals = {}  # type: Dict[str, str]

        defs_ptn = re.compile(r'^#define\s+(\w+?)\s*$')
        vals_ptn = re.compile(r'^#define\s+(\w+?)\s+(\S.*?)$')
        for line in outs.splitlines():
            line = line.strip()

            m = vals_ptn.match(line)
            if m is not None:
                vals[m.group(1)] = m.group(2)
                continue

            m = defs_ptn.match(line)
            if m is not None:
                defs.add(m.group(1))
                continue

        return defs, vals

    def _dump_macro(self,
                    name: str,
                    hdrs: List[str],
                    fmts: str,
                    macros: List[str],
                    prefix: Optional[str] = None,
                    suffix: Optional[str] = None) -> Dict[str, str]:
        # generate a test program
        dump_prog = os.path.join(self.path_info, 'dump-{}.c'.format(name))
        with open(dump_prog, 'w') as f:
            # includes
            f.write('#include <stdio.h>\n')
            for i in hdrs:
                f.write('#include <{}>\n'.format(i))

            # main start
            f.write('int main(void) {\n')
            if prefix is not None:
                f.write(prefix)

            # dump
            for item in macros:
                f.write('printf("%s : {}\\n", "{}", {});\n'.format(
                    fmts, item, item
                ))

            # main end
            if suffix is not None:
                f.write(suffix)
            f.write('}\n')

        # try to compile the test program
        prog = os.path.join(self.path_info, 'dump-{}'.format(name))

        with cd(self.build):
            outs, _ = execute0(
                [self.clang] + self.template + [
                    '-I', self.musl_inc, '-lc', '-o', prog, dump_prog
                ]
            )

        # try to execute the test program
        outs, _ = execute0([prog])

        # collect the resuls
        rets = {}  # Dict[str, str]
        for line in outs.splitlines():
            toks = line.split(' : ', 1)
            rets[toks[0]] = toks[1]

        return rets

    def _dump_sizes(self,
                    name: str,
                    hdrs: List[str],
                    types: List[Union[str, Tuple[str, str]]],
                    prefix: Optional[str] = None,
                    suffix: Optional[str] = None) -> Dict[str, str]:
        # generate a test program
        dump_prog = os.path.join(self.path_info, 'dump-{}.c'.format(name))
        with open(dump_prog, 'w') as f:
            # includes
            f.write('#include <stdio.h>\n')
            for i in hdrs:
                f.write('#include <{}>\n'.format(i))

            # main start
            f.write('int main(void) {\n')
            if prefix is not None:
                f.write(prefix)

            # dump
            for item in types:
                if isinstance(item, str):
                    expr_name = item
                    expr_size = item

                elif isinstance(item, tuple):
                    expr_name = '{}.{}'.format(item[0], item[1])
                    expr_size = '(({} *)NULL)->{}'.format(item[0], item[1])

                else:
                    raise RuntimeError('Invalid type')

                f.write('printf("{} : %d\\n", sizeof({}));\n'.format(
                    expr_name, expr_size
                ))

            # main end
            if suffix is not None:
                f.write(suffix)
            f.write('}\n')

        # try to compile the test program
        prog = os.path.join(self.path_info, 'dump-{}'.format(name))

        with cd(self.build):
            outs, _ = execute0(
                [self.clang] + self.template + [
                    '-I', self.musl_inc, '-lc', '-o', prog, dump_prog
                ]
            )

        # try to execute the test program
        outs, _ = execute0([prog])

        # collect the resuls
        rets = {}  # Dict[str, str]
        for line in outs.splitlines():
            toks = line.split(' : ', 1)
            rets[toks[0]] = toks[1]

        return rets

    def extract_syscalls(self) -> Dict[str, int]:
        cache = os.path.join(self.path_info, 'syscall.json')

        # load cache
        if os.path.exists(cache):
            with open(cache) as f:
                return cast(Dict[str, int], json.load(f))

        # do extraction
        _, outs = self._prep(
            'syscall', ['asm/unistd.h']
        )
        prep = [
            i for i in outs.keys()
            if i.startswith('__NR_')
        ]

        data = self._dump_macro(
            'syscall', ['asm/unistd.h'], '%lu', prep,
        )
        info = SortedDict()  # type: Dict[str, int]
        for k, v in data.items():
            info[k[len('__NR_'):]] = int(v)

        # save cache
        with open(cache, 'w') as f:
            json.dump(info, f, indent=2)

        return info

    def _extract_flag_open(self) -> Dict[str, int]:
        _, outs = self._prep(
            'flag-open', ['asm/fcntl.h'],
        )
        prep = [
            i for i in outs.keys()
            if i.startswith('O_') or i.startswith('__O_')
        ]

        data = self._dump_macro(
            'flag-open', ['asm/fcntl.h'], '%lu', prep,
        )
        info = SortedDict()  # type: Dict[str, int]
        for k, v in data.items():
            info[k] = int(v)

        return info

    def _extract_flag_mode(self) -> Dict[str, int]:
        _, outs = self._prep(
            'flag-mode', ['linux/stat.h'],
        )
        prep = [
            i for i in outs.keys()
            if i.startswith('S_I') and i[-3:] in ('USR', 'GRP', 'OTH')
        ]

        data = self._dump_macro(
            'flag-mode', ['linux/stat.h'], '%lu', prep,
        )
        info = SortedDict()  # type: Dict[str, int]
        for k, v in data.items():
            info[k] = int(v)

        return info

    def _extract_flag_falloc(self) -> Dict[str, int]:
        _, outs = self._prep(
            'flag-falloc', ['uapi/linux/falloc.h'],
        )
        prep = [
            i for i in outs.keys()
            if i.startswith('FALLOC_FL_')
        ]

        data = self._dump_macro(
            'flag-falloc', ['uapi/linux/falloc.h'], '%lu', prep,
        )
        info = SortedDict()  # type: Dict[str, int]
        for k, v in data.items():
            info[k] = int(v)

        return info

    def _extract_flag_fadvise(self) -> Dict[str, int]:
        _, outs = self._prep(
            'flag-fadvise', ['uapi/linux/fadvise.h'],
        )
        prep = [
            i for i in outs.keys()
            if i.startswith('POSIX_FADV_')
        ]

        data = self._dump_macro(
            'flag-fadvise', ['uapi/linux/fadvise.h'], '%lu', prep,
        )
        info = SortedDict()  # type: Dict[str, int]
        for k, v in data.items():
            info[k] = int(v)

        return info

    def _extract_flag_splice(self) -> Dict[str, int]:
        _, outs = self._prep(
            'flag-splice', ['linux/sched.h', 'linux/splice.h'],
        )
        prep = [
            i for i in outs.keys()
            if i.startswith('SPLICE_F_') and i != 'SPLICE_F_ALL'
        ]

        data = self._dump_macro(
            'flag-splice', ['linux/sched.h', 'linux/splice.h'], '%lu', prep,
        )
        info = SortedDict()  # type: Dict[str, int]
        for k, v in data.items():
            info[k] = int(v)

        return info

    def _extract_flag_sync_file_range(self) -> Dict[str, int]:
        _, outs = self._prep(
            'flag-sync_file_range', ['uapi/linux/fs.h'],
        )
        prep = [
            i for i in outs.keys()
            if i.startswith('SYNC_FILE_RANGE_')
        ]

        data = self._dump_macro(
            'flag-sync_file_range', ['uapi/linux/fs.h'], '%lu', prep,
        )
        info = SortedDict()  # type: Dict[str, int]
        for k, v in data.items():
            info[k] = int(v)

        return info

    def _extract_flag_inode_type(self) -> Dict[str, int]:
        _, outs = self._prep(
            'flag-inode-type', ['linux/stat.h'],
        )
        prep = [
            i for i in outs.keys()
            if i.startswith('S_IF') and i != 'S_IFMT'
        ]

        data = self._dump_macro(
            'flag-inode-type', ['linux/stat.h'], '%lu', prep,
        )
        info = SortedDict()  # type: Dict[str, int]
        for k, v in data.items():
            info[k] = int(v)

        return info

    def _extract_size_base(self) -> Dict[str, int]:
        data = self._dump_sizes(
            'size-base',
            [
                'linux/types.h',
                'linux/stddef.h',
            ],
            [
                'short',
                'unsigned short',
                'int',
                'unsigned int',
                'long',
                'unsigned long',
                'void *',
                'char *',
                'size_t',
                'ssize_t',
                'off_t',
                'mode_t',
                'dev_t',
            ]
        )

        info = SortedDict()  # type: Dict[str, int]
        for k, v in data.items():
            info[k] = int(v)

        return info

    def _extract_size_struct_iovec(self) -> Dict[str, int]:
        data = self._dump_sizes(
            'size-struct-iovec',
            [
                'linux/uio.h',
            ],
            [
                'struct iovec',
                ('struct iovec', 'iov_base'),
                ('struct iovec', 'iov_len'),
            ]
        )

        info = SortedDict()  # type: Dict[str, int]
        for k, v in data.items():
            info[k] = int(v)

        return info

    def _extract_size_struct_stat(self) -> Dict[str, int]:
        data = self._dump_sizes(
            'size-struct-stat',
            [
                'linux/stat.h',
            ],
            [
                'struct stat',
                ('struct stat', 'st_dev'),
                ('struct stat', 'st_ino'),
                ('struct stat', 'st_nlink'),
                ('struct stat', 'st_mode'),
                ('struct stat', 'st_uid'),
                ('struct stat', 'st_gid'),
                ('struct stat', '__pad0'),
                ('struct stat', 'st_rdev'),
                ('struct stat', 'st_size'),
                ('struct stat', 'st_blksize'),
                ('struct stat', 'st_blocks'),
                ('struct stat', 'st_atime'),
                ('struct stat', 'st_atime_nsec'),
                ('struct stat', 'st_mtime'),
                ('struct stat', 'st_mtime_nsec'),
                ('struct stat', 'st_ctime'),
                ('struct stat', 'st_ctime_nsec'),
                ('struct stat', '__unused[0]'),
                ('struct stat', '__unused[1]'),
                ('struct stat', '__unused[2]'),
            ]
        )

        info = SortedDict()  # type: Dict[str, int]
        for k, v in data.items():
            info[k] = int(v)

        return info

    def extract_flags(self) -> Dict[str, Dict[str, Any]]:
        cache = os.path.join(self.path_info, 'flag.json')

        # load cache
        if os.path.exists(cache):
            with open(cache) as f:
                return cast(Dict[str, Dict[str, Any]], json.load(f))

        # do extraction
        info = {
            'open': self._extract_flag_open(),
            'mode': self._extract_flag_mode(),
            'falloc': self._extract_flag_falloc(),
            'fadvise': self._extract_flag_fadvise(),
            'splice': self._extract_flag_splice(),
            'sync_file_range': self._extract_flag_sync_file_range(),
            'inode-type': self._extract_flag_inode_type(),
        }

        # save cache
        with open(cache, 'w') as f:
            json.dump(info, f, indent=2)

        return info

    def extract_sizes(self) -> Dict[str, int]:
        cache = os.path.join(self.path_info, 'size.json')

        # load cache
        if os.path.exists(cache):
            with open(cache) as f:
                return cast(Dict[str, int], json.load(f))

        # do extraction
        info = SortedDict()  # type: Dict[str, int]
        info.update(self._extract_size_base())
        info.update(self._extract_size_struct_iovec())
        info.update(self._extract_size_struct_stat())

        # save cache
        with open(cache, 'w') as f:
            json.dump(info, f, indent=2)

        return info

    def extract(self, override: bool = False) -> None:
        # prepare the info directory
        prepdn(self.path_info, override=override)

        # do extraction
        with envldpaths(self.clang_libs):
            self.extract_syscalls()
            self.extract_flags()
            self.extract_sizes()
