from typing import List

import os
import string

from abc import ABC, abstractmethod


class Generator(ABC):

    def __init__(self, path: str) -> None:
        self.path = os.path.abspath(os.path.join(__file__, '..', path))

    @abstractmethod
    def gen(self) -> str:
        raise RuntimeError('Method not implemented')

    def save(self) -> None:
        with open(self.path, 'w') as f:
            f.write(self.gen())


class Generator_VARDEF(Generator):
    CHARSET = string.ascii_uppercase

    def __init__(self, num_group: int, max_group_size: int) -> None:
        super(Generator_VARDEF, self).__init__('dart/vardef.h')
        self.num_group = num_group
        self.max_group_size = max_group_size
        self.mark = '_RACER_DART_VARDEF_H_'

    def gen_header(self) -> List[str]:
        return [
            '#ifndef {}'.format(self.mark),
            '#define {}'.format(self.mark),
        ]

    def gen_footer(self) -> List[str]:
        return [
            '#endif /* {} */'.format(self.mark),
        ]

    def gen_ignore(self) -> List[str]:
        return [
            '#define _VARDEF_IGNORE(...)'
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
                '{}GROUP{}(Func, None, ##__VA_ARGS__)'.format(prefix, i - 1),
            ]))

        # generate VARDEF
        exprs.append(' '.join([
            '#define',
            '{}(Func, None, ...)'.format(vardef),
            '{}SELECT({}##__VA_ARGS__, {})(Func, None, ##__VA_ARGS__)'.format(
                prefix, ', ' * group_size, ', '.join([
                    '{}GROUP{}'.format(prefix, i) +
                    ', _VARDEF_IGNORE' * (group_size - 1)
                    for i in range(num_group, -1, -1)
                ])
            )
        ]))

        return exprs

    def gen(self) -> str:
        stmts = self.gen_header() + self.gen_ignore()
        for i in range(1, self.max_group_size + 1, 1):
            stmts += self.gen_pack(self.num_group, i)

        stmts += self.gen_footer()
        return '\n'.join(stmts)


if __name__ == '__main__':
    g = Generator_VARDEF(num_group=8, max_group_size=6)
    g.save()
