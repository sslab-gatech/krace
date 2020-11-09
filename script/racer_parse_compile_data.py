#!/usr/bin/env python3

from typing import List, Set, Dict, Iterator, cast, Optional

import re
import os
import sys
import json
import pickle

from collections import OrderedDict

from util import find_all_files

# sys config
sys.setrecursionlimit(10000)

RE_RACER_COMPILE_LOG_FILE = re.compile(r'^(.*)\.racer$')
RE_RACER_COMPILE_INST_LOC = re.compile(r'^(.*?) @\[ (.*?) \]$')


class Value(object):

    def __init__(self, hval: int) -> None:
        self.hval = hval
        self.parent = None  # type: Optional[Value]

    def set_parent(self, parent: 'Value') -> None:
        self.parent = parent


class ValueInst(Value):

    def __init__(self, hval: int, info: List[str], text: str) -> None:
        super(ValueInst, self).__init__(hval)
        self.info = info
        self.text = text

    def get_parent(self) -> 'ValueBlock':
        return cast(ValueBlock, self.parent)

    def get_locs(self) -> str:
        return ' @@ '.join(self.info)


class ValueBlock(Value):

    def __init__(self, hval: int) -> None:
        super(ValueBlock, self).__init__(hval)
        self.insts = OrderedDict()  # type: OrderedDict[int, ValueInst]
        self.preds = []  # type: List[ValueBlock]
        self.succs = []  # type: List[ValueBlock]

    def add_inst(self, inst: ValueInst) -> None:
        self.insts[inst.hval] = inst
        inst.set_parent(self)

    def add_pred(self, block: 'ValueBlock') -> None:
        self.preds.append(block)
        block.succs.append(self)

    def add_succ(self, block: 'ValueBlock') -> None:
        assert block in self.succs
        assert self in block.preds

    def get_parent(self) -> 'ValueFunc':
        return cast(ValueFunc, self.parent)


class ValueFunc(Value):

    def __init__(self, hval: int, name: str) -> None:
        super(ValueFunc, self).__init__(hval)
        self.name = name
        self.blocks = OrderedDict()  # type: OrderedDict[int, ValueBlock]
        self.entry = None  # type: Optional[ValueBlock]
        self.exits = set()  # type: Set[ValueBlock]

    def add_block(self, block: ValueBlock) -> None:
        self.blocks[block.hval] = block
        block.set_parent(self)

    def get_parent(self) -> 'ValueModule':
        return cast(ValueModule, self.parent)

    def set_entry(self) -> None:
        for b in self.blocks.values():
            if len(b.preds) == 0:
                assert self.entry is None
                self.entry = b

        assert self.entry is not None

    def set_exits(self) -> None:
        for b in self.blocks.values():
            if len(b.succs) == 0:
                self.exits.add(b)

        assert len(self.exits) != 0

    def show_cfg(self, marks: Optional[Set[int]] = None) -> None:
        # prepare args
        if marks is None:
            marks = set()

        # build cfg
        assert self.entry is not None

        queue = [self.entry]
        visit = {self.entry}

        while len(queue) != 0:
            # handle linkage
            node = queue.pop()
            for item in node.succs:
                if item not in visit:
                    visit.add(item)
                    queue.insert(0, item)

            # dump instructions
            print('{}: pred <{}>, succ <{}>'.format(
                node.hval,
                ', '.join([str(i.hval) for i in node.preds]),
                ', '.join([str(i.hval) for i in node.succs]),
            ))

            for inst in node.insts.values():
                prefix = '==>' if inst.hval in marks else '   '
                print('{} {} -- {}'.format(prefix, inst.get_locs(), inst.text))

            print('\n')

        assert len(self.blocks) == len(visit)


class ValueModule(Value):

    def __init__(self, hval: int,
                 name: str,
                 apis: List[str], gvar: List[str], structs: List[str]) -> None:
        super(ValueModule, self).__init__(hval)
        self.name = name

        self.apis = apis
        self.gvar = gvar
        self.structs = structs

        self.funcsByHval = OrderedDict()  # type: OrderedDict[int, ValueFunc]
        self.funcsByName = OrderedDict()  # type: OrderedDict[str, ValueFunc]

    def add_func(self, func: ValueFunc) -> None:
        self.funcsByHval[func.hval] = func
        self.funcsByName[func.name] = func
        func.set_parent(self)

    def get_parent(self) -> None:
        return None


def iter_compile_logs_by_module(path: str) -> Iterator[ValueModule]:
    for fn in find_all_files(path, RE_RACER_COMPILE_LOG_FILE):
        with open(fn) as f:
            data = json.load(f)

            # pass 1: create the nodes
            meta = data['meta']
            module = ValueModule(
                meta['seed'],
                fn[len(path):],
                meta['apis'], meta['gvar'], meta['structs']
            )
            for k, v in data['funcs'].items():
                func = ValueFunc(v['meta']['hash'], k)
                module.add_func(func)

                for b in v['blocks']:
                    block = ValueBlock(b['hash'])
                    func.add_block(block)

                    for i in b['inst']:
                        # parse source locations
                        info = []  # type: List[str]
                        locs = i['info']
                        while '@' in locs:
                            m = RE_RACER_COMPILE_INST_LOC.match(locs)
                            assert m is not None
                            info.insert(0, m.group(1))
                            locs = m.group(2)
                        info.insert(0, locs)

                        inst = ValueInst(i['hash'], info, i['repr'])
                        block.add_inst(inst)

            # pass 2: create the edges
            for k, v in data['funcs'].items():
                func = module.funcsByName[k]

                for b in v['blocks']:
                    block = func.blocks[b['hash']]

                    for x in b['pred']:
                        block.add_pred(func.blocks[x])

            # pass 3: check the edges
            for k, v in data['funcs'].items():
                func = module.funcsByName[k]

                for b in v['blocks']:
                    block = func.blocks[b['hash']]

                    for x in b['succ']:
                        block.add_succ(func.blocks[x])

                func.set_entry()
                func.set_exits()

            # finish
            yield module


def iter_compile_logs_by_func(path: str) -> Iterator[ValueFunc]:
    for module in iter_compile_logs_by_module(path):
        for func in module.funcsByName.values():
            yield func


def iter_compile_logs_by_block(path: str) -> Iterator[ValueBlock]:
    for func in iter_compile_logs_by_func(path):
        for block in func.blocks.values():
            yield block


def iter_compile_logs_by_inst(path: str) -> Iterator[ValueInst]:
    for block in iter_compile_logs_by_block(path):
        for inst in block.insts.values():
            yield inst


def hmap_compile_logs_by_inst(path: str) -> Dict[int, ValueInst]:
    cache = os.path.join(path, 'racer-compile-database-by-inst.pickle')
    if os.path.exists(cache):
        with open(cache, 'rb') as f:
            return cast(Dict[int, ValueInst], pickle.load(f))

    data = {}  # type: Dict[int, ValueInst]

    for inst in iter_compile_logs_by_inst(path):
        hval = inst.hval

        if hval in data:
            print('Conflicting hash code for instruction: {}'.format(hval))
            print('Inst 1: {} - {}'.format(
                inst.get_locs(), inst.text
            ))
            print('Inst 2: {} - {}'.format(
                data[hval].get_locs(), data[hval].text
            ))

        data[hval] = inst

    with open(cache, 'wb') as f:
        pickle.dump(data, f)

    return data


def hmap_compile_logs_by_block(path: str) -> Dict[int, ValueBlock]:
    cache = os.path.join(path, 'racer-compile-database-by-block.pickle')
    if os.path.exists(cache):
        with open(cache, 'rb') as f:
            return cast(Dict[int, ValueBlock], pickle.load(f))

    data = {}  # type: Dict[int, ValueBlock]

    for block in iter_compile_logs_by_block(path):
        hval = block.hval

        if hval in data:
            print('Conflicting hash code for block: {}'.format(hval))
            print('Block 1: in func {}'.format(block.get_parent().name))
            print('Block 2: in func {}'.format(data[hval].get_parent().name))

        data[hval] = block

    with open(cache, 'wb') as f:
        pickle.dump(data, f)

    return data


def hmap_compile_logs_by_func(path: str) -> Dict[int, ValueFunc]:
    cache = os.path.join(path, 'racer-compile-database-by-func.pickle')
    if os.path.exists(cache):
        with open(cache, 'rb') as f:
            return cast(Dict[int, ValueFunc], pickle.load(f))

    data = {}  # type: Dict[int, ValueFunc]

    for func in iter_compile_logs_by_func(path):
        hval = func.hval

        if hval in data:
            print('Conflicting hash code for func: {}'.format(hval))
            print('Func 1: in module {}'.format(func.get_parent().name))
            print('Func 2: in module {}'.format(data[hval].get_parent().name))

        data[hval] = func

    with open(cache, 'wb') as f:
        pickle.dump(data, f)

    return data


class CompileDatabase(object):

    def __init__(self, path: str) -> None:
        self.insts = hmap_compile_logs_by_inst(path)
        self.funcs = hmap_compile_logs_by_func(path)
        self.blocks = hmap_compile_logs_by_block(path)
