#!/usr/bin/env python3

# TODO (fix the stub issue of PySide and graaphviz)
# type: ignore

from typing import cast, NamedTuple, Type, List, Dict, Set, Tuple, \
    Optional, Union

import os
import sys
import json
import traceback

from argparse import ArgumentParser

from graphviz import Digraph

from PySide2.QtCore import \
    Qt, QPoint, QRect, QModelIndex
from PySide2.QtGui import \
    QFont, \
    QPen, QBrush, QPainter, \
    QPaintEvent, \
    QStandardItemModel, QStandardItem
from PySide2.QtWidgets import \
    QGroupBox, QAbstractItemView, QTreeView, QStatusBar, \
    QLineEdit, QPushButton, QCheckBox, \
    QVBoxLayout, QHBoxLayout, \
    QStyleOptionViewItem, \
    QWidget, QMessageBox, QApplication

from dart_viz import \
    VizJointType, \
    VizPoint, VizItem, VizFunc, VizExec, VizTask, VizRuntime, VizPack, \
    VizItemFuncEnter, VizItemFuncExit, VizItemCFGBlock, \
    VizItemForkRegister, VizItemForkCancel, \
    VizItemJoinArrive, VizItemJoinPass, \
    VizItemCtxtRun, VizItemExecPause, VizItemExecResume, \
    VizItemOrderDeposit, VizItemOrderConsume, \
    VizItemOrderPublish, VizItemOrderSubscribe, \
    VizItemQueueArrive, VizItemQueueNotify, \
    VizItemLockAcquire, VizItemLockRelease, \
    VizItemMemAlloc, VizItemMemFree, \
    VizItemMemRead, VizItemMemWrite, \
    VizItemMark, VizItemStep, \
    VizSlotFork, VizSlotJoin, VizSlotOrder, VizSlotQueue

from util import execute


class OverLay(QWidget):

    def __init__(self, parent: 'DartWidget'):
        QWidget.__init__(self, parent)

        # basics of overlay
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

        # drawing format
        self.p1 = QPoint(0, 0)
        self.p2 = QPoint(0, 0)
        self.pen = QPen(Qt.black, 1, Qt.SolidLine)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter()
        painter.begin(self)

        # use transparent background
        painter.setBackgroundMode(Qt.TransparentMode)

        # paint the line
        painter.setPen(self.pen)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.drawLine(self.p1, self.p2)

        painter.end()


def pop_warning(message: str) -> None:
    box = QMessageBox()
    box.setIcon(QMessageBox.Warning)
    box.setText(message)
    box.setWindowTitle('Warning')
    box.exec_()


def diag_rect_lc(r1: QRect, r2: QRect) -> Tuple[QPoint, QPoint, QRect]:
    x1 = r1.x()
    y1 = r1.y() + r1.height() // 2
    x2 = r2.x()
    y2 = r2.y() + r2.height() // 2

    x_pos = min(x1, x2)
    x_len = abs(x1 - x2)
    y_pos = min(y1, y2)
    y_len = abs(y1 - y2)

    return QPoint(x1, y1), QPoint(x2, y2), QRect(x_pos, y_pos, x_len, y_len)


# utilities
def abs_item_rect(
        dart: 'DartWidget', tree: QTreeView, index: QModelIndex
) -> QRect:
    rect = tree.visualRect(index)

    # adjust for indentation
    indent = tree.indentation()
    rect.adjust(indent, 0, indent, 0)

    # map to correct part
    return QRect(
        tree.viewport().mapTo(dart.region_content, rect.topLeft()),
        tree.viewport().mapTo(dart.region_content, rect.bottomRight()),
    )


def furthest_collapsed(
        tree: QTreeView, node: QStandardItem
) -> Optional[QStandardItem]:
    if node is None:
        return None

    pars = furthest_collapsed(tree, node.parent())
    if pars is not None:
        return pars

    if not tree.isExpanded(node.index()):
        return node

    return None


class DartAsyncConnector(NamedTuple):
    slot: Union[VizSlotFork, VizSlotJoin, VizSlotQueue, VizSlotOrder]
    from_item: VizItem
    into_item: VizItem
    overlay: OverLay


class DartFuncNode(QStandardItem):

    def __init__(self, dart: 'DartWidget', func: VizFunc) -> None:
        super().__init__(func.func.name)
        self.dart = dart
        self.func = func

        # async drawing
        self.async_send = []  # type: List[DartAsyncConnector]
        self.async_recv = []  # type: List[DartAsyncConnector]


class DartItemNode(QStandardItem):

    def __init__(self, dart: 'DartWidget', item: VizItem) -> None:
        super().__init__(item.icon() + ' ' + item.desc())
        self.dart = dart
        self.item = item

        # async drawing
        self.async_send = []  # type: List[DartAsyncConnector]
        self.async_recv = []  # type: List[DartAsyncConnector]


class DartTaskTree(QTreeView):

    def __init__(self, dart: 'DartWidget', task: VizTask) -> None:
        super().__init__()
        self.dart = dart
        self.task = task

        # states
        self.keywords = set()  # type: Set[VizItem]

        # dependencies
        self.button_mark = QPushButton('Mark')
        self.button_clear = QPushButton('Clear')
        self.button_reset = QPushButton('Reset')

        self.textin_search = QLineEdit()
        self.button_search = QPushButton('Search')

        layout_switch = QHBoxLayout()
        layout_switch.addWidget(self.button_mark)
        layout_switch.addWidget(self.button_clear)
        layout_switch.addWidget(self.button_reset)
        layout_switch.addWidget(self.textin_search)
        layout_switch.addWidget(self.button_search)

        self.switch = QWidget()
        self.switch.setLayout(layout_switch)

        self.status = QStatusBar()

        # connects signals
        self.button_mark.clicked.connect(self._on_mark_clicked)
        self.button_clear.clicked.connect(self._on_clear_clicked)
        self.button_reset.clicked.connect(self._on_reset_clicked)
        self.button_search.clicked.connect(self._on_search_clicked)

    def finish_initialization(self) -> None:
        # register selection notification
        self.selectionModel().currentChanged.connect(self._on_cursor_changed)

    # utilities
    def _get_draw_pack(self, item: VizItem) -> Tuple[
        'DartTaskTree',
        Optional[Union['DartFuncNode', 'DartItemNode']],
        Optional[QRect]
    ]:
        tree = self.dart.map_task[item.task]
        node = furthest_collapsed(tree, self.dart.map_item[item])

        if node is None:
            rect = None
        else:
            rect = tree.visualRect(node.index())
            if not rect.isValid():
                rect = None

        return tree, node, rect

    # async plotting
    def _plot_async_line(
            self, overlay: OverLay, src: QRect, dst: QRect, pen: QPen
    ) -> None:
        p1, p2, rect = diag_rect_lc(src, dst)

        overlay.canvas = rect
        overlay.p1 = p1
        overlay.p2 = p2
        overlay.pen = pen

    def _plot_async_send(
            self, send: QModelIndex, conn: DartAsyncConnector
    ) -> None:
        # find the other end
        recv_item = conn.into_item
        recv_tree, recv_node, recv_rect = self._get_draw_pack(recv_item)
        if recv_rect is None:
            conn.overlay.hide()
            return

        # select the pen
        if isinstance(conn.slot, VizSlotFork):
            pen = QPen(Qt.darkYellow, 1, Qt.SolidLine)

        elif isinstance(conn.slot, VizSlotJoin):
            pen = QPen(Qt.darkGreen, 1, Qt.SolidLine)

        elif isinstance(conn.slot, VizSlotOrder):
            pen = QPen(Qt.darkMagenta, 1, Qt.SolidLine)

        elif isinstance(conn.slot, VizSlotQueue):
            pen = QPen(Qt.darkGray, 1, Qt.SolidLine)

        else:
            raise RuntimeError('Invalid async slot type')

        # tell overlay on line spec
        self._plot_async_line(
            conn.overlay,
            abs_item_rect(self.dart, self, send),
            abs_item_rect(self.dart, recv_tree, recv_node.index()),
            pen
        )

        conn.overlay.setGeometry(self.dart.region_content.geometry())
        conn.overlay.update()
        conn.overlay.show()

    def drawRow(
            self,
            painter: QPainter, options: QStyleOptionViewItem, index: QModelIndex
    ) -> None:
        # conditional rendering
        node = cast(QStandardItemModel, self.model()).itemFromIndex(index)

        # highlight nodes with error
        if isinstance(node, DartItemNode):
            item = node.item
            if len(item.error) != 0:
                node.setForeground(QBrush(Qt.red))
                node.setWhatsThis('\n'.join(item.error))

        # original rendering
        super().drawRow(painter, options, index)

        if self.dart.show_async:
            # if an ItemNode is drawn, it must be expanded
            if isinstance(node, DartItemNode):
                for i in node.async_send:
                    self._plot_async_send(index, i)

            ''' NOTE: toggle as needed
            # if a FuncNode is drawn, only draw if it is collapsed and not root
            elif isinstance(node, DartFuncNode):
                if not self.isExpanded(index):
                    if node.func.call_from is not None:
                        for i in node.async_send:
                            self._plot_async_send(index, i)
            '''

    def _on_cursor_changed(self, index: QModelIndex, _p: QModelIndex) -> None:
        # clear message first
        self.status.clearMessage()

        # check if the root node is selected
        if not index.isValid():
            return

        # check if a func is selected
        node = cast(QStandardItemModel, self.model()).itemFromIndex(index)
        if isinstance(node, DartFuncNode):
            i_init = node.func.items[0]
            i_fini = node.func.items[-1]
            msg = '<{}> {} -- <{}> {}'.format(
                i_init.gcnt, i_init.locate(), i_fini.gcnt, i_fini.locate()
            )

        # check if an item is selected
        else:
            assert isinstance(node, DartItemNode)
            idx = node.item.gcnt
            pos = node.item.locate()
            msg = '<{}> {}'.format(idx, pos)

            txt = node.item.code()
            if txt is not None:
                msg = msg + ': ' + txt

        # show the message
        self.status.showMessage(msg)

    def _on_mark_clicked(self) -> None:
        index = self.selectionModel().currentIndex()
        if not index.isValid():
            pop_warning('Nothing to mark')
            return

        node = cast(QStandardItemModel, self.model()).itemFromIndex(index)
        if isinstance(node, DartFuncNode):
            pop_warning('Only items can be marked')
            return

        assert isinstance(node, DartItemNode)
        self.dart.add_mark(node.item)

    def _on_clear_clicked(self) -> None:
        index = self.selectionModel().currentIndex()
        if not index.isValid():
            pop_warning('Nothing to unmark')
            return

        node = cast(QStandardItemModel, self.model()).itemFromIndex(index)
        if isinstance(node, DartFuncNode):
            pop_warning('Only items can be unmark')
            return

        assert isinstance(node, DartItemNode)
        self.dart.del_mark(node.item)

    def _on_reset_clicked(self) -> None:
        self.selectionModel().clear()

    def _on_search_clicked(self) -> None:
        # clear prior searches
        for item in self.keywords:
            nval = self.dart.map_item[item]
            nval.setBackground(QBrush(Qt.white))
            if not self.dart.should_item_display(item):
                index = nval.index()
                self.setRowHidden(index.row(), index.parent(), True)

        # get needle to be searched
        needle = self.textin_search.text().strip()
        if len(needle) == 0:
            return

        # only search in expanded execution units
        for unit in self.task.children:
            base = unit.stack[0]
            node = self.dart.map_func[base]
            if not self.isExpanded(node.index()):
                continue

            for item in unit.children:
                if needle not in item.desc():
                    continue

                if item in self.dart.marks:
                    continue

                self.keywords.add(item)

                # style the keyword
                nval = self.dart.map_item[item]
                nval.setBackground(QBrush(Qt.cyan))
                index = nval.index()
                self.setRowHidden(index.row(), index.parent(), False)

                # expand the node and its parents
                while nval is not None:
                    self.expand(nval.index())
                    nval = nval.parent()


class DartWidget(QWidget):

    def __init__(
            self, pack: VizPack, opts: Set[VizPoint]
    ) -> None:
        super().__init__()

        # basics
        self.pack = pack

        # ctxts
        ctxts = {p.ptid for p in opts}

        # marked items
        self.marks = {self.pack.get_item(p) for p in opts}

        # opt: async
        self.show_async = False
        self.inst_async = []  # type: List[DartAsyncConnector]

        # opt: items
        self.show_order = False
        self.show_lock = False
        self.show_slab = False
        self.show_mem = False
        self.show_flow = False

        # opt: trace
        self.show_trace = False

        # opt: error
        self.show_error = False

        # mapping
        self.map_item = {}  # type: Dict[VizItem, DartItemNode]
        self.map_func = {}  # type: Dict[VizFunc, DartFuncNode]
        self.map_unit = {}  # type: Dict[VizExec, DartFuncNode]
        self.map_task = {}  # type: Dict[VizTask, DartTaskTree]

        # layout - control
        self.button_collapse_all = QPushButton('Collapse')
        self.textin_expand = QLineEdit()
        self.textin_expand.setText('; '.join(sorted([
            str(m.locate()) for m in self.marks
        ])))
        self.button_expand = QPushButton('Expand')

        self.chkbox_plot_async = QCheckBox('Async')
        self.chkbox_plot_async.setChecked(False)
        self.chkbox_plot_order = QCheckBox('Order')
        self.chkbox_plot_order.setChecked(False)
        self.chkbox_plot_lock = QCheckBox('Lock')
        self.chkbox_plot_lock.setChecked(False)
        self.chkbox_plot_slab = QCheckBox('Slab')
        self.chkbox_plot_slab.setChecked(False)
        self.chkbox_plot_mem = QCheckBox('Mem')
        self.chkbox_plot_mem.setChecked(False)
        self.chkbox_plot_flow = QCheckBox('Flow')
        self.chkbox_plot_flow.setChecked(False)
        self.chkbox_plot_trace = QCheckBox('Trace')
        self.chkbox_plot_trace.setChecked(False)
        self.chkbox_plot_error = QCheckBox('Error')
        self.chkbox_plot_error.setChecked(False)

        layout_control = QHBoxLayout()
        layout_control.addWidget(self.button_collapse_all)
        layout_control.addWidget(self.textin_expand)
        layout_control.addWidget(self.button_expand)

        layout_control.addWidget(self.chkbox_plot_async)
        layout_control.addWidget(self.chkbox_plot_order)
        layout_control.addWidget(self.chkbox_plot_lock)
        layout_control.addWidget(self.chkbox_plot_slab)
        layout_control.addWidget(self.chkbox_plot_mem)
        layout_control.addWidget(self.chkbox_plot_flow)
        layout_control.addWidget(self.chkbox_plot_trace)
        layout_control.addWidget(self.chkbox_plot_error)

        self.region_control = QGroupBox()
        self.region_control.setTitle('Control')
        self.region_control.setLayout(layout_control)

        # layout - content
        layout_content = QHBoxLayout()
        for ptid, task in sorted(pack.tasks.items(), key=lambda x: x[0]):
            if ptid not in ctxts:
                continue

            tree = self._viz_task(task)

            region_panel = QWidget()
            layout_panel = QVBoxLayout()
            layout_panel.addWidget(tree.switch)
            layout_panel.addWidget(tree)
            layout_panel.addWidget(tree.status)
            region_panel.setLayout(layout_panel)

            layout_content.addWidget(region_panel)

        self.region_content = QGroupBox()
        self.region_content.setTitle('Content')
        self.region_content.setLayout(layout_content)

        # overall
        layout = QVBoxLayout()
        layout.addWidget(self.region_control)
        layout.addWidget(self.region_content)
        self.setLayout(layout)

        # connecting the signals
        self.button_collapse_all.clicked.connect(self._on_collapse_all_clicked)
        self.button_expand.clicked.connect(self._on_expand_clicked)

        self.chkbox_plot_async.stateChanged.connect(self._on_plot_async_changed)
        self.chkbox_plot_order.stateChanged.connect(self._on_plot_order_changed)
        self.chkbox_plot_lock.stateChanged.connect(self._on_plot_lock_changed)
        self.chkbox_plot_slab.stateChanged.connect(self._on_plot_slab_changed)
        self.chkbox_plot_mem.stateChanged.connect(self._on_plot_mem_changed)
        self.chkbox_plot_flow.stateChanged.connect(self._on_plot_flow_changed)
        self.chkbox_plot_trace.stateChanged.connect(self._on_plot_trace_changed)
        self.chkbox_plot_error.stateChanged.connect(self._on_plot_error_changed)

        # enumerating the items and collect paint instructions
        for item in self.map_item.keys():
            if isinstance(item, (
                    VizItemForkRegister,
                    VizItemJoinArrive,
                    VizItemOrderDeposit,
                    VizItemQueueArrive,
            )):
                slot = item.slot
                for point in slot.users:
                    user = self.pack.get_item(point)
                    if user not in self.map_item:
                        continue

                    conn = DartAsyncConnector(
                        slot, item, user, OverLay(self)
                    )
                    self.inst_async.append(conn)

                    # assign conn to the from side
                    self.map_item[item].async_send.append(conn)
                    for func in item.chain():
                        self.map_func[func].async_send.append(conn)

                    # assign conn to the into side
                    self.map_item[user].async_recv.append(conn)
                    for func in user.chain():
                        self.map_func[func].async_recv.append(conn)

        # highlight marks
        for item in self.marks:
            node = self.map_item[item]
            node.setBackground(QBrush(Qt.yellow))

        # set node visibility initially
        for item, node in self.map_item.items():
            if item in self.marks or self.should_item_display(item):
                continue

            index = node.index()
            self.map_task[item.task].setRowHidden(
                index.row(), index.parent(), True
            )

    # tree construction
    def _viz_item(self, item: VizItem) -> DartItemNode:
        # check cache
        if item in self.map_item:
            return self.map_item[item]

        node = DartItemNode(self, item)

        # cache
        self.map_item[item] = node
        return node

    def _viz_func(self, func: VizFunc) -> DartFuncNode:
        # check cache
        if func in self.map_func:
            return self.map_func[func]

        node = DartFuncNode(self, func)

        for item in func.items:
            node.appendRow(self._viz_item(item))
            if isinstance(item, VizItemFuncEnter):
                node.appendRow(self._viz_func(item.func))

        # cache
        self.map_func[func] = node
        return node

    def _viz_unit(self, unit: VizExec) -> DartFuncNode:
        # check cache
        if unit in self.map_unit:
            return self.map_unit[unit]

        # build the item
        node = self._viz_func(unit.cur)

        # cache
        self.map_unit[unit] = node
        return node

    def _viz_task(self, task: VizTask) -> DartTaskTree:
        # check cache
        if task in self.map_task:
            return self.map_task[task]

        # build the model
        model = QStandardItemModel()
        model.setHorizontalHeaderLabels([task.title()])

        base = model.invisibleRootItem()
        for unit in task.children:
            base.appendRow(self._viz_unit(unit))

        # link model to tree
        tree = DartTaskTree(self, task)

        tree.setModel(model)
        tree.setFont(QFont('Courier'))
        tree.setVerticalScrollMode(QAbstractItemView.ScrollPerItem)
        tree.finish_initialization()

        # cache
        self.map_task[task] = tree
        return tree

    # events handlers
    def _on_collapse_all_clicked(self) -> None:
        for tree in self.map_task.values():
            tree.collapseAll()

    def _expand_one_point(
            self, pos: str
    ) -> Optional[Union[VizItem, VizFunc, VizTask]]:
        seq = None  # type: Optional[int]
        clk = None  # type: Optional[int]

        try:
            # parse the input
            tok = pos.split('-')
            if len(tok) == 3:
                ptid, seq, clk = int(tok[0]), int(tok[1]), int(tok[2])
            elif len(tok) == 2:
                ptid, seq = int(tok[0]), int(tok[1])
            elif len(tok) == 1:
                ptid = int(tok[0])
            else:
                raise RuntimeError('Invalid position: {}'.format(pos))

        except Exception as ex:
            pop_warning(str(ex))
            return None

        # expand whole task
        task = self.pack.tasks[ptid]
        tree = self.map_task[task]
        if seq is None:
            tree.expandAll()
            return None

        # expand whole unit
        unit = task.children[seq]
        node = self.map_unit[unit]
        if clk is None:
            tree.expandRecursively(node.index())
            return node.func

        # expand until child
        item = unit.children[clk]
        node = self.map_item[item]
        while node is not None:
            tree.expand(node.index())
            node = node.parent()

        return item

    def _on_expand_clicked(self) -> None:
        text = self.textin_expand.text().strip()
        for i in text.split(';'):
            i = i.strip()
            self._expand_one_point(i)

    def _on_plot_async_changed(self) -> None:
        self.show_async = self.chkbox_plot_async.isChecked()

        # force hide all async overlays
        for i in self.inst_async:
            i.overlay.hide()

    def should_item_display(self, item: VizItem) -> bool:
        # TODO (remove this blacklist)
        if isinstance(
                item, (VizItemOrderPublish, VizItemOrderSubscribe)
        ):
            return False

        if isinstance(
                item, (VizItemOrderDeposit, VizItemOrderConsume,
                       VizItemQueueArrive, VizItemQueueNotify)
        ):
            return self.show_order

        if isinstance(
                item, (VizItemLockAcquire, VizItemLockRelease)
        ):
            return self.show_lock

        if isinstance(
                item, (VizItemMemAlloc, VizItemMemFree)
        ):
            return self.show_slab

        if isinstance(
                item, (VizItemMemRead, VizItemMemWrite)
        ):
            return self.show_mem

        if isinstance(
                item, (VizItemExecPause, VizItemExecResume,
                       VizItemFuncEnter, VizItemFuncExit, VizItemCFGBlock)
        ):
            return self.show_flow

        return True

    def _toggle_item_display(
            self, checkbox: QCheckBox, types: Tuple[Type[VizItem], ...]
    ) -> bool:
        hidden = not checkbox.isChecked()
        for item, node in self.map_item.items():
            # never hide marked items
            if item in self.marks:
                continue

            if isinstance(item, types):
                index = node.index()
                self.map_task[item.task].setRowHidden(
                    index.row(), index.parent(), hidden
                )

        self.update()
        return not hidden

    def _on_plot_order_changed(self) -> None:
        self.show_order = self._toggle_item_display(
            self.chkbox_plot_order,
            (VizItemOrderDeposit, VizItemOrderConsume,
             VizItemQueueArrive, VizItemQueueNotify)
        )

    def _on_plot_lock_changed(self) -> None:
        self.show_lock = self._toggle_item_display(
            self.chkbox_plot_lock,
            (VizItemLockAcquire, VizItemLockRelease)
        )

    def _on_plot_slab_changed(self) -> None:
        self.show_slab = self._toggle_item_display(
            self.chkbox_plot_slab,
            (VizItemMemAlloc, VizItemMemFree)
        )

    def _on_plot_mem_changed(self) -> None:
        self.show_mem = self._toggle_item_display(
            self.chkbox_plot_mem,
            (VizItemMemRead, VizItemMemWrite)
        )

    def _on_plot_flow_changed(self) -> None:
        self.show_flow = self._toggle_item_display(
            self.chkbox_plot_flow,
            (VizItemExecPause, VizItemExecResume,
             VizItemFuncEnter, VizItemFuncExit, VizItemCFGBlock)
        )

    def _on_plot_trace_changed(self) -> None:
        hidden = self.chkbox_plot_trace.isChecked()

        # collect function nodes
        funcs = set()  # type: Set[VizFunc]

        for item in self.marks:
            node_item = self.map_item[item]

            node_func = node_item.parent()
            while node_func is not None:
                funcs.add(node_func.func)
                node_func = node_func.parent()

        # toggle unrelated items
        for item, node_item in self.map_item.items():
            if node_item.parent().func in funcs:
                continue

            # async and order items should always be displayed
            if isinstance(item, (
                    VizItemForkRegister, VizItemForkCancel,
                    VizItemJoinArrive, VizItemJoinPass,
                    VizItemCtxtRun,
                    VizItemOrderDeposit, VizItemOrderConsume,
                    VizItemMark, VizItemStep
            )):
                continue

            # now toggle the rest
            index = node_item.index()
            if hidden or self.should_item_display(item):
                self.map_task[item.task].setRowHidden(
                    index.row(), index.parent(), hidden
                )

        # hide unrelated func
        for func, node_func in self.map_func.items():
            if func in funcs:
                continue

            node_func.setEnabled(not hidden)

        # save the states
        self.show_trace = not hidden

    def _on_plot_error_changed(self) -> None:
        hidden = not self.chkbox_plot_error.isChecked()
        for item, node in self.map_item.items():
            # never hide marked items
            if item in self.marks:
                continue

            # ignore items without error
            if len(item.error) == 0:
                continue

            # never hide items that should be displayed
            if self.should_item_display(item):
                continue

            # only search in expanded units
            tree = self.map_task[item.task]
            base = self.map_func[item.unit.stack[0]]
            if not tree.isExpanded(base.index()):
                continue

            # toggle the display
            index = node.index()
            self.map_task[item.task].setRowHidden(
                index.row(), index.parent(), hidden
            )

            # expand the node and its parents
            nval = node.parent()
            while nval is not None:
                tree.expand(nval.index())
                nval = nval.parent()

        self.update()

    # mark manipulation
    def add_mark(self, item: VizItem) -> None:
        self.marks.add(item)
        node = self.map_item[item]
        node.setBackground(QBrush(Qt.yellow))

    def del_mark(self, item: VizItem) -> None:
        if item not in self.marks:
            pop_warning('Mark already cleared')
            return

        self.marks.remove(item)
        node = self.map_item[item]
        node.setBackground(QBrush(Qt.white))


class DartGraph(object):

    def __init__(
            self,
            pack: VizPack, opts: Set[VizPoint],
            limit_src: Dict[VizJointType, Optional[int]],
            limit_dst: Dict[VizJointType, Optional[int]],
    ) -> None:
        super().__init__()

        # basics
        self.pack = pack

        # identify scope to display
        total_nodes = set(opts)
        total_edges = {}  # type: Dict[Tuple[VizPoint, VizPoint], VizJointType]

        for p in opts:
            _, nodes, edges = self.pack.scope_with_edge(
                self.pack.get_unit(p), limit_src, limit_dst
            )
            total_nodes.update(nodes)
            total_edges.update(edges)

        # build the graph
        self.graph = Digraph('DART', directory='/tmp', engine='dot')

        # arrange per-ptid ordering (node)
        task_point = {}  # type: Dict[int, Set[VizPoint]]
        for point in total_nodes:
            if point.ptid not in task_point:
                task_point[point.ptid] = {point}
            else:
                task_point[point.ptid].add(point)

        # arrange per-ptid ordering (edge)
        task_joint = {
        }  # type: Dict[int, Dict[Tuple[VizPoint, VizPoint], VizJointType]]
        for k, v in total_edges.items():
            src, dst = k
            assert src in total_nodes
            assert dst in total_nodes

            if src.ptid == dst.ptid:
                if src.ptid not in task_joint:
                    task_joint[src.ptid] = {k: v}
                else:
                    task_joint[src.ptid][k] = v

        # add task group
        ptid_set = set(task_point.keys())
        assert ptid_set.issuperset(set(task_joint.keys()))

        for ptid in sorted(ptid_set):
            with self.graph.subgraph(name='cluster_{}'.format(ptid)) as c:
                # set attrs
                c.attr(color='blue')
                c.attr(label='Task {}'.format(ptid))

                # add nodes
                series = {}  # type: Dict[int, Set[VizPoint]]
                for point in task_point[ptid]:
                    item = self.pack.get_item(point)
                    if point in opts:
                        c.node(
                            str(point),
                            label='[{}] {} {}'.format(
                                str(point), item.icon(), item.desc()
                            ),
                            style='filled',
                            color='yellow',
                        )
                    else:
                        c.node(
                            str(point),
                            label='[{}] {} {}'.format(
                                str(point), item.icon(), item.desc()
                            )
                        )

                    # also collect same-unit points
                    if point.seq not in series:
                        series[point.seq] = {point}
                    else:
                        series[point.seq].add(point)

                # add edges
                if ptid in task_joint:
                    for edge, kind in task_joint[ptid].items():
                        src, dst = edge
                        c.edge(
                            str(src), str(dst),
                            label=kind.name,
                            color=DartGraph.get_edge_color(kind),
                        )

                # add fallthroughs
                for pset in series.values():
                    ptrs = sorted(pset)
                    size = len(ptrs)
                    if size == 1:
                        continue

                    for p1, p2 in zip(range(0, size - 1, 1), range(1, size, 1)):
                        if not (ptrs[p1], ptrs[p2]) in total_edges:
                            c.edge(str(ptrs[p1]), str(ptrs[p2]))

        # add cross-task edges
        for k, v in total_edges.items():
            src, dst = k

            # only add the main graph
            if src.ptid != dst.ptid:
                self.graph.edge(
                    str(src), str(dst),
                    label=v.name,
                    color=DartGraph.get_edge_color(v),
                )

        # save the do file
        self.graph.save()

    @staticmethod
    def get_edge_color(kind: VizJointType) -> str:
        if kind == VizJointType.FORK:
            return 'gold'
        elif kind == VizJointType.JOIN:
            return 'green'
        elif kind == VizJointType.EMBED:
            return 'cyan'
        elif kind == VizJointType.QUEUE:
            return 'grey'
        elif kind == VizJointType.ORDER:
            return 'magenta'
        elif kind == VizJointType.FIFO:
            return 'brown'
        else:
            raise RuntimeError('Invalid edge type')

    def show(self) -> None:
        execute(['xdot', '/tmp/DART.gv'])


def rerun_analysis(ledger: str) -> None:
    # find filename
    temp = os.path.join(os.path.dirname(ledger), 'console')
    i = 0
    while True:
        path = os.path.join(temp + '.{}'.format(i))
        if not os.path.exists(path):
            break
        i += 1

    # parse the ledger
    runtime = VizRuntime()
    try:
        runtime.process(ledger)
    except Exception as ex:
        with open(os.path.join(path + '-error'), 'w') as t:
            t.write(repr(ex))
            t.write('\n-------- EXCEPTION --------\n')
            traceback.print_tb(sys.exc_info()[2], file=t)

    # save the console
    console = '\n'.join(runtime.records)
    with open(path, 'w') as f:
        f.write(console)

    # save the races
    runtime.dump_races(path + '-racer')


def main(argv: List[str]) -> int:
    # setup argument parser
    parser = ArgumentParser()

    parser.add_argument(
        'input',
        help='Path to the ledger file'
    )

    # generic settings
    parser.add_argument(
        '-c', '--clean', action='store_true',
        help='Clear existing results'
    )

    # actions
    subs = parser.add_subparsers(dest='cmd')

    # analyze
    subs.add_parser(
        'analyze',
        help='Analyze the ledger',
    )

    # graph
    sub_graph = subs.add_parser(
        'graph',
        help='Plot the graphr',
    )
    sub_graph.add_argument(
        '-s', '--select', action='append', default=[],
        help='Selected ptid-seq-clk to show'
    )
    sub_graph.add_argument(
        '-d', '--depth', type=str, required=True,
        help='Depth of the trace (configuration file)'
    )

    # trace
    sub_trace = subs.add_parser(
        'trace',
        help='Plot the trace',
    )
    sub_trace.add_argument(
        '-s', '--select', action='append', default=[],
        help='Selected ptid-seq-clk to show'
    )

    # parse
    args = parser.parse_args(argv)

    # action: analysis
    if args.cmd == 'analyze':
        rerun_analysis(args.input)
        return 0

    # cache
    cache = os.path.join(os.path.dirname(args.input), 'visual')
    if not os.path.exists(cache) or args.clean:
        runtime = VizRuntime()
        runtime.process(args.input)
        pack = VizPack(runtime.tasks)
        pack.save(cache)

    else:
        pack = VizPack.load(cache)

    # positions
    opts = set(VizPoint.parse(i) for i in args.select)

    # action: trace
    if args.cmd == 'trace':
        app = QApplication([])

        widget = DartWidget(pack, opts)
        widget.resize(1000, 1800)
        widget.show()

        return cast(int, app.exec_())

    # depth config
    with open(args.depth) as f:
        data = json.load(f)

    limit_src = {VizJointType[k]: v for k, v in data['src'].items()}
    limit_dst = {VizJointType[k]: v for k, v in data['dst'].items()}

    # action: graph
    if args.cmd == 'graph':
        graph = DartGraph(pack, opts, limit_src, limit_dst)
        graph.show()
        return 0

    # no valid action chosen
    parser.print_help()
    return -1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
