from typing import Dict, List, Tuple, Optional

import os
import sys
import logging
import asciitree  # type: ignore

from termcolor import colored
from argparse import ArgumentParser

from util import enable_coloring_in_logging, cd, execute, execute0, ensure

import config


class Snapshot(object):

    def __init__(self, ctxt: str, path: str, repo: str, item: str) -> None:
        # basics
        self.ctxt = ctxt
        self.path = path
        self.repo = repo
        self.item = item

        # derived
        self.tag = '{}:{}'.format(self.repo, self.item)

        # queried
        self.image = self._query_image()
        self.machine = self._query_machine()

    def _query_image(self) -> Optional[str]:
        outs, _ = execute0([
            'docker', 'images',
            '--all',
            '--filter', 'reference={}'.format(self.tag),
            '--quiet',
        ])

        lines = outs.strip().splitlines()
        if len(lines) == 0:
            return None

        if len(lines) == 1:
            return lines[0]

        raise RuntimeError(
            '[docker] more than one images exist for tag {}: {}'.format(
                self.tag, ' '.join(lines)
            )
        )

    def _query_machine(self) -> Optional[str]:
        if self.image is None:
            return None

        result = None

        # collect running containers with image as the ancestor
        outs, _ = execute0([
            'docker', 'ps',
            '--all',
            '--filter', 'ancestor={}'.format(self.image),
            '--format', '{{.ID}}:{{.Image}}:{{.Status}}',
        ])

        lines = outs.strip().splitlines()
        for line in lines:
            machine, image, status = line.split(':')

            if image != self.image:
                continue

            if result is not None:
                raise RuntimeError(
                    '[docker] multiple machines exist for image {}: {}'.format(
                        self.image, ' '.join(lines)
                    )
                )

            status = status.strip()
            if not status.startswith('Up '):
                if ensure(
                        '[docker]',
                        'Invalid machine status: {},'.format(status),
                        'reset the machine is needed.',
                        'Continue?'
                ):
                    execute([
                        'docker', 'rm',
                        '--force',
                        machine,
                    ])
                    return self._query_machine()

                else:
                    raise RuntimeError(
                        '[docker] invalid machine status: {} ({}): {}'.format(
                            machine, self.tag, status
                        )
                    )

            result = machine

        return result

    def _query_users(self) -> int:
        if self.machine is None:
            return 0

        outs, _ = execute0([
            'docker', 'top',
            self.machine,
            '--format', 'pid,tty=',
        ])

        lines = outs.strip().splitlines()
        if len(lines) < 2 or lines[0] != 'PID':
            raise RuntimeError(
                '[docker] invalid user query for machine {} ({}): {}'.format(
                    self.machine, self.tag, outs
                )
            )

        return len(lines) - 2

    def build(self) -> bool:
        """
        Build the image, may opt for incremental build or clean build
        """

        # decide how to build image if image already exists
        if self.image is not None:
            if ensure(
                    '[docker]',
                    'image {} exists,'.format(self.image),
                    'force build (fresh) will clean the image.',
                    'Continue?'
            ):
                if not self.clean():
                    logging.error('[docker] build: halted - clean failed')
                    return False

            elif ensure(
                    '[docker]',
                    'image {} exists,'.format(self.image),
                    'force build (incremental) will reset the image.',
                    'Continue?'
            ):
                if not self.reset():
                    logging.error('[docker] build: halted - reset failed')
                    return False

            else:
                logging.error('[docker] build: ignored - image exists')
                return False

        # always build from ctxt directory
        with cd(self.ctxt):
            execute([
                'docker', 'build',
                '--file', os.path.join(self.path, self.item, 'Dockerfile'),
                '--tag', '{}'.format(self.tag),
                '--progress', 'plain',
                '.',
            ])

        # make sure the image is created
        self.image = self._query_image()
        if self.image is None:
            raise RuntimeError(
                '[docker] snapshot build failed: {}'.format(self.tag)
            )

        return True

    def start(self) -> bool:
        """
        Start the machine from the image, build the image if necessary
        """

        if self.image is None:
            if not self.build():
                logging.error('[docker] start: halted - build failed')
                return False

        # reset the machine if needed so we always start from a clean image
        if self.machine is not None:
            if ensure(
                    '[docker]',
                    'machine {} exists,'.format(self.machine),
                    'force start will reset the machine.',
                    'Continue?'
            ):
                if not self.reset():
                    logging.error('[docker] start: halted - reset failed')
                    return False

            else:
                logging.error('[docker] start: ignored - machine exists')
                return False

        # start the machine
        execute([
            'docker', 'run',
            '--privileged',
            '--mount', 'type=bind,src={},dst={}'.format(
                config.PROJ_PATH, config.DOCKER_MPTR
            ),
            '--mount', 'type=tmpfs,dst={},tmpfs-size={}m'.format(
                config.VIRTEX_TMP_DIR, config.DOCKER_TMP_SIZE_IN_MB
            ),
            '--shm-size={}m'.format(config.DOCKER_SHM_SIZE_IN_MB),
            '--workdir', config.DOCKER_MPTR,
            '--detach',
            '--interactive',
            '--rm',
            '{}'.format(self.image),
        ])

        # make sure the machine is started
        self.machine = self._query_machine()
        if self.machine is None:
            raise RuntimeError(
                '[docker] snapshot start failed: {}'.format(self.tag)
            )

        return True

    def shell(self) -> bool:
        """
        Shell into the machine, start the machine if necessary
        """

        if self.machine is None:
            if not self.start():
                logging.error('[docker] shell: halted - start failed')
                return False

            assert self.machine is not None

        execute([
            'docker', 'exec',
            '--privileged',
            '--workdir', config.DOCKER_MPTR,
            '--interactive',
            '--tty',
            self.machine,
            '/bin/bash',
        ])

        return True

    def reset(self) -> bool:
        """
        Reset the machine to its built state, drop all modifications.
        """

        if self.machine is None:
            return True

        # warn if there are uses logged in
        users = self._query_users()
        if users != 0:
            if not ensure(
                    '[docker]',
                    '{} users exists for machine {},'.format(users,
                                                             self.machine),
                    'force reset will kill all the users.',
                    'Continue?'
            ):
                logging.info('[docker] reset: ignored - user exists')
                return False

        # kill the machine (and all users)
        execute([
            'docker', 'rm',
            '--force',
            self.machine,
        ])

        # make sure the machine is gone
        self.machine = self._query_machine()
        if self.machine is not None:
            raise RuntimeError(
                '[docker] snapshot reset failed: {}'.format(self.tag)
            )

        return True

    def clean(self) -> bool:
        """
        Clean the image, remove it (and the associated machine) completely
        """

        if self.image is None:
            return True

        # stop the machine if running
        if self.machine is not None:
            if ensure(
                    '[docker]',
                    'machine {} exists,'.format(self.machine),
                    'force clean will reset the machine.',
                    'Continue?'
            ):
                if not self.reset():
                    logging.error('[docker] clean: halted - reset failed')
                    return False

            else:
                logging.error('[docker] clean: ignored - machine exists')
                return False

        # remove dangling images
        deps = []

        outs, _ = execute0([
            'docker', 'images',
            '--filter', 'dangling=true',
            '--filter', 'since={}'.format(self.image),
            '--quiet',
        ])

        dang = outs.strip().split()
        for iid in dang:
            outs, _ = execute0([
                'docker', 'history',
                '--quiet',
                iid
            ])

            hist = outs.strip().split()
            if self.image in hist:
                deps.append(iid)

                # remove dangling machines
                outs, _ = execute0([
                    'docker', 'ps',
                    '--all',
                    '--filter', 'ancestor={}'.format(iid),
                    '--quiet',
                ])

                mach = outs.strip().split()
                execute([
                    'docker', 'rm',
                    '--force',
                    *mach
                ])

        if len(deps) != 0:
            execute([
                'docker', 'rmi',
                *deps,
            ])

        # remove the image
        execute([
            'docker', 'rmi',
            self.image,
        ])

        # make sure the image is gone
        self.image = self._query_image()
        if self.image is not None:
            raise RuntimeError(
                '[docker] snapshot clean failed: {}'.format(self.tag)
            )

        return True

    def status(self) -> str:
        return '[{}] <IMAGE: {}> MACHINE: {}'.format(
            colored(self.item, 'yellow', attrs=['bold']),
            colored('NONE' if self.image is None else self.image, 'cyan'),
            colored('NONE' if self.machine is None else self.machine, 'green'),
        )


class Docker(object):

    def __init__(self, ctxt: str, path: str, repo: str) -> None:
        # basics
        self.ctxt = ctxt
        self.path = path
        self.repo = repo

        # derived
        self.root, self.items = self._get_items()

        # snapshots
        self.snapshots = {
            item: Snapshot(self.ctxt, self.path, self.repo, item)
            for item in self.items
        }

    def _get_items(self) -> Tuple[str, Dict[str, List[str]]]:
        root = None  # type: Optional[str]
        rets = {
            item: []
            for item in os.listdir(self.path)
        }  # type: Dict[str, List[str]]

        for item in rets:
            dockerfile = os.path.join(self.path, item, 'Dockerfile')
            if not os.path.isfile(dockerfile):
                raise RuntimeError(
                    '[docker] expecting file at {}'.format(dockerfile)
                )

            # find the FROM line in the Dockerfile
            line = None  # type: Optional[str]
            with open(dockerfile) as f:
                for l in f:
                    if not l.startswith('FROM '):
                        continue

                    if line is not None:
                        raise RuntimeError(
                            '[docker] multi-inheritance found at {}'.format(
                                dockerfile
                            )
                        )

                    line = l.strip()

            if line is None:
                raise RuntimeError(
                    '[docker] no dependency found at {}'.format(dockerfile)
                )

            # parse the FROM line
            dep = line.split(' ')[1]
            if ':' in dep:
                dep_repo, dep_item = dep.split(':')
            else:
                dep_repo, dep_item = (dep, 'latest')

            if dep_repo != self.repo:
                assert root is None
                root = item
            else:
                rets[dep_item].append(item)

        assert root is not None
        return root, rets

    def build(self, item: str) -> bool:
        # build ancestors
        for key, val in self.items.items():
            if item in val and self.snapshots[key].image is None:
                self.build(key)

        # clean dependencies
        children = []

        for dep in self.items[item]:
            if self.snapshots[dep].image is None:
                continue

            if not ensure(
                    '[docker]',
                    'child snapshot {} exists,'.format(dep),
                    'force build will clean-build the child snapshot.',
                    'Continue?'
            ):
                logging.error('[docker] build: aborted - child exists')
                return False

            if not self.clean(dep):
                return False

            children.append(dep)

        # build the image
        if not self.snapshots[item].build():
            return False

        # rebuild dependencies
        for dep in children:
            if not self.build(dep):
                return False

        return True

    def start(self, item: str) -> bool:
        snap = self.snapshots[item]

        if snap.image is None:
            self.build(item)

        return snap.start()

    def shell(self, item: str) -> bool:
        snap = self.snapshots[item]

        if snap.machine is None:
            self.start(item)

        return snap.shell()

    def reset(self, item: str) -> bool:
        return self.snapshots[item].reset()

    def clean(self, item: str) -> bool:
        for dep in self.items[item]:
            if self.snapshots[dep].image is None:
                continue

            if not ensure(
                    '[docker]',
                    'child snapshot {} exists,'.format(dep),
                    'force clean will clean the child snapshot.',
                    'Continue?'
            ):
                logging.error('[docker] clean: aborted - child exists')
                return False

            if not self.clean(dep):
                return False

        return self.snapshots[item].clean()

    def _stat_dict(self, item: str, stats: Dict[str, str]) -> Dict[str, Dict]:
        return {
            stats[child]: self._stat_dict(child, stats)
            for child in self.items[item]
        }

    def status(self) -> None:
        stats = {
            key: snap.status()
            for key, snap in self.snapshots.items()
        }

        dicts = {stats[self.root]: self._stat_dict(self.root, stats)}
        print(asciitree.LeftAligned()(dicts))

    def mkleaf(self) -> bool:
        for key, val in self.items.items():
            if len(val) == 0:
                if not self.build(key):
                    return False

        return True

    def mkroot(self) -> bool:
        return self.build(self.root)


# entry
def main(argv: List[str]) -> int:
    # do not work if in a container
    if config.DOCKERIZED:
        print('Already in a dockerized environment', file=sys.stderr)
        return -1

    # build the docker instance
    docker = Docker(config.PROJ_PATH, config.DOCKER_PATH, config.DOCKER_REPO)

    # setup argument parser
    parser = ArgumentParser()

    # logging configs
    parser.add_argument(
        '-v', '--verbose', action='count', default=0,
        help='Verbosity level, can be specified multiple times, default to 0',
    )

    # action selection
    subs = parser.add_subparsers(dest='cmd')

    subs.add_parser(
        'status',
        help='Show docker status',
    )

    subs.add_parser(
        'mkleaf',
        help='Construct the full tree',
    )

    subs.add_parser(
        'mkroot',
        help='Recreate the existing tree from root',
    )

    sub_build = subs.add_parser(
        'build',
        help='Build docker snapshot',
    )
    sub_build.add_argument(
        'item', choices=docker.items.keys(),
        help='Name of the snapsnot',
    )

    sub_start = subs.add_parser(
        'start',
        help='Start docker snapshot',
    )
    sub_start.add_argument(
        'item', choices=docker.items.keys(),
        help='Name of the snapsnot',
    )

    sub_shell = subs.add_parser(
        'shell',
        help='Shell docker snapshot',
    )
    sub_shell.add_argument(
        'item', choices=docker.items.keys(),
        help='Name of the snapsnot',
    )

    sub_reset = subs.add_parser(
        'reset',
        help='Reset docker snapshot',
    )
    sub_reset.add_argument(
        'item', choices=docker.items.keys(),
        help='Name of the snapsnot',
    )

    sub_clean = subs.add_parser(
        'clean',
        help='Clean docker snapshot',
    )
    sub_clean.add_argument(
        'item', choices=docker.items.keys(),
        help='Name of the snapsnot',
    )

    # parse
    args = parser.parse_args(argv)

    # prepare logs
    enable_coloring_in_logging()
    logging.basicConfig(
        format='%(asctime)s %(levelname)s %(message)s',
        level=logging.WARNING - (logging.DEBUG - logging.NOTSET) * args.verbose
    )

    if args.cmd == 'status':
        docker.status()

    elif args.cmd == 'mkleaf':
        if not docker.mkleaf():
            return -1

    elif args.cmd == 'mkroot':
        if not docker.mkroot():
            return -1

    elif args.cmd == 'build':
        if not docker.build(args.item):
            return -1

    elif args.cmd == 'start':
        if not docker.start(args.item):
            return -1

    elif args.cmd == 'shell':
        if not docker.shell(args.item):
            return -1

    elif args.cmd == 'reset':
        if not docker.reset(args.item):
            return -1

    elif args.cmd == 'clean':
        if not docker.clean(args.item):
            return -1

    else:
        parser.print_help()
        return -2

    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
