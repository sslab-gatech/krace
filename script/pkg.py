import os
import logging

from abc import ABC, abstractmethod

from util import cd, execute0, prepdn, prepfn

import config


class Mark(object):

    def __init__(self, name: str, item: str, hval: str) -> None:
        self.path = os.path.join(
            config.STUDIO_MARKS, '{}-{}'.format(name, item)
        )
        self.hval = hval

    def exist(self) -> bool:
        if not os.path.exists(self.path):
            return False

        with open(self.path) as f:
            if f.read().strip() != self.hval:
                return False

        return True

    def touch(self) -> None:
        prepfn(self.path)
        with open(self.path, 'w') as f:
            f.write(self.hval)


class Package(ABC):

    def __init__(self, repo: str, name: str, path: str) -> None:
        # basics
        self.repo = repo
        self.name = name

        # paths
        self.path_src = path
        self.path_build = os.path.join(config.STUDIO_BUILD, self.name)
        self.path_store = os.path.join(config.STUDIO_STORE, self.name)

        # status
        with cd(config.PROJ_PATH):
            outs, _ = execute0(['git', 'ls-tree', 'HEAD', self.path_src])
            self.hash = outs.strip().split()[2]

    @abstractmethod
    def _setup_impl(self, override: bool) -> None:
        raise RuntimeError('Method not implemented')

    def setup(self, override: bool = False) -> None:
        mark = Mark(self.name, 'setup', self.hash)

        if mark.exist() and not override:
            logging.info('Mark {} existed, do nothing'.format(mark.path))
            return

        prepdn(self.path_build, True)
        prepdn(self.path_store, True)
        self._setup_impl(override)

        logging.info('[Done] Setup')
        mark.touch()

    @abstractmethod
    def _build_impl(self, override: bool) -> None:
        raise RuntimeError('Method not implemented')

    def build(self, override: bool = False) -> None:
        mark = Mark(self.name, 'build', self.hash)

        if mark.exist() and not override:
            logging.info('Mark {} existed, do nothing'.format(mark.path))
            return

        prepdn(self.path_build, False)
        prepdn(self.path_store, False)
        self._build_impl(override)

        logging.info('[Done] Build')
        mark.touch()

    @abstractmethod
    def _store_impl(self, override: bool) -> None:
        raise RuntimeError('Method not implemented')

    def store(self, override: bool = False) -> None:
        mark = Mark(self.name, 'store', self.hash)

        if mark.exist() and not override:
            logging.info('Mark {} existed, do nothing'.format(mark.path))
            return

        prepdn(self.path_build, False)
        prepdn(self.path_store, False)
        self._store_impl(override)

        logging.info('[Done] Store')
        mark.touch()

    def make(self, override: int = 0) -> None:
        self.setup(override > 2)
        self.build(override > 1)
        self.store(override > 0)
