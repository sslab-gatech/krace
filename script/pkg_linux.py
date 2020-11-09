from typing import NamedTuple, Dict, List, Set

import re
import os
import shutil

from pkg import Package

from util import cd, execute, execute0, find_all_files

import config


class LinuxIntent(NamedTuple):
    devel: bool
    ktsan: bool
    kasan: bool
    lockdep: bool


LINUX_INTENT_TABLE = {
    'baseline': LinuxIntent(
        devel=False,
        ktsan=False,
        kasan=False,
        lockdep=False,
    ),
    'check-kasan': LinuxIntent(
        devel=False,
        ktsan=False,
        kasan=True,
        lockdep=True,
    ),
    'check-ktsan': LinuxIntent(
        devel=False,
        ktsan=True,
        kasan=False,
        lockdep=False,
    ),
    'dart': LinuxIntent(
        devel=False,
        ktsan=False,
        kasan=True,
        lockdep=True,
    ),
    'dart-dev': LinuxIntent(
        devel=True,
        ktsan=False,
        kasan=True,
        lockdep=True,
    ),
}


class Package_LINUX(Package):

    def __init__(self) -> None:
        super(Package_LINUX, self).__init__(
            'linux', 'linux-{}'.format(config.OPTION().shape),
            os.path.join(config.PROJ_PATH, 'kernel', 'linux')
        )
        self.flavor = config.OPTION().flavor
        self.intent = LINUX_INTENT_TABLE[config.OPTION().intent]
        self.build_option = [
            'ARCH=x86_64',
            'CC={}'.format(os.path.join(config.SCRIPT_PATH, 'cmd_cc.py')),
        ]

    def _on_dev_branch(self) -> bool:
        with cd(self.path_src):
            outs, _ = execute0([
                'git', 'diff', 'origin/master', '--shortstat'
            ])
            return len(outs.strip()) != 0

    def _apply_patches(self) -> None:
        # prepare the linux kernel repo
        with cd(self.path_src):
            execute(['git', 'reset', '--', '.'])
            execute(['git', 'checkout', '--', '.'])
            execute(['git', 'clean', '-fd'])
            execute(['git', 'checkout', config.LINUX_VERSION])

        # apply the ktsan patch (if we choose to use ktsan)
        if self.intent.ktsan:
            patch = os.path.join(self.path_src, '..', 'ktsan.patch')
            with cd(self.path_src):
                execute(['git', 'apply', '-3', patch])

        # apply the racer patch
        patch = os.path.join(self.path_src, '..', 'racer.patch')
        with cd(self.path_src):
            execute(['git', 'apply', '-3', patch])

    def _restore_branch(self) -> None:
        with cd(self.path_src):
            execute(['git', 'reset', '--', '.'])
            execute(['git', 'checkout', '--', '.'])
            execute(['git', 'clean', '-fd'])
            execute(['git', 'checkout', 'master'])

    def _setup_impl(self, override: bool = False) -> None:
        # patch if not building on our own branch
        if not self._on_dev_branch():
            self._apply_patches()

        # standard racer_defconfig
        with cd(self.path_src):
            execute(['make'] + self.build_option + [
                'O={}'.format(self.path_build),
                'racer_defconfig',
            ])

        # qemu-kvm configs
        with cd(self.path_build):
            execute(['make'] + self.build_option + [
                'kvmconfig',
            ])
            execute(['make'] + self.build_option + [
                'qemuconfig',
            ])

        # flavor configs
        with cd(self.path_build):
            execute(['make'] + self.build_option + [
                'racer_{}_config'.format(self.flavor)
            ])

        # checker configs
        with cd(self.path_build):

            if self.intent.ktsan:
                execute(['make'] + self.build_option + [
                    'check_ktsan_config',
                ])

            if self.intent.kasan:
                execute(['make'] + self.build_option + [
                    'check_kasan_config',
                ])

            if self.intent.lockdep:
                execute(['make'] + self.build_option + [
                    'check_lockdep_config',
                ])

        # enable dart
        with cd(self.path_build):
            execute(['make'] + self.build_option + [
                'dart_devel_config' if self.intent.devel else 'dart_config'
            ])

    def _build_impl(self, override: bool = False) -> None:
        with cd(self.path_build):
            execute(['make'] + self.build_option + [
                '-j{}'.format(config.NCPU),
            ])

        # NOTE: clean out of the compilation databases
        for item in find_all_files(
                self.path_build,
                re.compile(r'^racer-compile-database-.*\.pickle$')
        ):
            os.unlink(item)

    def _store_impl(self, override: bool = False) -> None:
        with cd(self.path_build):
            # install headers and modules
            execute([
                'make',
                'INSTALL_HDR_PATH={}'.format(self.path_store),
                'headers_install',
            ])
            execute([
                'make',
                'INSTALL_MOD_PATH={}'.format(self.path_store),
                'modules_install',
            ])

        # install bzImage
        path_bin = os.path.join(self.path_store, 'bin')
        os.makedirs(path_bin, exist_ok=True)

        shutil.copy2(
            os.path.join(self.path_build, 'arch', 'x86_64', 'boot', 'bzImage'),
            os.path.join(path_bin, 'bzImage'),
            follow_symlinks=True
        )

        # done with the kernel repo, revert to master (if not on dev branch)
        if not self._on_dev_branch():
            self._restore_branch()

    def module_order(self, mods: List[str]) -> List[str]:
        # extract module dependencies
        path_lib = os.path.join(self.path_store, 'lib', 'modules')
        assert len(os.listdir(path_lib)) == 1
        version = os.listdir(path_lib)[0]

        deps_info = {}  # type: Dict[str, List[str]]
        path_mdep = os.path.join(path_lib, version, 'modules.dep')
        with open(path_mdep, 'r') as f:
            for line in f:
                line = line.strip()
                toks = line.split(':')
                assert len(toks) == 2
                deps_info[toks[0]] = toks[1].strip().split()

        # construct the correct module loading order
        pend = set()  # type: Set[str]
        for m in mods:
            pend.update(deps_info[m])

        def _r(info: Dict[str, List[str]], hist: List[str], item: str) -> None:
            if item in hist:
                return

            for i in info[item]:
                _r(info, hist, i)

            hist.append(item)

        deps = []  # type: List[str]
        for m in mods:
            for i in deps_info[m]:
                _r(deps_info, deps, i)

        return [i.replace('kernel/', '/mod/') for i in deps]
