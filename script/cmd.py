from typing import List

from abc import ABC, abstractmethod

from argparse import ArgumentParser, Namespace


class Parser(ABC):

    def __init__(self) -> None:
        self.parser = type(self).build()

    @classmethod
    @abstractmethod
    def build(cls) -> ArgumentParser:
        raise RuntimeError('Method not implemented')

    def parse(self, argv: List[str]) -> Namespace:
        args, rems = self.parser.parse_known_args(argv)

        if len(rems) != 0:
            raise RuntimeError('Unknown arguments: {}'.format(' '.join(rems)))

        return args


class Parser_CC(Parser):

    @classmethod
    def build(cls) -> ArgumentParser:
        parser = ArgumentParser(add_help=False)

        # output
        parser.add_argument('-o', type=str, default=None)

        # c/c++ standard
        parser.add_argument('-std', type=str, default=None)

        # optimization
        parser.add_argument('-O', type=str, default=None)

        # operation mode
        parser.add_argument('-c', action='store_true')
        parser.add_argument('-E', action='store_true')
        parser.add_argument('-S', action='store_true')

        # keys
        parser.add_argument('-ansi', action='store_true')
        parser.add_argument('-nostdinc', action='store_true')
        parser.add_argument('-nostdlib', action='store_true')
        parser.add_argument('-no-integrated-as', action='store_true')

        # control
        parser.add_argument('-C', action='store_true')
        parser.add_argument('-P', action='store_true')

        parser.add_argument('-s', action='store_true')
        parser.add_argument('-w', action='store_true')

        parser.add_argument('-r', action='store_true')
        parser.add_argument('-x', type=str, default=None)
        parser.add_argument('-G', type=str, default=None)

        parser.add_argument('-shared', action='store_true')

        # misc
        parser.add_argument('-pipe', action='store_true')

        # debug
        parser.add_argument('-g', action='store_true')
        parser.add_argument('-gdwarf-2', action='store_true')
        parser.add_argument('-gdwarf-4', action='store_true')
        parser.add_argument('-pg', action='store_true')

        # metadata
        parser.add_argument('-MD', action='store_true')
        parser.add_argument('-MG', action='store_true')
        parser.add_argument('-MM', action='store_true')
        parser.add_argument('-MP', action='store_true')
        parser.add_argument('-MF', type=str, default=None)

        # defines
        parser.add_argument('-D', type=str, action='append', default=[])
        # undefs
        parser.add_argument('-U', type=str, action='append', default=[])

        # includes
        parser.add_argument('-I', type=str, action='append', default=[])
        # include headers
        parser.add_argument('-include', type=str, action='append', default=[])
        # include system
        parser.add_argument('-isystem', type=str, action='append', default=[])

        # libs
        parser.add_argument('-l', type=str, action='append', default=[])

        # warnings
        parser.add_argument('-W', type=str, action='append', default=[])

        # flags
        parser.add_argument('-f', type=str, action='append', default=[])

        # machine
        parser.add_argument('-m', type=str, action='append', default=[])

        # extra params
        parser.add_argument('--param', type=str, action='append', default=[])

        # dump results
        parser.add_argument('-dA', action='store_true')
        parser.add_argument('-dD', action='store_true')
        parser.add_argument('-dI', action='store_true')
        parser.add_argument('-dM', action='store_true')

        # quiet
        parser.add_argument('-Q', action='append', default=[])

        # feature testing
        parser.add_argument('--version', action='store_true')
        parser.add_argument('-print-file-name', type=str, default=None)

        # src file
        parser.add_argument('inputs', type=str, nargs='*')

        # finish
        return parser
