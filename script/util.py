from typing import Any, Type, TypeVar, Callable, IO, Iterator, Pattern, \
    List, Dict, Tuple, Optional

import os
import sys
import shutil
import signal
import logging
import tempfile
import subprocess

from pathlib import Path
from contextlib import contextmanager
from multiprocessing import Pool


# with statements
@contextmanager
def cd(pn: str) -> Iterator[None]:
    cur = os.getcwd()
    os.chdir(os.path.expanduser(pn))
    try:
        yield
    finally:
        os.chdir(cur)


@contextmanager
def environ(key: str,
            value: Optional[str],
            concat: Optional[str] = None,
            prepend: bool = True) -> Iterator[None]:
    def _set_env(k: str, v: Optional[str]) -> None:
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v

    old_value = os.environ.get(key, None)

    if value is None or concat is None or old_value is None:
        new_value = value
    elif prepend:
        new_value = value + concat + old_value
    else:
        new_value = old_value + concat + value

    _set_env(key, new_value)

    try:
        yield
    finally:
        _set_env(key, old_value)


@contextmanager
def envpaths(*path: str) -> Iterator[None]:
    with environ('PATH',
                 value=':'.join(path), concat=':',
                 prepend=True):
        yield


@contextmanager
def envldpaths(*path: str) -> Iterator[None]:
    with environ('LD_LIBRARY_PATH',
                 value=':'.join(path), concat=':',
                 prepend=True):
        yield


@contextmanager
def envpreload(path: str) -> Iterator[None]:
    with environ('LD_PRELOAD',
                 value=path):
        yield


# dump output
def dump_execute_outputs(stdout: str, stderr: str, **others: str) -> None:
    print('-' * 8 + ' stdout ' + '-' * 8)
    print(stdout)

    print('-' * 8 + ' stderr ' + '-' * 8)
    print(stderr)

    for k, v in others.items():
        print('-' * 8 + ' {} '.format(k) + '-' * 8)
        print(v)


# command execution
def execute(cmd: List[str],
            stdout: IO = sys.stdout,
            stderr: IO = sys.stderr,
            timeout: Optional[int] = None) -> None:
    # version specific handling
    version_specific_kwargs = {}  # type: Dict[str, Any]
    if sys.version_info >= (3, 6):
        version_specific_kwargs['errors'] = 'backslashreplace'

    with subprocess.Popen(
            cmd,
            bufsize=0,
            stdout=stdout,
            stderr=stderr,
            universal_newlines=True,
            **version_specific_kwargs,
    ) as p:
        try:
            rc = p.wait(timeout=timeout)
            if rc != 0:
                raise RuntimeError('Failed to execute {}: exit code {}'.format(
                    ' '.join(cmd), rc
                ))
            return
        except subprocess.TimeoutExpired:
            p.kill()
            raise RuntimeError(
                'Failed to execute {}: timed out'.format(' '.join(cmd))
            )


def execute0(cmd: List[str],
             timeout: Optional[int] = None,
             timeout_allowed: bool = False) -> Tuple[str, str]:
    # version specific handling
    version_specific_kwargs = {}  # type: Dict[str, Any]
    if sys.version_info >= (3, 6):
        version_specific_kwargs['errors'] = 'backslashreplace'

    with subprocess.Popen(
            cmd,
            bufsize=16 * (1 << 20),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            **version_specific_kwargs,
    ) as p:
        try:
            outs, errs = p.communicate(timeout=timeout)

            rc = p.returncode
            if rc != 0:
                dump_execute_outputs(outs, errs)
                raise RuntimeError('Failed to execute {}: exit code {}'.format(
                    ' '.join(cmd), rc
                ))

            return outs, errs
        except subprocess.TimeoutExpired:
            p.kill()

            outs, errs = p.communicate()
            if timeout_allowed:
                return outs, errs

            dump_execute_outputs(outs, errs)
            raise RuntimeError(
                'Failed to execute {}: timed out'.format(' '.join(cmd))
            )


def execute1(cmd: List[str],
             timeout: Optional[int] = None) -> None:
    with open(os.devnull, 'w') as fout, open(os.devnull, 'w') as ferr:
        execute(cmd, fout, ferr, timeout)


def execute2(cmd: List[str],
             path_log: str,
             timeout: Optional[int] = None) -> None:
    path_out = path_log + '.out'
    path_err = path_log + '.err'
    with open(path_out, 'w') as stdout, open(path_err, 'w') as stderr:
        execute(cmd, stdout, stderr, timeout)


def execute3(cmd: List[str],
             path_out: str,
             path_err: str,
             timeout: Optional[int] = None) -> None:
    with open(path_out, 'w') as stdout, open(path_err, 'w') as stderr:
        execute(cmd, stdout, stderr, timeout)


# file operations
def inplace_replace(path: str, needle: str, replace: str) -> None:
    with tempfile.NamedTemporaryFile('w') as tmp:
        with open(path) as f:
            for line in f:
                newline = line.replace(needle, replace)
                tmp.write(newline)

        tmp.flush()
        shutil.copyfile(tmp.name, path)


def touch(path: str, size: Optional[int] = None) -> None:
    Path(path).touch()
    if size is not None:
        with open(path, 'wb') as f:
            f.truncate(size)


# filesystem operations
def prepdn(path: str, override: bool = False) -> None:
    if os.path.exists(path) and override:
        shutil.rmtree(path)
    os.makedirs(path, exist_ok=True)


def prepfn(path: str, override: bool = False) -> None:
    if os.path.exists(path) and override:
        os.unlink(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)


def find_all_files(base: str, regex: Optional[Pattern] = None) -> List[str]:
    result = []  # type: List[str]
    for dirpath, _, files in os.walk(base):
        for name in files:
            if regex is None or regex.match(name) is not None:
                result.append(os.path.join(dirpath, name))
    return result


def mkdir_seq(base: str) -> str:
    while True:
        path = os.path.join(base, str(len(os.listdir(base))))
        try:
            os.mkdir(path)
            return path
        except FileExistsError:
            pass


# multi-processing
T = TypeVar('T')
R = TypeVar('R')


def parallelize(
        func: Callable[[T], R],
        args: List[T],
        ncpu: Optional[int] = None) -> List[R]:
    with Pool(ncpu) as pool:
        try:
            return pool.map(func, args)
        except KeyboardInterrupt:
            pool.terminate()
            pool.join()
            raise RuntimeError('Interrupted')


# input handling
def ensure(*msg: str) -> bool:
    choice = input('{} [y/N]: '.format(' '.join(msg)))
    return choice in ['y', 'Y']


# design patterns
class Singleton(type):
    _insts = {}  # type: Dict[Type, Any]

    def __call__(cls, *args: Any, **kwargs: Any) -> Any:
        if cls not in cls._insts:
            cls._insts[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._insts[cls]


# string ops
def ascii_encode(s: str) -> bytes:
    return s.encode('ascii')


# signal handlers
@contextmanager
def disable_interrupt() -> Iterator[None]:
    sighand = signal.signal(signal.SIGINT, signal.SIG_IGN)
    try:
        yield
    finally:
        signal.signal(signal.SIGINT, sighand)


def _sigterm_handler(signo: int, frame: Any) -> None:
    logging.warning(
        'SIGTERM ignored, use SIGINT to interrupt and SIGKILL to force kill'
    )


def disable_sigterm() -> None:
    signal.signal(signal.SIGTERM, _sigterm_handler)


# linux
def is_error_code(rv: int) -> bool:
    return -4096 < rv < 0


# file loading
def read_source_location(loc: str, base: Optional[str] = None) -> str:
    toks = loc.split(':')
    if len(toks) == 2:
        return '{' + loc + '}'

    assert len(toks) == 3
    path = toks[0] if base is None else os.path.join(base, toks[0])
    lnum = int(toks[1])

    with open(path) as f:
        i = 0
        for line in f:
            line = line.strip()
            i += 1
            if i == lnum:
                return line

    return 'Invalid source location: {}'.format(loc)


# logging utils
@contextmanager
def multiplex_logging(path: str, mode: str = 'w') -> Iterator[None]:
    handler = logging.FileHandler(path, mode=mode)
    handler.setLevel(logging.DEBUG)
    logging.getLogger().addHandler(handler)
    try:
        yield
    finally:
        logging.getLogger().removeHandler(handler)
        handler.close()


def enable_coloring_in_logging() -> None:
    logging.addLevelName(
        logging.CRITICAL,
        '\033[1;31m%s\033[1;0m' % logging.getLevelName(logging.CRITICAL),
    )
    logging.addLevelName(
        logging.ERROR,
        '\033[1;31m%s\033[1;0m' % logging.getLevelName(logging.ERROR),
    )
    logging.addLevelName(
        logging.WARNING,
        '\033[1;33m%s\033[1;0m' % logging.getLevelName(logging.WARNING),
    )
    logging.addLevelName(
        logging.INFO,
        '\033[1;32m%s\033[1;0m' % logging.getLevelName(logging.INFO),
    )
    logging.addLevelName(
        logging.DEBUG,
        '\033[1;35m%s\033[1;0m' % logging.getLevelName(logging.DEBUG),
    )
