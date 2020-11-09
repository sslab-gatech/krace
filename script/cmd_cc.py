#!/usr/bin/env python3

from typing import cast, Any, List, Dict, Optional

import os
import sys
import json
import fcntl
import subprocess

from collections import OrderedDict

from cmd import Parser_CC
from pkg_llvm import Package_LLVM
from pkg_racer import Package_Racer

from util import envldpaths

import config


def _clang() -> List[str]:
    return [os.path.join(Package_LLVM().path_store, 'bin', 'clang')]


def _clang_wrap(mode: str, output: str) -> List[str]:
    racer = Package_Racer()

    path_racer_instrument = os.path.join(
        racer.path_store, 'lib', 'libRacerInstrument.so'
    )

    path_racer_profile = os.path.join(
        racer.path_src, 'profile', 'linux.json'
    )

    return _clang() + [
        # KASAN, KTSAN needs this
        '-fno-experimental-new-pass-manager',
        # preserve code structures to the maximum degree
        '-fno-inline', '-fno-inline-functions',
        # instrument dart code
        '-Xclang', '-load', '-Xclang', path_racer_instrument,
        '-mllvm', '-racer-mode', '-mllvm', mode,
        '-mllvm', '-racer-input', '-mllvm', path_racer_profile,
        '-mllvm', '-racer-output', '-mllvm', output,
    ]


def main(argv: List[str]) -> int:
    cc = Parser_CC()

    # parse clang argument
    args = cc.parse(argv)

    # filter non-compilations
    src = None  # type: Optional[str]
    hook = True
    mode = 'normal'

    if not args.c:
        hook = False

    elif args.o is None:
        hook = False

    elif len(args.inputs) != 1 or args.inputs[0] in ['-', '/dev/null']:
        hook = False

    elif '__ASSEMBLY__' in args.D:
        hook = False

    elif '__KERNEL__' not in args.D:
        hook = False

    # filter based on source code location
    if hook:
        src = cast(str, args.inputs[0])

        base = os.path.join(config.PROJ_PATH, 'kernel', 'linux') + '/'
        if src.startswith(base):
            src = src[len(base):]
        else:
            assert not src.startswith('/')

        # whitelist approach, hook nothing by default
        hook = False

        # hook fs/
        if src.startswith('fs/'):
            hook = True
            name = src.split('/', 1)[1]

            # ignore utility filesystems
            if name in {
                '9p', 'devpts', 'ramfs',
                'proc', 'debugfs', 'tracefs', 'exportfs',
            }:
                mode = 'ignore'

            # blacklist btrfs/locking.c, all races there are benign
            if name in {
                'btrfs/locking.c'
            }:
                hook = False

        # hook block/
        elif src.startswith('block/'):
            hook = True

        # hook drivers/block/loop
        elif src == 'drivers/block/loop.c':
            hook = True

        # hook mm/<filesystem related code>
        elif src.startswith('mm/'):
            name = src.split('/')[1]
            if name in {
                'filemap.c', 'fadvise.c',
                'backing-dev.c', 'page-writeback.c', 'readahead.c',
            }:
                hook = True

            elif name == 'kasan':
                hook = True
                mode = 'ignore'

        # hook lib/ selectively
        elif src.startswith('lib/'):
            name = src.split('/')[1]
            if name in {
                'radix-tree.c', 'xarray.c'
            }:
                hook = True
                mode = 'ignore'

    if src is not None:
        # build spec compilation template
        if src == 'scripts/mod/empty.c':
            spec_args = list(argv)
            assert spec_args[-1] == args.inputs[0]
            assert spec_args[-2] == args.o
            assert spec_args[-3] == '-o'
            assert spec_args[-4] == '-c'
            spec_args = spec_args[:-4]

            with open('compile_template.json', 'w') as f:
                json.dump(spec_args, f, indent=2)

        # build dart compilation database
        if src.startswith('lib/dart/'):
            path_dart = os.path.join(config.PASS_PATH, 'dart')

            # load existing compile db
            path_compile_db = os.path.join(path_dart, 'compile_commands.json')
            if not os.path.exists(path_compile_db):
                compile_db = []  # type: List[Dict[str, Any]]
            else:
                with open(path_compile_db, 'r') as f:
                    fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                    compile_db = json.load(f)
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)

            # use the actual source file instead of the kernel symlink
            dart_file = os.path.join(path_dart, src[len('lib/dart/'):])

            dart_args = list(argv)
            assert dart_args[-1] == args.inputs[0]
            dart_args[-1] = dart_file

            # construct the record
            record = OrderedDict()  # type: Dict[str, Any]
            record['directory'] = os.getcwd()
            record['file'] = dart_file
            record['arguments'] = _clang() + dart_args
            record['output'] = args.o

            # either override the record or append the report
            found = False
            for i, v in enumerate(compile_db):
                if v['output'] == record['output']:
                    compile_db[i] = record
                    found = True
                    break

            if not found:
                compile_db.append(record)

            # write back the compile db
            with open(path_compile_db, 'w') as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                json.dump(compile_db, f, indent=2)
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    # execute the actual clang command
    llvm = _clang_wrap(mode, args.o + '.racer') if hook else _clang()

    libs = os.path.join(Package_LLVM().path_store, 'lib')
    with envldpaths(libs):
        return subprocess.run(llvm + argv).returncode


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
