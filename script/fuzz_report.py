#!/usr/bin/env python3

from typing import Tuple, List, Dict, Set

import re
import os
import sys
import json
import logging

from argparse import ArgumentParser

from dart_viz import VizPoint
from fuzz_stat import iter_seed_exec_inc, SeedExecPack

import config

from util import execute, ensure, enable_coloring_in_logging

TICK_RANGE_THRESHOLD = 2000


def _analyze_file(
        path: str
) -> Dict[Tuple[int, int], Set[Tuple[VizPoint, VizPoint]]]:
    ptn_pair = re.compile(
        r'RACE <(.*?):(\d+) \|=\| (.*?):(\d+)> \[(\d+):(\d+)\] (\d+)'
    )
    ptn_list = re.compile(r'(\d+):(\d+) - (\d+)')

    results = {}  # type: Dict[Tuple[int, int], Set[Tuple[VizPoint, VizPoint]]]

    divider = False
    with open(path) as f:
        for line in f:
            line = line.strip()
            if divider:
                m = ptn_list.match(line)
                assert m is not None

            elif line.startswith('--------'):
                divider = True

            else:
                m = ptn_pair.match(line)
                if m is None:
                    continue

                t1 = int(m.group(2))
                t2 = int(m.group(4))
                assert t2 > t1
                if t2 - t1 > TICK_RANGE_THRESHOLD:
                    continue

                key = (int(m.group(5)), int(m.group(6)))
                p1 = VizPoint.parse(m.group(1))
                p2 = VizPoint.parse(m.group(3))

                if key not in results:
                    results[key] = set()

                results[key].add((p1, p2))

    return results


def show_races(
        show_stats: bool = False,
        show_alone: bool = False,
        show_cross: bool = False,
) -> None:
    _PairType = Dict[SeedExecPack, Set[Tuple[VizPoint, VizPoint]]]
    packs = {}  # type: Dict[Tuple[int, int], _PairType]

    # preload viewed traces to filter plotted traces
    base = os.path.join(config.STUDIO_BATCH, config.OPTION().tag)
    path = os.path.join(base, 'report.json')
    data = {}  # type: Dict[str, List[str]]
    if os.path.exists(path):
        with open(path) as f:
            data = json.load(f)

    path = os.path.join(base, 'manual.json')
    meta = {}  # type: Dict[Tuple[int, int], str]
    if os.path.exists(path):
        with open(path) as f:
            for k, v in json.load(f).items():
                toks = k.split(':')
                meta[(int(toks[0]), int(toks[1]))] = v

    # iterate over the exec packs
    for pack in iter_seed_exec_inc():
        result = os.path.join(pack.path, 'console-racer')
        if not os.path.exists(result):
            continue

        for key, val in _analyze_file(result).items():
            if key not in packs:
                packs[key] = {}

            packs[key][pack] = val

    # derive statistics
    stats = {
        key: sum([len(v) for v in val.values()])
        for key, val in packs.items()
    }

    def _show_race_pair(
            _key: Tuple[int, int],
            _meta: Dict[Tuple[int, int], str],
            _data: Dict[str, List[str]],
            _packs: Dict[Tuple[int, int], _PairType],
            _stats: Dict[Tuple[int, int], int],
    ) -> None:
        # get meta info
        info = ''
        if _key in _meta:
            info = _meta[_key]
        elif (_key[1], _key[0]) in _meta:
            info = _meta[(_key[1], _key[0])]

        print('{}:{} - {} [{}]'.format(_key[0], _key[1], _stats[_key], info))
        for pack in sorted(_packs[_key].keys(), key=lambda p: p.ctime):
            sample = list(_packs[_key][pack])[0]
            packid = '{}/{}/{}/{}'.format(
                pack.seed.sketch, pack.seed.digest, pack.seed.bucket,
                pack.rseq
            )

            # mark viewed items
            if packid in _data:
                if str(sample[0]) in data[packid] and \
                        str(sample[1]) in data[packid]:
                    mark = '> '
                else:
                    mark = '  '
            else:
                mark = '  '

            # show it
            print('\t{} {} [{} |=| {}]'.format(
                mark, packid, sample[0], sample[1]
            ))

    if show_stats:
        for item in sorted(stats.items(), key=lambda x: x[1], reverse=True):
            print('{}:{} - {}'.format(item[0][0], item[0][1], item[1]))

    if show_alone:
        for key in packs:
            _show_race_pair(key, meta, data, packs, stats)

    if show_cross:
        hist = set()  # type: Set[Tuple[int, int]]
        for key in packs:
            # only show alias pairs that can be reversed
            if key[0] == key[1]:
                continue

            inv = (key[1], key[0])
            if inv not in packs:
                continue
            if key in hist or inv in hist:
                continue

            hist.add(key)
            hist.add(inv)

            # show with marking
            print('================================================')
            _show_race_pair(key, meta, data, packs, stats)
            print('------------------------------------------------')
            _show_race_pair(inv, meta, data, packs, stats)
            print('\n')


def show_errors() -> None:
    for pack in iter_seed_exec_inc():
        result = os.path.join(pack.path, 'console-error')
        if os.path.exists(result):
            print(result)


def view_trace(pack: str, points: List[str]) -> None:
    base = os.path.join(config.STUDIO_BATCH, config.OPTION().tag)

    # accounting
    hist = os.path.join(base, 'report.json')
    data = {}  # type: Dict[str, List[str]]
    if os.path.exists(hist):
        with open(hist) as f:
            data = json.load(f)

    if pack in data:
        exts = []
        for p in points:
            if p not in data[pack]:
                exts.append(p)

        if len(exts) == 0:
            if not ensure('Trace viewed already, continue?'):
                return

        else:
            data[pack].extend(exts)
            with open(hist, 'w') as f:
                json.dump(data, f, indent=2)

    else:
        data[pack] = points
        with open(hist, 'w') as f:
            json.dump(data, f, indent=2)

    logging.info('Done with accounting, plotting trace')

    # trace viewing
    path = os.path.join(base, 'queue', pack, 'ledger')

    cmds = [os.path.join(config.SCRIPT_PATH, 'dart_app.py'), path, 'trace']
    for point in points:
        cmds.extend(['-s', point])

    execute(cmds)


def main(argv: List[str]) -> int:
    # prepare parser
    parser = ArgumentParser()

    # logging configs
    parser.add_argument(
        '-v', '--verbose', action='count', default=1,
        help='Verbosity level, can be specified multiple times, default to 1',
    )

    subs = parser.add_subparsers(dest='cmd')

    # show
    sub_show = subs.add_parser('show')
    sub_show.add_argument('type', choices={'s', 'a', 'x', 'e'})

    # view
    sub_view = subs.add_parser('view')
    sub_view.add_argument('pack')
    sub_view.add_argument('points', nargs='+')

    # handle args
    args = parser.parse_args(argv)

    # prepare logs
    enable_coloring_in_logging()
    logging.basicConfig(
        format='%(asctime)s %(levelname)s %(message)s',
        level=logging.WARNING - (logging.DEBUG - logging.NOTSET) * args.verbose
    )

    # run action
    if args.cmd == 'show':
        if args.type == 's':
            show_races(show_stats=True)
        elif args.type == 'a':
            show_races(show_alone=True)
        elif args.type == 'x':
            show_races(show_cross=True)
        elif args.type == 'e':
            show_errors()

    elif args.cmd == 'view':
        view_trace(args.pack, args.points)

    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
