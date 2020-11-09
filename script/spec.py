from typing import List

import sys
import logging

from argparse import ArgumentParser

from spec_extract import Extractor
from spec_factory import Spec

from util import enable_coloring_in_logging


def main(argv: List[str]) -> int:
    # setup argument parser
    parser = ArgumentParser()

    # logging configs
    parser.add_argument(
        '-v', '--verbose', action='count', default=1,
        help='Verbosity level, can be specified multiple times, default to 1',
    )

    # override flag
    parser.add_argument(
        '-c', '--clean', action='store_true',
        help='Clean existing files',
    )

    # action selection
    subs = parser.add_subparsers(dest='cmd')
    subs.add_parser(
        'extract',
        help='Extract information',
    )

    sub_compose = subs.add_parser(
        'compose',
        help='Compose the specification',
    )
    sub_compose.add_argument(
        '-s', '--show', action='store_true',
        help='Show the composed specification in text'
    )

    # parse
    args = parser.parse_args(argv)

    # prepare logs
    enable_coloring_in_logging()
    logging.basicConfig(
        format='%(asctime)s %(levelname)s %(message)s',
        level=logging.WARNING - (logging.DEBUG - logging.NOTSET) * args.verbose
    )

    # construct the instance
    if args.cmd == 'extract':
        extractor = Extractor()
        extractor.extract(args.clean)

    elif args.cmd == 'compose':
        composer = Spec.formulate()
        if args.show:
            for syscall in composer.Syscalls:
                assert syscall.base is not None
                print('[{}]'.format(syscall.base.name))

                total_weight = sum(syscall.opts.values())
                for option, weight in syscall.opts.items():
                    if weight == 0:
                        continue
                    print('  {:2.0f}%% - {}'.format(
                        weight / total_weight * 10000, option.dump()
                    ))

    else:
        parser.print_help()
        return -1

    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
