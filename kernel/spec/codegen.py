from typing import List

import os
import string

from abc import ABC, abstractmethod


class Generator(ABC):

    def __init__(self, name: str) -> None:
        # basic
        self.name = name

        # derived
        self.path = 'generated/{}.h'.format(self.name)
        self.mark = '_RACER_SPEC_{}_H_'.format(self.name.upper())

    def gen_warning(self) -> List[str]:
        return [
            '/* AUTO-GENERATED ({}) - DO NOT EDIT */'.format(self.name)
        ]

    def gen_mark_header(self) -> List[str]:
        return [
            '#ifndef {}'.format(self.mark),
            '#define {}'.format(self.mark),
        ]

    def gen_mark_footer(self) -> List[str]:
        return [
            '#endif /* {} */'.format(self.mark),
        ]

    @abstractmethod
    def generate(self) -> str:
        raise RuntimeError('Method not implemented')

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, 'w') as f:
            f.write(self.generate())


class Generator_VARDEF(Generator):
    CHARSET = string.ascii_uppercase

    def __init__(self, num_group: int, max_group_size: int) -> None:
        super(Generator_VARDEF, self).__init__('vardef')
        self.num_group = num_group
        self.max_group_size = max_group_size

    def gen_ignore(self) -> List[str]:
        return [
            '#define _VARDEF_IGNORE(...) static_assert(false)'
        ]

    def gen_pack(self, num_group: int, group_size: int) -> List[str]:
        exprs = []  # type: List[str]

        # common
        vardef = 'VARDEF{}'.format(group_size)
        prefix = '_' + vardef + '_'

        # generate SELECT
        elems = []  # type: List[str]
        for i in range(num_group + 1):
            for j in range(group_size):
                elems.append('{}{}'.format(Generator_VARDEF.CHARSET[j], i))

        exprs.append(
            '#define {}SELECT({}, N, ...) N'.format(
                prefix, ', '.join(elems)
            )
        )

        # generate GROUP_X
        arg_group = ', '.join([
            Generator_VARDEF.CHARSET[j] for j in range(group_size)
        ])

        exprs.append(
            '#define {}GROUP0(Func, None, ...) None'.format(
                prefix
            )
        )
        for i in range(1, num_group + 1, 1):
            exprs.append(' '.join([
                '#define',
                '{}GROUP{}(Func, None, {}, ...)'.format(prefix, i, arg_group),
                'Func({})'.format(arg_group),
                '{}GROUP{}(Func, None, __VA_ARGS__)'.format(prefix, i - 1),
            ]))

        # generate VARDEF
        exprs.append(' '.join([
            '#define',
            '{}(Func, None, ...)'.format(vardef),
            '{}SELECT(, , ##__VA_ARGS__, {})(Func, None, __VA_ARGS__)'.format(
                prefix, ', '.join([
                    '{}GROUP{}'.format(prefix, i) +
                    ', _VARDEF_IGNORE' * (group_size - 1)
                    for i in range(num_group, -1, -1)
                ])
            )
        ]))

        return exprs

    def generate(self) -> str:
        exprs = self.gen_warning()
        exprs += self.gen_mark_header()
        exprs += self.gen_ignore()
        for i in range(1, self.max_group_size + 1, 1):
            exprs += self.gen_pack(self.num_group, i)
        exprs += self.gen_mark_footer()
        return '\n'.join(exprs)


if __name__ == '__main__':
    g = Generator_VARDEF(num_group=8, max_group_size=6)
    g.save()
