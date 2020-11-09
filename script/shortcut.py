#!/usr/bin/env python3

from typing import List

import sys

from argparse import ArgumentParser

from util import cd, execute, ensure

import config

DEF_INTENT_DEVELOP = 'dart-dev'
DEF_INTENT_RELEASE = 'dart-dev'


# utils
def _clean_build(flavor: str, intent: str) -> None:
    with cd(config.PROJ_PATH):
        execute(['make', 'build-racer', 'EXTRA=-ccc'])
        execute(['make', 'build-linux', 'EXTRA=-ccc',
                 'F={}'.format(flavor), 'I={}'.format(intent)])
        execute(['make', 'build-initramfs', 'EXTRA=-ccc',
                 'F={}'.format(flavor), 'I={}'.format(intent)])
        execute(['make', 'spec-extract',
                 'F={}'.format(flavor), 'I={}'.format(intent)])
        execute(['make', 'spec-compose',
                 'F={}'.format(flavor), 'I={}'.format(intent)])


def _incremental_build(flavor: str, intent: str) -> None:
    with cd(config.PROJ_PATH):
        execute(['make', 'build-linux', 'EXTRA=-cc',
                 'F={}'.format(flavor), 'I={}'.format(intent)])
        execute(['make', 'build-initramfs', 'EXTRA=-ccc',
                 'F={}'.format(flavor), 'I={}'.format(intent)])


def _ready(flavor: str, intent: str, build: bool, clean: bool) -> None:
    if build:
        _incremental_build(flavor, intent)

    if clean:
        _clean_build(flavor, intent)


def _process(cmd: List[str], extra: List[str], value: List[str]) -> None:
    if len(extra) != 0:
        cmd.append('EXTRA={}'.format(' '.join(extra)))

    if len(value) != 0:
        cmd.append('VALUE={}'.format(' '.join(value)))

    execute(cmd)


def run_test(
        flavor: str, intent: str = DEF_INTENT_DEVELOP,
        build: bool = False, clean: bool = False,
        trial: bool = True, reset: bool = True
) -> None:
    _ready(flavor, intent, build, clean)

    with cd(config.PROJ_PATH):
        cmds = [
            'make', 'exec-test',
            'F={}'.format(flavor), 'I={}'.format(intent)
        ]
        extra = []  # type: List[str]
        value = []  # type: List[str]

        if reset:
            extra.append('-ccc')

        if trial:
            test = list(extra)
            test.extend(['-s', 'PLAIN', '-n', '1'])
            _process(cmds, test, value)

            if not ensure('Continue exec-test without limit?'):
                return

        # long running
        _process(cmds, extra, value)


def run_work(
        flavor: str, intent: str = DEF_INTENT_DEVELOP,
        build: bool = False, clean: bool = False,
        trial: bool = True, reset: bool = True
) -> None:
    _ready(flavor, intent, build, clean)

    with cd(config.PROJ_PATH):
        cmds = [
            'make', 'fuzz-validate',
            'F={}'.format(flavor), 'I={}'.format(intent)
        ]
        extra = []  # type: List[str]
        value = []  # type: List[str]

        if reset:
            extra.append('-ccc')

        if trial:
            test = list(value)
            test.extend(['-s', '1'])
            _process(cmds, extra, test)

            if not ensure('Continue fuzz-validate without limit?'):
                return

        # long running
        _process(cmds, extra, value)


def run_prep(
        flavor: str, intent: str = DEF_INTENT_RELEASE,
        build: bool = False, clean: bool = False,
        trial: bool = True, reset: bool = True
) -> None:
    _ready(flavor, intent, build, clean)

    with cd(config.PROJ_PATH):
        cmds = [
            'make', 'fuzz-probe',
            'F={}'.format(flavor), 'I={}'.format(intent)
        ]
        extra = []  # type: List[str]
        value = []  # type: List[str]

        if reset:
            extra.append('-ccc')

        if trial:
            test = list(value)
            test.extend(['-s', '1'])
            _process(cmds, extra, test)

            if not ensure('Continue fuzz-probe without limit?'):
                return

        # long running
        _process(cmds, extra, value)


def run_fuzz(
        flavor: str, intent: str = DEF_INTENT_RELEASE,
        build: bool = False, clean: bool = False,
        trial: bool = True, reset: bool = True
) -> None:
    _ready(flavor, intent, build, clean)

    with cd(config.PROJ_PATH):
        cmds = [
            'make', 'fuzz-launch',
            'F={}'.format(flavor), 'I={}'.format(intent)
        ]
        extra = []  # type: List[str]
        value = []  # type: List[str]

        if reset:
            extra.append('-ccc')

        if trial:
            test = list(value)
            test.extend(['-s', '1'])
            _process(cmds, extra, test)

            if not ensure('Continue fuzz-launch without limit?'):
                return

        # long running
        _process(cmds, extra, value)


def main(argv: List[str]) -> int:
    # setup argument parser
    parser = ArgumentParser()

    parser.add_argument('action', choices=('test', 'work', 'prep', 'fuzz'))
    parser.add_argument('flavor', choices=('ext4', 'btrfs', 'xfs'))

    parser.add_argument('-b', '--build', action='store_true')
    parser.add_argument('-c', '--clean', action='store_true')
    parser.add_argument('-T', '--no-trial', action='store_true')
    parser.add_argument('-R', '--no-reset', action='store_true')

    # parse
    args = parser.parse_args(argv)

    if args.action == 'test':
        run_test(args.flavor,
                 build=args.build, clean=args.clean,
                 trial=(not args.no_trial), reset=(not args.no_reset))

    elif args.action == 'work':
        run_work(args.flavor,
                 build=args.build, clean=args.clean,
                 trial=(not args.no_trial), reset=(not args.no_reset))

    elif args.action == 'prep':
        run_prep(args.flavor,
                 build=args.build, clean=args.clean,
                 trial=(not args.no_trial), reset=(not args.no_reset))

    elif args.action == 'fuzz':
        run_fuzz(args.flavor,
                 build=args.build, clean=args.clean,
                 trial=(not args.no_trial), reset=(not args.no_reset))

    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
