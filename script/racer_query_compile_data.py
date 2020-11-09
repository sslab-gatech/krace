#!/usr/bin/env python3

from typing import List, Set

import sys

from argparse import ArgumentParser

from pkg_linux import Package_LINUX

from racer_parse_compile_data import \
    iter_compile_logs_by_module, \
    iter_compile_logs_by_func, \
    iter_compile_logs_by_block, \
    iter_compile_logs_by_inst


def find_instruction(path: str, goal: str) -> None:
    hval = int(goal)

    for block in iter_compile_logs_by_block(path):
        if hval in block.insts:
            func = block.get_parent()
            print('Instruction: ' + block.insts[hval].text)
            print('Function: ' + func.name)
            print('--------')
            func.show_cfg({hval})
            return

    print('Instruction not found')


def find_block(path: str, goal: str) -> None:
    hval = int(goal)

    for func in iter_compile_logs_by_func(path):
        if hval in func.blocks:
            print('Function: ' + func.name)
            print('--------')
            func.show_cfg(set(func.blocks[hval].insts.keys()))
            return

    print('Block not found')


def find_string(path: str, goal: str) -> None:
    for inst in iter_compile_logs_by_inst(path):
        if goal in inst.text:
            func = inst.get_parent().get_parent()
            print('Instruction: ' + inst.text)
            print('Function: ' + func.name)
            print('--------')
            func.show_cfg({inst.hval})
            return

    print('String not found')


def find_location(path: str, goal: str) -> None:
    for inst in iter_compile_logs_by_inst(path):
        if goal in inst.get_locs():
            func = inst.get_parent().get_parent()
            print('Instruction: ' + inst.text)
            print('Function: ' + func.name)
            print('--------')
            func.show_cfg({inst.hval})
            return

    print('String not found')


def find_function(path: str, goal: str) -> None:
    try:
        hval = int(goal)
    except ValueError:
        hval = 0

    for module in iter_compile_logs_by_module(path):
        if hval in module.funcsByHval:
            module.funcsByHval[hval].show_cfg()
            return

        if goal in module.funcsByName:
            module.funcsByName[goal].show_cfg()
            return

    print('Function not found')


def list_module(path: str) -> None:
    mods = set()  # type: Set[str]

    for module in iter_compile_logs_by_module(path):
        mods.add(module.name)

    for i in sorted(mods):
        print(i)


def list_function(path: str) -> None:
    funcs = set()  # type: Set[str]

    for module in iter_compile_logs_by_module(path):
        funcs.update(module.funcsByName.keys())

    for i in sorted(funcs):
        print(i)


def list_location(path: str) -> None:
    locs = set()  # type: Set[str]

    for inst in iter_compile_logs_by_inst(path):
        locs.update(inst.info)

    for i in sorted(locs):
        print(i)


def list_api(path: str) -> None:
    apis = set()  # type: Set[str]
    funcs = set()  # type: Set[str]

    for module in iter_compile_logs_by_module(path):
        apis.update(module.apis)
        funcs.update(module.funcsByName.keys())

    apis.difference_update(funcs)

    for i in sorted(apis):
        print(i)


def list_gvar(path: str) -> None:
    gvars = set()  # type: Set[str]

    for module in iter_compile_logs_by_module(path):
        gvars.update(module.gvar)

    for i in sorted(gvars):
        print(i)


def list_type(path: str) -> None:
    types = set()  # type: Set[str]

    for module in iter_compile_logs_by_module(path):
        types.update(module.structs)

    for i in sorted(types):
        print(i)


def main(argv: List[str]) -> int:
    # prepare parser
    parser = ArgumentParser()

    subs = parser.add_subparsers(dest='cmd')

    # find
    sub_find = subs.add_parser('find')
    sub_find.add_argument('type', choices={'i', 's', 'l', 'b', 'f'})
    sub_find.add_argument('item')

    # list
    sub_list = subs.add_parser('list')
    sub_list.add_argument('type', choices={'m', 'f', 'l', 'a', 'g', 't'})

    # handle args
    args = parser.parse_args(argv)
    path = Package_LINUX().path_build

    # run action
    if args.cmd == 'find':
        if args.type == 'i':
            find_instruction(path, args.item)
        elif args.type == 's':
            find_string(path, args.item)
        elif args.type == 'l':
            find_location(path, args.item)
        elif args.type == 'b':
            find_block(path, args.item)
        elif args.type == 'f':
            find_function(path, args.item)

    elif args.cmd == 'list':
        if args.type == 'm':
            list_module(path)
        elif args.type == 'f':
            list_function(path)
        elif args.type == 'l':
            list_location(path)
        elif args.type == 'a':
            list_api(path)
        elif args.type == 'g':
            list_gvar(path)
        elif args.type == 't':
            list_type(path)

    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
