from typing import cast, Any, NamedTuple, Type, Tuple, List, Dict, Optional

import os
import pickle
import itertools

from enum import Enum

from spec_basis import Field, Arg, Ret, Lego, Syscall, SyscallGroup, \
    NodeType, PathType, FdType, DirFdType
from spec_const import \
    SPEC_SYSCALL_GROUP_WEIGHT_TOTAL, \
    SPEC_RAND_SIZE_MAX, \
    SPEC_RAND_COUNT_MAX, \
    SPEC_RAND_OFFSET_MIN, SPEC_RAND_OFFSET_MAX, \
    SPEC_FD_LIMIT_MAX, \
    SPEC_AT_FDCWD
from spec_random import SPEC_RANDOM
from spec_extract import Extractor
from spec_lego_pointer import LegoPointer
from spec_lego_simple import LegoSimple
from spec_lego_struct import LegoStruct
from spec_lego_vector import LegoVector
from spec_type_buf import \
    KindSendBufRange, \
    KindRecvBufData
from spec_type_fd import \
    KindSendFd, KindSendFdExt, KindSendFdRes, \
    KindRecvFd
from spec_type_int import \
    KindSendIntConst, KindSendIntRange, KindSendIntFlag, \
    KindRecvIntData
from spec_type_len import \
    KindSendLen
from spec_type_path import \
    KindSendPath, KindSendPathExt, \
    PathMutationStrategy
from spec_type_str import \
    KindSendStrConst, KindSendStrRange, \
    KindRecvStrData
from util_bean import BeanRef


class ModPack(NamedTuple):
    name: str
    conf: List[int]


class Spec(object):

    def __init__(self, extractor: Extractor) -> None:
        # extractions
        extractor.extract()
        self.Info_syscalls = extractor.extract_syscalls()
        self.Info_flags = extractor.extract_flags()
        self.Info_sizes = extractor.extract_sizes()

        # syscalls
        self.Syscalls = [
            self.syscall_open(),
            self.syscall_openat(),
            self.syscall_creat(),
            self.syscall_close(),

            self.syscall_mkdir(),
            self.syscall_mkdirat(),

            self.syscall_read(),
            self.syscall_readv(),
            self.syscall_pread64(),

            self.syscall_write(),
            self.syscall_writev(),
            self.syscall_pwrite64(),

            self.syscall_lseek(),
            self.syscall_truncate(),
            self.syscall_ftruncate(),
            self.syscall_fallocate(),

            self.syscall_getdents(),
            self.syscall_getdents64(),

            self.syscall_readlink(),
            self.syscall_readlinkat(),

            self.syscall_access(),
            self.syscall_faccessat(),

            self.syscall_stat(),
            self.syscall_lstat(),
            self.syscall_fstat(),
            self.syscall_newfstatat(),

            self.syscall_chmod(),
            self.syscall_fchmod(),
            self.syscall_fchmodat(),

            self.syscall_link(),
            self.syscall_linkat(),
            self.syscall_symlink(),
            self.syscall_symlinkat(),

            self.syscall_unlink(),
            self.syscall_unlinkat(),
            self.syscall_rmdir(),

            self.syscall_rename(),
            self.syscall_renameat2(),

            self.syscall_dup(),
            self.syscall_dup2(),
            self.syscall_dup3(),

            self.syscall_splice(),
            self.syscall_sendfile(),

            self.syscall_fsync(),
            self.syscall_fdatasync(),
            self.syscall_syncfs(),
            self.syscall_sync_file_range(),

            self.syscall_fadvise64(),
            self.syscall_readahead(),
        ]

        # precalls
        self.Precalls = [
            self.precall_mkdir_dir_foo(),
            self.precall_open_dir_foo(),
            self.precall_dup2_fd_of_dir_foo(),

            self.precall_creat_file_bar(),
            self.precall_dup2_fd_of_file_bar(),

            self.precall_mknod_generic_baz(),
            self.precall_open_generic_baz(),
            self.precall_dup2_fd_of_generic_baz(),

            self.precall_link_link_bar(),
            self.precall_open_link_bar(),
            self.precall_dup2_fd_of_link_bar(),

            self.precall_symlink_sym_foo(),
            self.precall_open_sym_foo(),
            self.precall_dup2_fd_of_sym_foo(),
        ]

        # finalize
        for syscall in self.Precalls:
            assert syscall.ready()

        for syscall_group in self.Syscalls:
            syscall_group.finalize()

    # interface
    def precall_sequence(self) -> List[Syscall]:
        items = [i.clone() for i in self.Precalls]
        for i in items:
            i.link()
            i.check()

        return items

    def syscall_generate(self) -> Syscall:
        group = SPEC_RANDOM.choice(self.Syscalls)

        opts = list(group.opts.keys())
        vals = [group.opts[i] for i in opts]

        syscall = SPEC_RANDOM.choices(opts, weights=vals, k=1)[0].clone()
        syscall.link()
        syscall.check()

        return syscall

    # utils: field
    def _build_field(
            self,
            name: str,
            tyid: str,
            hold: str,
            lego: Lego,
    ) -> Field:
        return Field.build(
            name=name,
            tyid=tyid,
            size=self.Info_sizes['{}.{}'.format(hold, name)],
            lego=lego,
        )

    # utils: arg
    def _build_arg(
            self,
            name: str,
            tyid: str,
            lego: Lego,
    ) -> Arg:
        return Arg.build(
            name=name,
            tyid=tyid,
            size=self.Info_sizes[tyid],
            lego=lego,
        )

    # utils: ret
    def _build_ret(
            self,
            tyid: str,
            lego: Lego,
    ) -> Ret:
        return Ret.build(
            tyid=tyid,
            size=self.Info_sizes[tyid],
            lego=lego,
        )

    # utils: syscall
    def _build_syscall(self, name: str) -> Syscall:
        sys = Syscall()
        sys.snum = self.Info_syscalls[name.split('$')[0]]
        sys.name = name
        sys.args = []
        return sys

    def _build_derived_syscall(
            self,
            base: Syscall,
            name: str,
            mods: List[Tuple[int, Lego]],
            retm: Optional[Lego],
    ) -> Syscall:
        child = base.clone()
        child.name = base.name + '$' + name

        for m in mods:
            arg = child.args[m[0]]
            child.args[m[0]] = self._build_arg(arg.name, arg.tyid, m[1])

        if retm is not None:
            child.retv = self._build_ret(base.retv.tyid, retm)

        child.link()
        child.check()
        return child

    # ks: int_range
    def ks_int_i8(self) -> KindSendIntRange:
        return KindSendIntRange.build(bits=8, signed=True)

    def ks_int_u8(self) -> KindSendIntRange:
        return KindSendIntRange.build(bits=8, signed=False)

    def ks_int_i16(self) -> KindSendIntRange:
        return KindSendIntRange.build(bits=16, signed=True)

    def ks_int_u16(self) -> KindSendIntRange:
        return KindSendIntRange.build(bits=16, signed=False)

    def ks_int_i32(self) -> KindSendIntRange:
        return KindSendIntRange.build(bits=32, signed=True)

    def ks_int_u32(self) -> KindSendIntRange:
        return KindSendIntRange.build(bits=32, signed=False)

    def ks_int_i64(self) -> KindSendIntRange:
        return KindSendIntRange.build(bits=64, signed=True)

    def ks_int_u64(self) -> KindSendIntRange:
        return KindSendIntRange.build(bits=64, signed=False)

    def ks_int_off64(self) -> KindSendIntRange:
        return KindSendIntRange.build(
            bits=64, signed=True,
            val_min=SPEC_RAND_OFFSET_MIN,
            val_max=SPEC_RAND_OFFSET_MAX
        )

    # ks: int_const
    def ks_int_const_i8(self, val: int) -> KindSendIntConst:
        return KindSendIntConst.build(
            bits=8,
            signed=True,
            val_const=val,
        )

    def ks_int_const_u8(self, val: int) -> KindSendIntConst:
        return KindSendIntConst.build(
            bits=8,
            signed=False,
            val_const=val,
        )

    def ks_int_const_i16(self, val: int) -> KindSendIntConst:
        return KindSendIntConst.build(
            bits=16,
            signed=True,
            val_const=val,
        )

    def ks_int_const_u16(self, val: int) -> KindSendIntConst:
        return KindSendIntConst.build(
            bits=16,
            signed=False,
            val_const=val,
        )

    def ks_int_const_i32(self, val: int) -> KindSendIntConst:
        return KindSendIntConst.build(
            bits=32,
            signed=True,
            val_const=val,
        )

    def ks_int_const_u32(self, val: int) -> KindSendIntConst:
        return KindSendIntConst.build(
            bits=32,
            signed=False,
            val_const=val,
        )

    def ks_int_const_i64(self, val: int) -> KindSendIntConst:
        return KindSendIntConst.build(
            bits=64,
            signed=True,
            val_const=val,
        )

    def ks_int_const_u64(self, val: int) -> KindSendIntConst:
        return KindSendIntConst.build(
            bits=64,
            signed=False,
            val_const=val,
        )

    def ks_int_const_AT_FDCWD(self) -> KindSendIntConst:
        return KindSendIntConst.build(
            bits=32,
            signed=True,
            val_const=SPEC_AT_FDCWD,
        )

    # ks: int_range
    def ks_int_range_i8(self, vmin: int, vmax: int) -> KindSendIntRange:
        return KindSendIntRange.build(
            bits=8,
            signed=True,
            val_min=vmin,
            val_max=vmax,
        )

    def ks_int_range_u8(self, vmin: int, vmax: int) -> KindSendIntRange:
        return KindSendIntRange.build(
            bits=8,
            signed=False,
            val_min=vmin,
            val_max=vmax,
        )

    def ks_int_range_i16(self, vmin: int, vmax: int) -> KindSendIntRange:
        return KindSendIntRange.build(
            bits=16,
            signed=True,
            val_min=vmin,
            val_max=vmax,
        )

    def ks_int_range_u16(self, vmin: int, vmax: int) -> KindSendIntRange:
        return KindSendIntRange.build(
            bits=16,
            signed=False,
            val_min=vmin,
            val_max=vmax,
        )

    def ks_int_range_i32(self, vmin: int, vmax: int) -> KindSendIntRange:
        return KindSendIntRange.build(
            bits=32,
            signed=True,
            val_min=vmin,
            val_max=vmax,
        )

    def ks_int_range_u32(self, vmin: int, vmax: int) -> KindSendIntRange:
        return KindSendIntRange.build(
            bits=32,
            signed=False,
            val_min=vmin,
            val_max=vmax,
        )

    def ks_int_range_i64(self, vmin: int, vmax: int) -> KindSendIntRange:
        return KindSendIntRange.build(
            bits=64,
            signed=True,
            val_min=vmin,
            val_max=vmax,
        )

    def ks_int_range_u64(self, vmin: int, vmax: int) -> KindSendIntRange:
        return KindSendIntRange.build(
            bits=64,
            signed=False,
            val_min=vmin,
            val_max=vmax,
        )

    # ks: int_flag
    def ks_int_flag_open(self) -> KindSendIntFlag:
        return KindSendIntFlag.build(
            bits=32, signed=True,
            name='open',
            vals=set(self.Info_flags['open'].values()),
        )

    def ks_int_flag_mode(self) -> KindSendIntFlag:
        return KindSendIntFlag.build(
            bits=32, signed=False,
            name='mode',
            vals=set(self.Info_flags['mode'].values()),
        )

    def ks_int_flag_falloc(self) -> KindSendIntFlag:
        return KindSendIntFlag.build(
            bits=32, signed=True,
            name='falloc',
            vals=set(self.Info_flags['falloc'].values()),
        )

    def ks_int_flag_fadvise(self) -> KindSendIntFlag:
        return KindSendIntFlag.build(
            bits=32, signed=True,
            name='fadvise',
            vals=set(self.Info_flags['fadvise'].values()),
        )

    def ks_int_flag_splice(self) -> KindSendIntFlag:
        return KindSendIntFlag.build(
            bits=32, signed=True,
            name='splice',
            vals=set(self.Info_flags['splice'].values()),
        )

    def ks_int_flag_sync_file_range(self) -> KindSendIntFlag:
        return KindSendIntFlag.build(
            bits=32, signed=True,
            name='sync_file_range',
            vals=set(self.Info_flags['sync_file_range'].values()),
        )

    # ks: int_holder
    def ks_int_h8(self) -> KindSendIntConst:
        return KindSendIntConst.build(bits=8, signed=True, val_const=0)

    def ks_int_h16(self) -> KindSendIntConst:
        return KindSendIntConst.build(bits=16, signed=True, val_const=0)

    def ks_int_h32(self) -> KindSendIntConst:
        return KindSendIntConst.build(bits=32, signed=True, val_const=0)

    def ks_int_h64(self) -> KindSendIntConst:
        return KindSendIntConst.build(bits=64, signed=True, val_const=0)

    # ks: str
    def ks_str(self) -> KindSendStrRange:
        return KindSendStrRange.build()

    # ks: str_holder
    def ks_str_holder(self) -> KindSendStrRange:
        return KindSendStrRange.build(char_set=[chr(0)])

    # ks; str_const
    def ks_str_const(self, val: str) -> KindSendStrConst:
        return KindSendStrConst.build(
            val_const=val,
        )

    # ks: buf
    def ks_buf(self) -> KindSendBufRange:
        return KindSendBufRange.build()

    # ks: buf_holder
    def ks_buf_holder(self) -> KindSendBufRange:
        return KindSendBufRange.build(byte_set=[b'\x00'])

    # ks: path
    def ks_path_generic(self) -> KindSendPath:
        return KindSendPath.build(mark=NodeType.GENERIC)

    def ks_path_file(self) -> KindSendPath:
        return KindSendPath.build(mark=NodeType.FILE)

    def ks_path_dir(self) -> KindSendPath:
        return KindSendPath.build(mark=NodeType.DIR)

    def ks_path_link(self) -> KindSendPath:
        return KindSendPath.build(mark=NodeType.LINK)

    def ks_path_sym(self) -> KindSendPath:
        return KindSendPath.build(mark=NodeType.SYM)

    # ks: path_const
    def ks_path_generic_const(self, val: str) -> KindSendPath:
        return KindSendPath.build(
            segment=self.l_str_const_in(val),
            mark=NodeType.GENERIC,
            strategies={PathMutationStrategy.CREATE_SEGMENT: 1},
        )

    def ks_path_file_const(self, val: str) -> KindSendPath:
        return KindSendPath.build(
            segment=self.l_str_const_in(val),
            mark=NodeType.FILE,
            strategies={PathMutationStrategy.CREATE_SEGMENT: 1},
        )

    def ks_path_dir_const(self, val: str) -> KindSendPath:
        return KindSendPath.build(
            segment=self.l_str_const_in(val),
            mark=NodeType.DIR,
            strategies={PathMutationStrategy.CREATE_SEGMENT: 1},
        )

    def ks_path_link_const(self, val: str) -> KindSendPath:
        return KindSendPath.build(
            segment=self.l_str_const_in(val),
            mark=NodeType.LINK,
            strategies={PathMutationStrategy.CREATE_SEGMENT: 1},
        )

    def ks_path_sym_const(self, val: str) -> KindSendPath:
        return KindSendPath.build(
            segment=self.l_str_const_in(val),
            mark=NodeType.SYM,
            strategies={PathMutationStrategy.CREATE_SEGMENT: 1},
        )

    # ks: path_ext
    def ks_path_ext_generic(self) -> KindSendPathExt:
        return KindSendPathExt.build(mark=NodeType.GENERIC)

    def ks_path_ext_file(self) -> KindSendPathExt:
        return KindSendPathExt.build(mark=NodeType.FILE)

    def ks_path_ext_dir(self) -> KindSendPathExt:
        return KindSendPathExt.build(mark=NodeType.DIR)

    def ks_path_ext_link(self) -> KindSendPathExt:
        return KindSendPathExt.build(mark=NodeType.LINK)

    def ks_path_ext_sym(self) -> KindSendPathExt:
        return KindSendPathExt.build(mark=NodeType.SYM)

    # ks: fd
    def ks_fd_generic(self) -> KindSendFd:
        return KindSendFd.build(mark=NodeType.GENERIC)

    def ks_fd_file(self) -> KindSendFd:
        return KindSendFd.build(mark=NodeType.FILE)

    def ks_fd_dir(self) -> KindSendFd:
        return KindSendFd.build(mark=NodeType.DIR)

    def ks_fd_link(self) -> KindSendFd:
        return KindSendFd.build(mark=NodeType.LINK)

    def ks_fd_sym(self) -> KindSendFd:
        return KindSendFd.build(mark=NodeType.SYM)

    # ks: fd_const
    def ks_fd_generic_const(self, val: int) -> KindSendFd:
        return KindSendFd.build(mark=NodeType.GENERIC, val_const=val)

    def ks_fd_file_const(self, val: int) -> KindSendFd:
        return KindSendFd.build(mark=NodeType.FILE, val_const=val)

    def ks_fd_dir_const(self, val: int) -> KindSendFd:
        return KindSendFd.build(mark=NodeType.DIR, val_const=val)

    def ks_fd_link_const(self, val: int) -> KindSendFd:
        return KindSendFd.build(mark=NodeType.LINK, val_const=val)

    def ks_fd_sym_const(self, val: int) -> KindSendFd:
        return KindSendFd.build(mark=NodeType.SYM, val_const=val)

    # ks: fd_ext
    def ks_fd_ext_generic(self) -> KindSendFdExt:
        return KindSendFdExt.build(mark=NodeType.GENERIC)

    def ks_fd_ext_file(self) -> KindSendFdExt:
        return KindSendFdExt.build(mark=NodeType.FILE)

    def ks_fd_ext_dir(self) -> KindSendFdExt:
        return KindSendFdExt.build(mark=NodeType.DIR)

    def ks_fd_ext_link(self) -> KindSendFdExt:
        return KindSendFdExt.build(mark=NodeType.LINK)

    def ks_fd_ext_sym(self) -> KindSendFdExt:
        return KindSendFdExt.build(mark=NodeType.SYM)

    # ks: fd_res
    def ks_fd_res_generic(self) -> KindSendFdRes:
        return KindSendFdRes.build(mark=NodeType.GENERIC)

    def ks_fd_res_file(self) -> KindSendFdRes:
        return KindSendFdRes.build(mark=NodeType.FILE)

    def ks_fd_res_dir(self) -> KindSendFdRes:
        return KindSendFdRes.build(mark=NodeType.DIR)

    def ks_fd_res_link(self) -> KindSendFdRes:
        return KindSendFdRes.build(mark=NodeType.LINK)

    def ks_fd_res_sym(self) -> KindSendFdRes:
        return KindSendFdRes.build(mark=NodeType.SYM)

    # ks: len
    def ks_len_u8(self, ptr: LegoPointer) -> KindSendLen:
        return KindSendLen.build(bits=8, ptr=BeanRef[LegoPointer](ptr))

    def ks_len_u16(self, ptr: LegoPointer) -> KindSendLen:
        return KindSendLen.build(bits=16, ptr=BeanRef[LegoPointer](ptr))

    def ks_len_u32(self, ptr: LegoPointer) -> KindSendLen:
        return KindSendLen.build(bits=32, ptr=BeanRef[LegoPointer](ptr))

    def ks_len_u64(self, ptr: LegoPointer) -> KindSendLen:
        return KindSendLen.build(bits=64, ptr=BeanRef[LegoPointer](ptr))

    # kr: int_data
    def kr_int_i8(self) -> KindRecvIntData:
        return KindRecvIntData.build(bits=8, signed=True)

    def kr_int_u8(self) -> KindRecvIntData:
        return KindRecvIntData.build(bits=8, signed=False)

    def kr_int_i16(self) -> KindRecvIntData:
        return KindRecvIntData.build(bits=16, signed=True)

    def kr_int_u16(self) -> KindRecvIntData:
        return KindRecvIntData.build(bits=16, signed=False)

    def kr_int_i32(self) -> KindRecvIntData:
        return KindRecvIntData.build(bits=32, signed=True)

    def kr_int_u32(self) -> KindRecvIntData:
        return KindRecvIntData.build(bits=32, signed=False)

    def kr_int_i64(self) -> KindRecvIntData:
        return KindRecvIntData.build(bits=64, signed=True)

    def kr_int_u64(self) -> KindRecvIntData:
        return KindRecvIntData.build(bits=64, signed=False)

    # kr: str
    def kr_str(self) -> KindRecvStrData:
        return KindRecvStrData.build()

    # kr: buf
    def kr_buf(self) -> KindRecvBufData:
        return KindRecvBufData.build()

    # kr: fd
    def kr_fd_generic(self) -> KindRecvFd:
        return KindRecvFd.build(mark=NodeType.GENERIC)

    def kr_fd_file(self) -> KindRecvFd:
        return KindRecvFd.build(mark=NodeType.FILE)

    def kr_fd_dir(self) -> KindRecvFd:
        return KindRecvFd.build(mark=NodeType.DIR)

    def kr_fd_link(self) -> KindRecvFd:
        return KindRecvFd.build(mark=NodeType.LINK)

    def kr_fd_sym(self) -> KindRecvFd:
        return KindRecvFd.build(mark=NodeType.SYM)

    # l_simple: int_range (in)
    def l_int_i8_in(self) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_int_i8()
        )

    def l_int_u8_in(self) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_int_u8()
        )

    def l_int_i16_in(self) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_int_i16()
        )

    def l_int_u16_in(self) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_int_u16()
        )

    def l_int_i32_in(self) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_int_i32()
        )

    def l_int_u32_in(self) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_int_u32()
        )

    def l_int_i64_in(self) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_int_i64()
        )

    def l_int_u64_in(self) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_int_u64()
        )

    def l_int_off64_in(self) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_int_off64()
        )

    # l_simple: int_holder (out) (w/ in-holder)
    def l_int_i8_out(self) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_int_h8(),
            kind_recv=self.kr_int_i8(),
        )

    def l_int_u8_out(self) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_int_h8(),
            kind_recv=self.kr_int_u8(),
        )

    def l_int_i16_out(self) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_int_h16(),
            kind_recv=self.kr_int_i16(),
        )

    def l_int_u16_out(self) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_int_h16(),
            kind_recv=self.kr_int_u16(),
        )

    def l_int_i32_out(self) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_int_h32(),
            kind_recv=self.kr_int_i32(),
        )

    def l_int_u32_out(self) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_int_h32(),
            kind_recv=self.kr_int_u32(),
        )

    def l_int_i64_out(self) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_int_h64(),
            kind_recv=self.kr_int_i64(),
        )

    def l_int_u64_out(self) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_int_h64(),
            kind_recv=self.kr_int_u64(),
        )

    # l_simple: int (r)
    def l_int_i8_r(self) -> LegoSimple:
        return LegoSimple.build(
            kind_recv=self.kr_int_i8(),
        )

    def l_int_u8_r(self) -> LegoSimple:
        return LegoSimple.build(
            kind_recv=self.kr_int_u8(),
        )

    def l_int_i16_r(self) -> LegoSimple:
        return LegoSimple.build(
            kind_recv=self.kr_int_i16(),
        )

    def l_int_u16_r(self) -> LegoSimple:
        return LegoSimple.build(
            kind_recv=self.kr_int_u16(),
        )

    def l_int_i32_r(self) -> LegoSimple:
        return LegoSimple.build(
            kind_recv=self.kr_int_i32(),
        )

    def l_int_u32_r(self) -> LegoSimple:
        return LegoSimple.build(
            kind_recv=self.kr_int_u32(),
        )

    def l_int_i64_r(self) -> LegoSimple:
        return LegoSimple.build(
            kind_recv=self.kr_int_i64(),
        )

    def l_int_u64_r(self) -> LegoSimple:
        return LegoSimple.build(
            kind_recv=self.kr_int_u64(),
        )

    # l_simple: int_const (int)
    def l_int_const_i8_in(self, val: int) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_int_const_i8(val)
        )

    def l_int_const_u8_in(self, val: int) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_int_const_u8(val)
        )

    def l_int_const_i16_in(self, val: int) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_int_const_i16(val)
        )

    def l_int_const_u16_in(self, val: int) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_int_const_u16(val)
        )

    def l_int_const_i32_in(self, val: int) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_int_const_i32(val)
        )

    def l_int_const_u32_in(self, val: int) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_int_const_u32(val)
        )

    def l_int_const_i64_in(self, val: int) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_int_const_i64(val)
        )

    def l_int_const_u64_in(self, val: int) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_int_const_u64(val)
        )

    def l_int_const_AT_FDCWD_in(self) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_int_const_AT_FDCWD()
        )

    # l_simple: int_range (in)
    def l_int_range_i8_in(self, vmin: int, vmax: int) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_int_range_i8(vmin, vmax)
        )

    def l_int_range_u8_in(self, vmin: int, vmax: int) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_int_range_u8(vmin, vmax)
        )

    def l_int_range_i16_in(self, vmin: int, vmax: int) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_int_range_i16(vmin, vmax)
        )

    def l_int_range_u16_in(self, vmin: int, vmax: int) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_int_range_u16(vmin, vmax)
        )

    def l_int_range_i32_in(self, vmin: int, vmax: int) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_int_range_i32(vmin, vmax)
        )

    def l_int_range_u32_in(self, vmin: int, vmax: int) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_int_range_u32(vmin, vmax)
        )

    def l_int_range_i64_in(self, vmin: int, vmax: int) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_int_range_i64(vmin, vmax)
        )

    def l_int_range_u64_in(self, vmin: int, vmax: int) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_int_range_u64(vmin, vmax)
        )

    # l_simple: int_flag (in)
    def l_int_flag_open_in(self) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_int_flag_open()
        )

    def l_int_flag_mode_in(self) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_int_flag_mode()
        )

    def l_int_flag_falloc_in(self) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_int_flag_falloc()
        )

    def l_int_flag_fadvise_in(self) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_int_flag_fadvise()
        )

    def l_int_flag_splice_in(self) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_int_flag_splice()
        )

    def l_int_flag_sync_file_range_in(self) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_int_flag_sync_file_range()
        )

    # l_ptr: int_off (in)
    def l_ptr_int_off64_in(self) -> LegoPointer:
        return LegoPointer.build(
            memv=BeanRef[Lego](self.l_int_off64_in())
        )

    # l_simple: str (in)
    def l_str_in(self) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_str()
        )

    def l_str_out(self) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_str_holder(),
            kind_recv=self.kr_str(),
        )

    # l_simple str_const (in)
    def l_str_const_in(self, val: str) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_str_const(val)
        )

    # l_ptr: str (in)
    def l_ptr_str_in(self) -> LegoPointer:
        return LegoPointer.build(
            memv=BeanRef[Lego](self.l_str_in())
        )

    def l_ptr_str_out(self) -> LegoPointer:
        return LegoPointer.build(
            memv=BeanRef[Lego](self.l_str_out())
        )

    # l_simple: buf (in)
    def l_buf_in(self) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_buf()
        )

    def l_buf_out(self) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_buf_holder(),
            kind_recv=self.kr_buf(),
        )

    # l_ptr: buf (in)
    def l_ptr_buf_in(self) -> LegoPointer:
        return LegoPointer.build(
            memv=BeanRef[Lego](self.l_buf_in())
        )

    # l_ptr: buf (out)
    def l_ptr_buf_out(self) -> LegoPointer:
        return LegoPointer.build(
            memv=BeanRef[Lego](self.l_buf_out())
        )

    # l_simple: path (in)
    def l_path_generic_in(self) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_path_generic()
        )

    def l_path_file_in(self) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_path_file()
        )

    def l_path_dir_in(self) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_path_dir()
        )

    def l_path_link_in(self) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_path_link()
        )

    def l_path_sym_in(self) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_path_sym()
        )

    # l_simple: path_const (in)
    def l_path_generic_const_in(self, val: str) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_path_generic_const(val)
        )

    def l_path_file_const_in(self, val: str) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_path_file_const(val)
        )

    def l_path_dir_const_in(self, val: str) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_path_dir_const(val)
        )

    def l_path_link_const_in(self, val: str) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_path_link_const(val)
        )

    def l_path_sym_const_in(self, val: str) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_path_sym_const(val)
        )

    # l_ptr: path (in)
    def l_ptr_path_generic_in(self) -> LegoPointer:
        return LegoPointer.build(
            memv=BeanRef[Lego](self.l_path_generic_in())
        )

    def l_ptr_path_file_in(self) -> LegoPointer:
        return LegoPointer.build(
            memv=BeanRef[Lego](self.l_path_file_in())
        )

    def l_ptr_path_dir_in(self) -> LegoPointer:
        return LegoPointer.build(
            memv=BeanRef[Lego](self.l_path_dir_in())
        )

    def l_ptr_path_link_in(self) -> LegoPointer:
        return LegoPointer.build(
            memv=BeanRef[Lego](self.l_path_link_in())
        )

    def l_ptr_path_sym_in(self) -> LegoPointer:
        return LegoPointer.build(
            memv=BeanRef[Lego](self.l_path_sym_in())
        )

    # l_ptr: path_const (in)
    def l_ptr_path_generic_const_in(
            self, val: str, null: bool = False
    ) -> LegoPointer:
        return LegoPointer.build(
            memv=BeanRef[Lego](self.l_path_generic_const_in(val)),
            null=null
        )

    def l_ptr_path_file_const_in(
            self, val: str, null: bool = False
    ) -> LegoPointer:
        return LegoPointer.build(
            memv=BeanRef[Lego](self.l_path_file_const_in(val)),
            null=null
        )

    def l_ptr_path_dir_const_in(
            self, val: str, null: bool = False
    ) -> LegoPointer:
        return LegoPointer.build(
            memv=BeanRef[Lego](self.l_path_dir_const_in(val)),
            null=null
        )

    def l_ptr_path_link_const_in(
            self, val: str, null: bool = False
    ) -> LegoPointer:
        return LegoPointer.build(
            memv=BeanRef[Lego](self.l_path_link_const_in(val)),
            null=null
        )

    def l_ptr_path_sym_const_in(
            self, val: str, null: bool = False
    ) -> LegoPointer:
        return LegoPointer.build(
            memv=BeanRef[Lego](self.l_path_sym_const_in(val)),
            null=null
        )

    # l_simple: path_ext (in)
    def l_path_ext_generic_in(self) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_path_ext_generic()
        )

    def l_path_ext_file_in(self) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_path_ext_file()
        )

    def l_path_ext_dir_in(self) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_path_ext_dir()
        )

    def l_path_ext_link_in(self) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_path_ext_link()
        )

    def l_path_ext_sym_in(self) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_path_ext_sym()
        )

    # l_ptr: path_ext (in)
    def l_ptr_path_ext_generic_in(self, null: bool = True) -> LegoPointer:
        return LegoPointer.build(
            memv=BeanRef[Lego](self.l_path_ext_generic_in()),
            null=null
        )

    def l_ptr_path_ext_file_in(self, null: bool = True) -> LegoPointer:
        return LegoPointer.build(
            memv=BeanRef[Lego](self.l_path_ext_file_in()),
            null=null
        )

    def l_ptr_path_ext_dir_in(self, null: bool = True) -> LegoPointer:
        return LegoPointer.build(
            memv=BeanRef[Lego](self.l_path_ext_dir_in()),
            null=null
        )

    def l_ptr_path_ext_link_in(self, null: bool = True) -> LegoPointer:
        return LegoPointer.build(
            memv=BeanRef[Lego](self.l_path_ext_link_in()),
            null=null
        )

    def l_ptr_path_ext_sym_in(self, null: bool = True) -> LegoPointer:
        return LegoPointer.build(
            memv=BeanRef[Lego](self.l_path_ext_sym_in()),
            null=null
        )

    # l_simple: fd (in)
    def l_fd_generic_in(self) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_fd_generic()
        )

    def l_fd_file_in(self) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_fd_file()
        )

    def l_fd_dir_in(self) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_fd_dir()
        )

    def l_fd_link_in(self) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_fd_link()
        )

    def l_fd_sym_in(self) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_fd_sym()
        )

    # l_simple: fd_const (in)
    def l_fd_generic_const_in(self, val: int) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_fd_generic_const(val)
        )

    def l_fd_file_const_in(self, val: int) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_fd_file_const(val)
        )

    def l_fd_dir_const_in(self, val: int) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_fd_dir_const(val)
        )

    def l_fd_link_const_in(self, val: int) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_fd_link_const(val)
        )

    def l_fd_sym_const_in(self, val: int) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_fd_sym_const(val)
        )

    # l_simple: fd_ext (in)
    def l_fd_ext_generic_in(self) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_fd_ext_generic()
        )

    def l_fd_ext_file_in(self) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_fd_ext_file()
        )

    def l_fd_ext_dir_in(self) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_fd_ext_dir()
        )

    def l_fd_ext_link_in(self) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_fd_ext_link()
        )

    def l_fd_ext_sym_in(self) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_fd_ext_sym()
        )

    # l_simple: fd_res (in)
    def l_fd_res_generic_in(self) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_fd_res_generic()
        )

    def l_fd_res_file_in(self) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_fd_res_file()
        )

    def l_fd_res_dir_in(self) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_fd_res_dir()
        )

    def l_fd_res_link_in(self) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_fd_res_link()
        )

    def l_fd_res_sym_in(self) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_fd_res_sym()
        )

    # l_simple: fd (r)
    def l_fd_generic_r(self) -> LegoSimple:
        return LegoSimple.build(
            kind_recv=self.kr_fd_generic()
        )

    def l_fd_file_r(self) -> LegoSimple:
        return LegoSimple.build(
            kind_recv=self.kr_fd_file()
        )

    def l_fd_dir_r(self) -> LegoSimple:
        return LegoSimple.build(
            kind_recv=self.kr_fd_dir()
        )

    def l_fd_link_r(self) -> LegoSimple:
        return LegoSimple.build(
            kind_recv=self.kr_fd_link()
        )

    def l_fd_sym_r(self) -> LegoSimple:
        return LegoSimple.build(
            kind_recv=self.kr_fd_sym()
        )

    # l_struct: iovec
    def l_struct_iovec_in(self) -> LegoStruct:
        l_iov_base_in = self.l_ptr_buf_in()

        return LegoStruct.build(
            size=self.Info_sizes['struct iovec'],
            fields=[
                self._build_field(
                    'iov_base',
                    'void *',
                    'struct iovec',
                    l_iov_base_in
                ),
                self._build_field(
                    'iov_len',
                    'size_t',
                    'struct iovec',
                    self.l_len_u64_in(l_iov_base_in)
                ),
            ]
        )

    def l_struct_iovec_out(self) -> LegoStruct:
        l_iov_base_out = self.l_ptr_buf_out()

        return LegoStruct.build(
            size=self.Info_sizes['struct iovec'],
            fields=[
                self._build_field(
                    'iov_base',
                    'void *',
                    'struct iovec',
                    l_iov_base_out
                ),
                self._build_field(
                    'iov_len',
                    'size_t',
                    'struct iovec',
                    self.l_len_u64_in(l_iov_base_out)
                ),
            ]
        )

    # l_vector: iovec
    def l_vector_iovec_in(self) -> LegoVector:
        return LegoVector.build(
            cells=[
                self.l_struct_iovec_in()
                for _ in range(SPEC_RAND_COUNT_MAX)
            ],
            cell_min=0,
        )

    def l_vector_iovec_out(self) -> LegoVector:
        return LegoVector.build(
            cells=[
                self.l_struct_iovec_out()
                for _ in range(SPEC_RAND_COUNT_MAX)
            ],
            cell_min=0,
        )

    # l_ptr: vector_iovec
    def l_ptr_vector_iovec_in(self) -> LegoPointer:
        return LegoPointer.build(
            memv=BeanRef[Lego](self.l_vector_iovec_in())
        )

    def l_ptr_vector_iovec_out(self) -> LegoPointer:
        return LegoPointer.build(
            memv=BeanRef[Lego](self.l_vector_iovec_out())
        )

    # l_struct: stat
    def l_struct_stat_out(self) -> LegoStruct:
        return LegoStruct.build(
            size=self.Info_sizes['struct stat'],
            fields=[
                self._build_field(
                    'st_dev',
                    '__kernel_ulong_t',
                    'struct stat',
                    self.l_int_u64_out()
                ),
                self._build_field(
                    'st_ino',
                    '__kernel_ulong_t',
                    'struct stat',
                    self.l_int_u64_out()
                ),
                self._build_field(
                    'st_nlink',
                    '__kernel_ulong_t',
                    'struct stat',
                    self.l_int_u64_out()
                ),
                self._build_field(
                    'st_mode',
                    'unsigned int',
                    'struct stat',
                    self.l_int_u32_out()
                ),
                self._build_field(
                    'st_uid',
                    'unsigned int',
                    'struct stat',
                    self.l_int_u32_out()
                ),
                self._build_field(
                    'st_gid',
                    'unsigned int',
                    'struct stat',
                    self.l_int_u32_out()
                ),
                self._build_field(
                    '__pad0',
                    'unsigned int',
                    'struct stat',
                    self.l_int_u32_out()
                ),
                self._build_field(
                    'st_rdev',
                    '__kernel_ulong_t',
                    'struct stat',
                    self.l_int_u64_out()
                ),
                self._build_field(
                    'st_size',
                    '__kernel_long_t',
                    'struct stat',
                    self.l_int_i64_out()
                ),
                self._build_field(
                    'st_blksize',
                    '__kernel_long_t',
                    'struct stat',
                    self.l_int_i64_out()
                ),
                self._build_field(
                    'st_blocks',
                    '__kernel_long_t',
                    'struct stat',
                    self.l_int_i64_out()
                ),
                self._build_field(
                    'st_atime',
                    '__kernel_ulong_t',
                    'struct stat',
                    self.l_int_u64_out()
                ),
                self._build_field(
                    'st_atime_nsec',
                    '__kernel_ulong_t',
                    'struct stat',
                    self.l_int_u64_out()
                ),
                self._build_field(
                    'st_mtime',
                    '__kernel_ulong_t',
                    'struct stat',
                    self.l_int_u64_out()
                ),
                self._build_field(
                    'st_mtime_nsec',
                    '__kernel_ulong_t',
                    'struct stat',
                    self.l_int_u64_out()
                ),
                self._build_field(
                    'st_ctime',
                    '__kernel_ulong_t',
                    'struct stat',
                    self.l_int_u64_out()
                ),
                self._build_field(
                    'st_ctime_nsec',
                    '__kernel_ulong_t',
                    'struct stat',
                    self.l_int_u64_out()
                ),
                self._build_field(
                    '__unused[0]',
                    '__kernel_long_t',
                    'struct stat',
                    self.l_int_i64_out()
                ),
                self._build_field(
                    '__unused[1]',
                    '__kernel_long_t',
                    'struct stat',
                    self.l_int_i64_out()
                ),
                self._build_field(
                    '__unused[2]',
                    '__kernel_long_t',
                    'struct stat',
                    self.l_int_i64_out()
                ),
            ]
        )

    # l_ptr: stat
    def l_ptr_struct_stat_out(self) -> LegoPointer:
        return LegoPointer.build(
            memv=BeanRef[Lego](self.l_struct_stat_out())
        )

    # l_simple: len (in)
    def l_len_u8_in(self, ptr: LegoPointer) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_len_u8(ptr)
        )

    def l_len_u16_in(self, ptr: LegoPointer) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_len_u16(ptr)
        )

    def l_len_u32_in(self, ptr: LegoPointer) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_len_u32(ptr)
        )

    def l_len_u64_in(self, ptr: LegoPointer) -> LegoSimple:
        return LegoSimple.build(
            kind_send=self.ks_len_u64(ptr)
        )

    # helpers: makers
    def _m_ptr_path_in(self, node: NodeType, path: PathType) -> Lego:
        if (node, path) == (NodeType.GENERIC, PathType.NEW):
            return self.l_ptr_path_generic_in()
        if (node, path) == (NodeType.GENERIC, PathType.EXT):
            return self.l_ptr_path_ext_generic_in()

        if (node, path) == (NodeType.FILE, PathType.NEW):
            return self.l_ptr_path_file_in()
        if (node, path) == (NodeType.FILE, PathType.EXT):
            return self.l_ptr_path_ext_file_in()

        if (node, path) == (NodeType.DIR, PathType.NEW):
            return self.l_ptr_path_dir_in()
        if (node, path) == (NodeType.DIR, PathType.EXT):
            return self.l_ptr_path_ext_dir_in()

        if (node, path) == (NodeType.LINK, PathType.NEW):
            return self.l_ptr_path_link_in()
        if (node, path) == (NodeType.LINK, PathType.EXT):
            return self.l_ptr_path_ext_link_in()

        if (node, path) == (NodeType.SYM, PathType.NEW):
            return self.l_ptr_path_sym_in()
        if (node, path) == (NodeType.SYM, PathType.EXT):
            return self.l_ptr_path_ext_sym_in()

        raise RuntimeError('Invalid types')

    def _m_fd_in(self, node: NodeType, fd: FdType) -> Lego:
        if (node, fd) == (NodeType.GENERIC, FdType.NEW):
            return self.l_fd_generic_in()
        if (node, fd) == (NodeType.GENERIC, FdType.EXT):
            return self.l_fd_ext_generic_in()
        if (node, fd) == (NodeType.GENERIC, FdType.RES):
            return self.l_fd_res_generic_in()

        if (node, fd) == (NodeType.FILE, FdType.NEW):
            return self.l_fd_file_in()
        if (node, fd) == (NodeType.FILE, FdType.EXT):
            return self.l_fd_ext_file_in()
        if (node, fd) == (NodeType.FILE, FdType.RES):
            return self.l_fd_res_file_in()

        if (node, fd) == (NodeType.DIR, FdType.NEW):
            return self.l_fd_dir_in()
        if (node, fd) == (NodeType.DIR, FdType.EXT):
            return self.l_fd_ext_dir_in()
        if (node, fd) == (NodeType.DIR, FdType.RES):
            return self.l_fd_res_dir_in()

        if (node, fd) == (NodeType.LINK, FdType.NEW):
            return self.l_fd_link_in()
        if (node, fd) == (NodeType.LINK, FdType.EXT):
            return self.l_fd_ext_link_in()
        if (node, fd) == (NodeType.LINK, FdType.RES):
            return self.l_fd_res_link_in()

        if (node, fd) == (NodeType.SYM, FdType.NEW):
            return self.l_fd_sym_in()
        if (node, fd) == (NodeType.SYM, FdType.EXT):
            return self.l_fd_ext_sym_in()
        if (node, fd) == (NodeType.SYM, FdType.RES):
            return self.l_fd_res_sym_in()

        raise RuntimeError('Invalid types')

    def _m_dirfd_in(self, dirfd: DirFdType) -> Lego:
        if dirfd == DirFdType.CWD:
            return self.l_int_const_AT_FDCWD_in()
        if dirfd == DirFdType.NEW:
            return self.l_fd_dir_in()
        if dirfd == DirFdType.EXT:
            return self.l_fd_ext_dir_in()
        if dirfd == DirFdType.RES:
            return self.l_fd_res_dir_in()
        raise RuntimeError('Invalid types')

    def _m_fd_r(self, node: NodeType) -> Lego:
        if node == NodeType.GENERIC:
            return self.l_fd_generic_r()
        if node == NodeType.FILE:
            return self.l_fd_file_r()
        if node == NodeType.DIR:
            return self.l_fd_dir_r()
        if node == NodeType.LINK:
            return self.l_fd_link_r()
        if node == NodeType.SYM:
            return self.l_fd_sym_r()
        raise RuntimeError('Invalid types')

    # helpers: refine, multiplex and partition
    def _refine(
            self,
            base: Syscall,
            conf: Tuple[Any, ...],
            args: Dict[int, ModPack],
            retv: Optional[ModPack],
    ) -> Syscall:
        return self._build_derived_syscall(
            base, '_'.join([c.name.lower() for c in conf]),
            [
                (
                    idx, cast(Lego, getattr(self, '_m_' + pack.name)(
                        *[conf[i] for i in pack.conf]
                    ))
                )
                for idx, pack in args.items()
            ],
            cast(Lego, getattr(self, '_m_' + retv.name)(
                *[conf[i] for i in retv.conf]
            )) if retv is not None else None
        )

    def _multiplex(
            self,
            base: Syscall,
            conf: List[Type[Enum]],
            args: Dict[int, ModPack],
            retv: Optional[ModPack],
    ) -> List[Syscall]:
        return [
            self._refine(base, item, args, retv)
            for item in itertools.product(*[[i for i in e] for e in conf])
        ]

    def _partition(
            self,
            base: Syscall,
            opts: List[Syscall],
            dist_base: int,
            dist_opts: List[Tuple[Type, Dict[Any, int]]],
    ) -> SyscallGroup:

        group = SyscallGroup()
        group.set_base(base, dist_base)
        opts_part = SPEC_SYSCALL_GROUP_WEIGHT_TOTAL - dist_base

        opts_sums = 1
        opts_conf = []  # type: List[List[Enum]]
        for item in dist_opts:
            for k in item[1]:
                assert isinstance(k, item[0])

            opts_sums *= sum(item[1].values())
            opts_conf.append([i for i in cast(Type[Enum], item[0])])

        i = 0
        for conf in itertools.product(*opts_conf):
            val = opts_part
            for idx, item in enumerate(dist_opts):
                val *= item[1][conf[idx]]

            group.add_option(opts[i], val / opts_sums)
            i += 1
        assert i == len(opts)

        return group

    # shortcuts: path_in_optional_fd_r
    def _multiplex_ptr_path_in_optional_fd_r(
            self,
            base: Syscall,
            arg_path_in: int,
            ret_fd: bool,
    ) -> List[Syscall]:
        return self._multiplex(
            base,
            [NodeType, PathType],
            {
                arg_path_in: ModPack('ptr_path_in', [0, 1])
            },
            ModPack('fd_r', [0]) if ret_fd else None
        )

    def _partition_ptr_path_in_optional_fd_r(
            self,
            base: Syscall,
            opts: List[Syscall],
            dist_base: int,
            dist_node: Dict[NodeType, int],
            dist_path: Dict[PathType, int],
    ) -> SyscallGroup:
        return self._partition(
            base, opts,
            dist_base,
            [
                (NodeType, dist_node),
                (PathType, dist_path),
            ]
        )

    # shortcuts: fd_in_optional_fd_r
    def _multiplex_fd_in_optional_fd_r(
            self,
            base: Syscall,
            arg_fd_in: int,
            ret_fd: bool,
    ) -> List[Syscall]:
        return self._multiplex(
            base,
            [NodeType, FdType],
            {
                arg_fd_in: ModPack('fd_in', [0, 1])
            },
            ModPack('fd_r', [0]) if ret_fd else None
        )

    def _partition_fd_in_optional_fd_r(
            self,
            base: Syscall,
            opts: List[Syscall],
            dist_base: int,
            dist_node: Dict[NodeType, int],
            dist_fd: Dict[FdType, int],
    ) -> SyscallGroup:
        return self._partition(
            base, opts,
            dist_base,
            [
                (NodeType, dist_node),
                (FdType, dist_fd),
            ]
        )

    # shortcuts: dirfd_in_path_in_optional_fd_r
    def _multiplex_dirfd_in_ptr_path_in_optional_fd_r(
            self,
            base: Syscall,
            arg_dirfd_in: int,
            arg_path_in: int,
            ret_fd: bool,
    ) -> List[Syscall]:
        return self._multiplex(
            base,
            [DirFdType, NodeType, PathType],
            {
                arg_dirfd_in: ModPack('dirfd_in', [0]),
                arg_path_in: ModPack('ptr_path_in', [1, 2])
            },
            ModPack('fd_r', [1]) if ret_fd else None
        )

    def _partition_dirfd_in_ptr_path_in_optional_fd_r(
            self,
            base: Syscall,
            opts: List[Syscall],
            dist_base: int,
            dist_dirfd: Dict[DirFdType, int],
            dist_node: Dict[NodeType, int],
            dist_path: Dict[PathType, int],
    ) -> SyscallGroup:
        return self._partition(
            base, opts,
            dist_base,
            [
                (DirFdType, dist_dirfd),
                (NodeType, dist_node),
                (PathType, dist_path),
            ]
        )

    # shortcuts: fd_in_fd_in
    def _multiplex_fd_in_fd_in(
            self,
            base: Syscall,
            arg_fd1_in: int,
            arg_fd2_in: int,
    ) -> List[Syscall]:
        return self._multiplex(
            base,
            [NodeType, FdType, NodeType, FdType],
            {
                arg_fd1_in: ModPack('fd_in', [0, 1]),
                arg_fd2_in: ModPack('fd_in', [2, 3]),
            },
            None
        )

    def _partition_fd_in_fd_in(
            self,
            base: Syscall,
            opts: List[Syscall],
            dist_base: int,
            dist_node_1: Dict[NodeType, int],
            dist_fd_1: Dict[FdType, int],
            dist_node_2: Dict[NodeType, int],
            dist_fd_2: Dict[FdType, int],
    ) -> SyscallGroup:
        return self._partition(
            base, opts,
            dist_base,
            [
                (NodeType, dist_node_1),
                (FdType, dist_fd_1),
                (NodeType, dist_node_2),
                (FdType, dist_fd_2),
            ]
        )

    # shortcuts: path_in_path_in
    def _multiplex_ptr_path_in_ptr_path_in(
            self,
            base: Syscall,
            arg_path1_in: int,
            arg_path2_in: int,
    ) -> List[Syscall]:
        return self._multiplex(
            base,
            [NodeType, PathType, NodeType, PathType],
            {
                arg_path1_in: ModPack('ptr_path_in', [0, 1]),
                arg_path2_in: ModPack('ptr_path_in', [2, 3]),
            },
            None
        )

    def _partition_ptr_path_in_ptr_path_in(
            self,
            base: Syscall,
            opts: List[Syscall],
            dist_base: int,
            dist_node_1: Dict[NodeType, int],
            dist_path_1: Dict[PathType, int],
            dist_node_2: Dict[NodeType, int],
            dist_path_2: Dict[PathType, int],
    ) -> SyscallGroup:
        return self._partition(
            base, opts,
            dist_base,
            [
                (NodeType, dist_node_1),
                (PathType, dist_path_1),
                (NodeType, dist_node_2),
                (PathType, dist_path_2),
            ]
        )

    # shortcuts: path_in_dirfd_in_path_in
    def _multiplex_ptr_path_in_dirfd_in_ptr_path_in(
            self,
            base: Syscall,
            arg_path1_in: int,
            arg_dirfd_in: int,
            arg_path2_in: int,
    ) -> List[Syscall]:
        return self._multiplex(
            base,
            [NodeType, PathType, DirFdType, NodeType, PathType],
            {
                arg_path1_in: ModPack('ptr_path_in', [0, 1]),
                arg_dirfd_in: ModPack('dirfd_in', [2]),
                arg_path2_in: ModPack('ptr_path_in', [3, 4]),
            },
            None
        )

    def _partition_ptr_path_in_dirfd_in_ptr_path_in(
            self,
            base: Syscall,
            opts: List[Syscall],
            dist_base: int,
            dist_node_1: Dict[NodeType, int],
            dist_path_1: Dict[PathType, int],
            dist_dirfd: Dict[DirFdType, int],
            dist_node_2: Dict[NodeType, int],
            dist_path_2: Dict[PathType, int],
    ) -> SyscallGroup:
        return self._partition(
            base, opts,
            dist_base,
            [
                (NodeType, dist_node_1),
                (PathType, dist_path_1),
                (DirFdType, dist_dirfd),
                (NodeType, dist_node_2),
                (PathType, dist_path_2),
            ]
        )

    # shortcuts: dirfd_in_path_in_dirfd_in_path_in
    def _multiplex_dirfd_in_ptr_path_in_dirfd_in_ptr_path_in(
            self,
            base: Syscall,
            arg_dirfd1_in: int,
            arg_path1_in: int,
            arg_dirfd2_in: int,
            arg_path2_in: int,
    ) -> List[Syscall]:
        return self._multiplex(
            base,
            [DirFdType, NodeType, PathType, DirFdType, NodeType, PathType],
            {
                arg_dirfd1_in: ModPack('dirfd_in', [0]),
                arg_path1_in: ModPack('ptr_path_in', [1, 2]),
                arg_dirfd2_in: ModPack('dirfd_in', [3]),
                arg_path2_in: ModPack('ptr_path_in', [4, 5]),
            },
            None
        )

    def _partition_dirfd_in_ptr_path_in_dirfd_in_ptr_path_in(
            self,
            base: Syscall,
            opts: List[Syscall],
            dist_base: int,
            dist_dirfd_1: Dict[DirFdType, int],
            dist_node_1: Dict[NodeType, int],
            dist_path_1: Dict[PathType, int],
            dist_dirfd_2: Dict[DirFdType, int],
            dist_node_2: Dict[NodeType, int],
            dist_path_2: Dict[PathType, int],
    ) -> SyscallGroup:
        return self._partition(
            base, opts,
            dist_base,
            [
                (DirFdType, dist_dirfd_1),
                (NodeType, dist_node_1),
                (PathType, dist_path_1),
                (DirFdType, dist_dirfd_2),
                (NodeType, dist_node_2),
                (PathType, dist_path_2),
            ]
        )

    # distributions
    def _d_node_normal(self) -> Dict[NodeType, int]:
        return {
            NodeType.GENERIC: 1,
            NodeType.FILE: 3,
            NodeType.DIR: 2,
            NodeType.LINK: 2,
            NodeType.SYM: 2,
        }

    def _d_node_favor_file(self) -> Dict[NodeType, int]:
        return {
            NodeType.GENERIC: 1,
            NodeType.FILE: 6,
            NodeType.DIR: 1,
            NodeType.LINK: 1,
            NodeType.SYM: 1,
        }

    def _d_node_favor_dir(self) -> Dict[NodeType, int]:
        return {
            NodeType.GENERIC: 1,
            NodeType.FILE: 1,
            NodeType.DIR: 6,
            NodeType.LINK: 1,
            NodeType.SYM: 1,
        }

    def _d_node_favor_link(self) -> Dict[NodeType, int]:
        return {
            NodeType.GENERIC: 1,
            NodeType.FILE: 1,
            NodeType.DIR: 1,
            NodeType.LINK: 6,
            NodeType.SYM: 1,
        }

    def _d_node_favor_sym(self) -> Dict[NodeType, int]:
        return {
            NodeType.GENERIC: 1,
            NodeType.FILE: 1,
            NodeType.DIR: 1,
            NodeType.LINK: 1,
            NodeType.SYM: 6,
        }

    def _d_path_normal(self) -> Dict[PathType, int]:
        return {
            PathType.NEW: 1,
            PathType.EXT: 1,
        }

    def _d_path_favor_new(self) -> Dict[PathType, int]:
        return {
            PathType.NEW: 4,
            PathType.EXT: 1,
        }

    def _d_path_favor_ext(self) -> Dict[PathType, int]:
        return {
            PathType.NEW: 1,
            PathType.EXT: 4,
        }

    def _d_fd_favor_ext_and_res(self) -> Dict[FdType, int]:
        return {
            FdType.EXT: 9,
            FdType.RES: 9,
            FdType.NEW: 2,
        }

    def _d_fd_balanced_with_new(self) -> Dict[FdType, int]:
        return {
            FdType.EXT: 3,
            FdType.RES: 3,
            FdType.NEW: 4,
        }

    def _d_dirfd_normal(self) -> Dict[DirFdType, int]:
        return {
            DirFdType.CWD: 3,
            DirFdType.EXT: 3,
            DirFdType.RES: 3,
            DirFdType.NEW: 1,
        }

    # syscalls
    def syscall_open(self) -> SyscallGroup:
        # base
        base = self._build_syscall('open')
        base.args.extend([
            self._build_arg(
                'path', 'char *',
                self.l_ptr_str_in()
            ),
            self._build_arg(
                'flags', 'int',
                self.l_int_flag_open_in(),
            ),
            self._build_arg(
                'modes', 'mode_t',
                self.l_int_flag_mode_in(),
            ),
        ])
        base.retv = self._build_ret(
            'int',
            self.l_int_i32_r()
        )
        base.link()
        base.check()

        # derived
        return self._partition_ptr_path_in_optional_fd_r(
            base,
            self._multiplex_ptr_path_in_optional_fd_r(
                base, 0, ret_fd=True
            ),
            dist_base=0,
            dist_node=self._d_node_normal(),
            dist_path=self._d_path_normal(),
        )

    def syscall_openat(self) -> SyscallGroup:
        # base
        base = self._build_syscall('openat')
        base.args.extend([
            self._build_arg(
                'dirfd', 'int',
                self.l_int_i32_in(),
            ),
            self._build_arg(
                'path', 'char *',
                self.l_ptr_str_in(),
            ),
            self._build_arg(
                'flags', 'int',
                self.l_int_flag_open_in(),
            ),
            self._build_arg(
                'modes', 'mode_t',
                self.l_int_flag_mode_in(),
            ),
        ])
        base.retv = self._build_ret(
            'int',
            self.l_int_i32_r()
        )
        base.link()
        base.check()

        # derived
        return self._partition_dirfd_in_ptr_path_in_optional_fd_r(
            base,
            self._multiplex_dirfd_in_ptr_path_in_optional_fd_r(
                base, 0, 1, ret_fd=True
            ),
            dist_base=0,
            dist_dirfd=self._d_dirfd_normal(),
            dist_node=self._d_node_normal(),
            dist_path=self._d_path_normal(),
        )

    def syscall_creat(self) -> SyscallGroup:
        # base
        base = self._build_syscall('creat')
        base.args.extend([
            self._build_arg(
                'path', 'char *',
                self.l_ptr_str_in()
            ),
            self._build_arg(
                'modes', 'mode_t',
                self.l_int_flag_mode_in(),
            ),
        ])
        base.retv = self._build_ret(
            'int',
            self.l_int_i32_r()
        )
        base.link()
        base.check()

        # derived
        return self._partition_ptr_path_in_optional_fd_r(
            base,
            self._multiplex_ptr_path_in_optional_fd_r(
                base, 0, ret_fd=True
            ),
            dist_base=0,
            dist_node=self._d_node_favor_file(),
            dist_path=self._d_path_favor_new(),
        )

    def syscall_close(self) -> SyscallGroup:
        # base
        base = self._build_syscall('close')
        base.args.extend([
            self._build_arg(
                'fd', 'int',
                self.l_int_i32_in()
            )
        ])
        base.retv = self._build_ret(
            'int',
            self.l_int_i32_r()
        )
        base.link()
        base.check()

        # derived
        return self._partition_fd_in_optional_fd_r(
            base,
            self._multiplex_fd_in_optional_fd_r(
                base, 0, ret_fd=False
            ),
            dist_base=0,
            dist_node=self._d_node_normal(),
            dist_fd=self._d_fd_favor_ext_and_res()
        )

    def syscall_mkdir(self) -> SyscallGroup:
        # base
        base = self._build_syscall('mkdir')
        base.args.extend([
            self._build_arg(
                'path', 'char *',
                self.l_ptr_str_in()
            ),
            self._build_arg(
                'modes', 'mode_t',
                self.l_int_flag_mode_in()
            ),
        ])
        base.retv = self._build_ret(
            'int',
            self.l_int_i32_r()
        )
        base.link()
        base.check()

        # derived
        return self._partition_ptr_path_in_optional_fd_r(
            base,
            self._multiplex_ptr_path_in_optional_fd_r(
                base, 0, ret_fd=False
            ),
            dist_base=0,
            dist_node=self._d_node_favor_dir(),
            dist_path=self._d_path_favor_new()
        )

    def syscall_mkdirat(self) -> SyscallGroup:
        # base
        base = self._build_syscall('mkdirat')
        base.args.extend([
            self._build_arg(
                'dirfd', 'int',
                self.l_int_i32_in(),
            ),
            self._build_arg(
                'path', 'char *',
                self.l_ptr_str_in(),
            ),
            self._build_arg(
                'modes', 'mode_t',
                self.l_int_flag_mode_in(),
            ),
        ])
        base.retv = self._build_ret(
            'int',
            self.l_int_i32_r()
        )
        base.link()
        base.check()

        # derived
        return self._partition_dirfd_in_ptr_path_in_optional_fd_r(
            base,
            self._multiplex_dirfd_in_ptr_path_in_optional_fd_r(
                base, 0, 1, ret_fd=False
            ),
            dist_base=0,
            dist_dirfd=self._d_dirfd_normal(),
            dist_node=self._d_node_favor_dir(),
            dist_path=self._d_path_favor_new()
        )

    def syscall_read(self) -> SyscallGroup:
        # base
        l_buf_out = self.l_ptr_buf_out()

        base = self._build_syscall('read')
        base.args.extend([
            self._build_arg(
                'fd', 'int',
                self.l_int_i32_in()
            ),
            self._build_arg(
                'buf', 'void *',
                l_buf_out
            ),
            self._build_arg(
                'count', 'size_t',
                self.l_len_u64_in(l_buf_out)
            ),
        ])
        base.retv = self._build_ret(
            'ssize_t',
            self.l_int_i64_r()
        )
        base.link()
        base.check()

        # derived
        return self._partition_fd_in_optional_fd_r(
            base,
            self._multiplex_fd_in_optional_fd_r(
                base, 0, ret_fd=False
            ),
            dist_base=0,
            dist_node=self._d_node_favor_file(),
            dist_fd=self._d_fd_favor_ext_and_res()
        )

    def syscall_readv(self) -> SyscallGroup:
        # base
        l_iov_out = self.l_ptr_vector_iovec_out()

        base = self._build_syscall('readv')
        base.args.extend([
            self._build_arg(
                'fd', 'int',
                self.l_int_i32_in()
            ),
            self._build_arg(
                'iov', 'void *',
                l_iov_out
            ),
            self._build_arg(
                'iovcnt', 'int',
                self.l_len_u32_in(l_iov_out)
            ),
        ])
        base.retv = self._build_ret(
            'ssize_t',
            self.l_int_i64_r()
        )
        base.link()
        base.check()

        # derived
        return self._partition_fd_in_optional_fd_r(
            base,
            self._multiplex_fd_in_optional_fd_r(
                base, 0, ret_fd=False
            ),
            dist_base=0,
            dist_node=self._d_node_favor_file(),
            dist_fd=self._d_fd_favor_ext_and_res()
        )

    def syscall_pread64(self) -> SyscallGroup:
        # base
        l_buf_out = self.l_ptr_buf_out()

        base = self._build_syscall('pread64')
        base.args.extend([
            self._build_arg(
                'fd', 'int',
                self.l_int_i32_in()
            ),
            self._build_arg(
                'buf', 'void *',
                l_buf_out
            ),
            self._build_arg(
                'count', 'size_t',
                self.l_len_u64_in(l_buf_out)
            ),
            self._build_arg(
                'offset', 'off_t',
                self.l_int_off64_in()
            )
        ])
        base.retv = self._build_ret(
            'ssize_t',
            self.l_int_i64_r()
        )
        base.link()
        base.check()

        # derived
        return self._partition_fd_in_optional_fd_r(
            base,
            self._multiplex_fd_in_optional_fd_r(
                base, 0, ret_fd=False
            ),
            dist_base=0,
            dist_node=self._d_node_favor_file(),
            dist_fd=self._d_fd_favor_ext_and_res()
        )

    def syscall_write(self) -> SyscallGroup:
        # base
        l_buf_in = self.l_ptr_buf_in()

        base = self._build_syscall('write')
        base.args.extend([
            self._build_arg(
                'fd', 'int',
                self.l_int_i32_in()
            ),
            self._build_arg(
                'buf', 'void *',
                l_buf_in
            ),
            self._build_arg(
                'count', 'size_t',
                self.l_len_u64_in(l_buf_in)
            ),
        ])
        base.retv = self._build_ret(
            'ssize_t',
            self.l_int_i64_r()
        )
        base.link()
        base.check()

        # derived
        return self._partition_fd_in_optional_fd_r(
            base,
            self._multiplex_fd_in_optional_fd_r(
                base, 0, ret_fd=False
            ),
            dist_base=0,
            dist_node=self._d_node_favor_file(),
            dist_fd=self._d_fd_favor_ext_and_res()
        )

    def syscall_writev(self) -> SyscallGroup:
        # base
        l_iov_in = self.l_ptr_vector_iovec_in()

        base = self._build_syscall('writev')
        base.args.extend([
            self._build_arg(
                'fd', 'int',
                self.l_int_i32_in()
            ),
            self._build_arg(
                'iov', 'void *',
                l_iov_in
            ),
            self._build_arg(
                'iovcnt', 'int',
                self.l_len_u32_in(l_iov_in)
            ),
        ])
        base.retv = self._build_ret(
            'ssize_t',
            self.l_int_i64_r()
        )
        base.link()
        base.check()

        # derived
        return self._partition_fd_in_optional_fd_r(
            base,
            self._multiplex_fd_in_optional_fd_r(
                base, 0, ret_fd=False
            ),
            dist_base=0,
            dist_node=self._d_node_favor_file(),
            dist_fd=self._d_fd_favor_ext_and_res()
        )

    def syscall_pwrite64(self) -> SyscallGroup:
        # base
        l_buf_in = self.l_ptr_buf_in()

        base = self._build_syscall('pwrite64')
        base.args.extend([
            self._build_arg(
                'fd', 'int',
                self.l_int_i32_in()
            ),
            self._build_arg(
                'buf', 'void *',
                l_buf_in
            ),
            self._build_arg(
                'count', 'size_t',
                self.l_len_u64_in(l_buf_in)
            ),
            self._build_arg(
                'offset', 'off_t',
                self.l_int_off64_in()
            )
        ])
        base.retv = self._build_ret(
            'ssize_t',
            self.l_int_i64_r()
        )
        base.link()
        base.check()

        # derived
        return self._partition_fd_in_optional_fd_r(
            base,
            self._multiplex_fd_in_optional_fd_r(
                base, 0, ret_fd=False
            ),
            dist_base=0,
            dist_node=self._d_node_favor_file(),
            dist_fd=self._d_fd_favor_ext_and_res()
        )

    def syscall_lseek(self) -> SyscallGroup:
        # base
        base = self._build_syscall('lseek')
        base.args.extend([
            self._build_arg(
                'fd', 'int',
                self.l_int_i32_in()
            ),
            self._build_arg(
                'offset', 'off_t',
                self.l_int_off64_in()
            ),
            self._build_arg(
                'whence', 'int',
                self.l_int_range_i32_in(0, 5)
            )
        ])
        base.retv = self._build_ret(
            'off_t',
            self.l_int_i64_r()
        )
        base.link()
        base.check()

        # derived
        return self._partition_fd_in_optional_fd_r(
            base,
            self._multiplex_fd_in_optional_fd_r(
                base, 0, ret_fd=False
            ),
            dist_base=0,
            dist_node=self._d_node_favor_file(),
            dist_fd=self._d_fd_favor_ext_and_res()
        )

    def syscall_truncate(self) -> SyscallGroup:
        # base
        base = self._build_syscall('truncate')
        base.args.extend([
            self._build_arg(
                'path', 'char *',
                self.l_ptr_str_in()
            ),
            self._build_arg(
                'offset', 'off_t',
                self.l_int_off64_in()
            ),
        ])
        base.retv = self._build_ret(
            'int',
            self.l_int_i32_r()
        )
        base.link()
        base.check()

        # derived
        return self._partition_ptr_path_in_optional_fd_r(
            base,
            self._multiplex_ptr_path_in_optional_fd_r(
                base, 0, ret_fd=False
            ),
            dist_base=0,
            dist_node=self._d_node_favor_file(),
            dist_path=self._d_path_favor_ext(),
        )

    def syscall_ftruncate(self) -> SyscallGroup:
        # base
        base = self._build_syscall('ftruncate')
        base.args.extend([
            self._build_arg(
                'fd', 'int',
                self.l_int_i32_in()
            ),
            self._build_arg(
                'offset', 'off_t',
                self.l_int_off64_in()
            ),
        ])
        base.retv = self._build_ret(
            'int',
            self.l_int_i32_r()
        )
        base.link()
        base.check()

        # derived
        return self._partition_fd_in_optional_fd_r(
            base,
            self._multiplex_fd_in_optional_fd_r(
                base, 0, ret_fd=False
            ),
            dist_base=0,
            dist_node=self._d_node_favor_file(),
            dist_fd=self._d_fd_favor_ext_and_res(),
        )

    def syscall_fallocate(self) -> SyscallGroup:
        # base
        base = self._build_syscall('fallocate')
        base.args.extend([
            self._build_arg(
                'fd', 'int',
                self.l_int_i32_in()
            ),
            self._build_arg(
                'mode', 'int',
                self.l_int_flag_falloc_in()
            ),
            self._build_arg(
                'offset', 'off_t',
                self.l_int_off64_in()
            ),
            self._build_arg(
                'count', 'size_t',
                self.l_int_range_u64_in(0, SPEC_RAND_SIZE_MAX)
            )
        ])
        base.retv = self._build_ret(
            'int',
            self.l_int_i32_r()
        )
        base.link()
        base.check()

        # derived
        return self._partition_fd_in_optional_fd_r(
            base,
            self._multiplex_fd_in_optional_fd_r(
                base, 0, ret_fd=False
            ),
            dist_base=0,
            dist_node=self._d_node_favor_file(),
            dist_fd=self._d_fd_favor_ext_and_res(),
        )

    def syscall_getdents(self) -> SyscallGroup:
        # base
        l_buf_out = self.l_ptr_buf_out()

        base = self._build_syscall('getdents')
        base.args.extend([
            self._build_arg(
                'fd', 'int',
                self.l_int_i32_in()
            ),
            self._build_arg(
                'buf', 'void *',
                l_buf_out
            ),
            self._build_arg(
                'count', 'size_t',
                self.l_len_u64_in(l_buf_out)
            ),
        ])
        base.retv = self._build_ret(
            'ssize_t',
            self.l_int_i64_r()
        )
        base.link()
        base.check()

        # derived
        return self._partition_fd_in_optional_fd_r(
            base,
            self._multiplex_fd_in_optional_fd_r(
                base, 0, ret_fd=False
            ),
            dist_base=0,
            dist_node=self._d_node_favor_dir(),
            dist_fd=self._d_fd_favor_ext_and_res()
        )

    def syscall_getdents64(self) -> SyscallGroup:
        # base
        l_buf_out = self.l_ptr_buf_out()

        base = self._build_syscall('getdents64')
        base.args.extend([
            self._build_arg(
                'fd', 'int',
                self.l_int_i32_in()
            ),
            self._build_arg(
                'buf', 'void *',
                l_buf_out
            ),
            self._build_arg(
                'count', 'size_t',
                self.l_len_u64_in(l_buf_out)
            ),
        ])
        base.retv = self._build_ret(
            'ssize_t',
            self.l_int_i64_r()
        )
        base.link()
        base.check()

        # derived
        return self._partition_fd_in_optional_fd_r(
            base,
            self._multiplex_fd_in_optional_fd_r(
                base, 0, ret_fd=False
            ),
            dist_base=0,
            dist_node=self._d_node_favor_dir(),
            dist_fd=self._d_fd_favor_ext_and_res()
        )

    def syscall_readlink(self) -> SyscallGroup:
        # base
        l_buf_out = self.l_ptr_buf_out()

        base = self._build_syscall('readlink')
        base.args.extend([
            self._build_arg(
                'path', 'char *',
                self.l_ptr_str_in()
            ),
            self._build_arg(
                'buf', 'void *',
                l_buf_out
            ),
            self._build_arg(
                'count', 'size_t',
                self.l_len_u64_in(l_buf_out)
            ),
        ])
        base.retv = self._build_ret(
            'ssize_t',
            self.l_int_i64_r()
        )
        base.link()
        base.check()

        # derived
        return self._partition_ptr_path_in_optional_fd_r(
            base,
            self._multiplex_ptr_path_in_optional_fd_r(
                base, 0, ret_fd=False
            ),
            dist_base=0,
            dist_node=self._d_node_favor_sym(),
            dist_path=self._d_path_favor_ext(),
        )

    def syscall_readlinkat(self) -> SyscallGroup:
        # base
        l_buf_out = self.l_ptr_buf_out()

        base = self._build_syscall('readlinkat')
        base.args.extend([
            self._build_arg(
                'dirfd', 'int',
                self.l_int_i32_in(),
            ),
            self._build_arg(
                'path', 'char *',
                self.l_ptr_str_in()
            ),
            self._build_arg(
                'buf', 'void *',
                l_buf_out
            ),
            self._build_arg(
                'count', 'size_t',
                self.l_len_u64_in(l_buf_out)
            ),
        ])
        base.retv = self._build_ret(
            'ssize_t',
            self.l_int_i64_r()
        )
        base.link()
        base.check()

        # derived
        return self._partition_dirfd_in_ptr_path_in_optional_fd_r(
            base,
            self._multiplex_dirfd_in_ptr_path_in_optional_fd_r(
                base, 0, 1, ret_fd=False
            ),
            dist_base=0,
            dist_dirfd=self._d_dirfd_normal(),
            dist_node=self._d_node_favor_sym(),
            dist_path=self._d_path_favor_ext(),
        )

    def syscall_access(self) -> SyscallGroup:
        # base
        base = self._build_syscall('access')
        base.args.extend([
            self._build_arg(
                'path', 'char *',
                self.l_ptr_str_in()
            ),
            self._build_arg(
                'mode', 'int',
                self.l_int_range_u32_in(0, 7),
            )
        ])
        base.retv = self._build_ret(
            'int',
            self.l_int_i32_r()
        )
        base.link()
        base.check()

        # derived
        return self._partition_ptr_path_in_optional_fd_r(
            base,
            self._multiplex_ptr_path_in_optional_fd_r(
                base, 0, ret_fd=False
            ),
            dist_base=0,
            dist_node=self._d_node_normal(),
            dist_path=self._d_path_favor_ext(),
        )

    def syscall_faccessat(self) -> SyscallGroup:
        # base
        base = self._build_syscall('faccessat')
        base.args.extend([
            self._build_arg(
                'dirfd', 'int',
                self.l_int_i32_in(),
            ),
            self._build_arg(
                'path', 'char *',
                self.l_ptr_str_in(),
            ),
            self._build_arg(
                'modes', 'mode_t',
                self.l_int_range_u32_in(0, 7),
            ),
            self._build_arg(
                'flags', 'int',
                self.l_int_const_i32_in(0)
            )
        ])
        base.retv = self._build_ret(
            'int',
            self.l_int_i32_r()
        )
        base.link()
        base.check()

        # derived
        return self._partition_dirfd_in_ptr_path_in_optional_fd_r(
            base,
            self._multiplex_dirfd_in_ptr_path_in_optional_fd_r(
                base, 0, 1, ret_fd=False
            ),
            dist_base=0,
            dist_dirfd=self._d_dirfd_normal(),
            dist_node=self._d_node_normal(),
            dist_path=self._d_path_favor_ext(),
        )

    def syscall_stat(self) -> SyscallGroup:
        # base
        base = self._build_syscall('stat')
        base.args.extend([
            self._build_arg(
                'path', 'char *',
                self.l_ptr_str_in()
            ),
            self._build_arg(
                'stat', 'void *',
                self.l_ptr_struct_stat_out()
            )
        ])
        base.retv = self._build_ret(
            'int',
            self.l_int_i32_r()
        )
        base.link()
        base.check()

        # derived
        return self._partition_ptr_path_in_optional_fd_r(
            base,
            self._multiplex_ptr_path_in_optional_fd_r(
                base, 0, ret_fd=False
            ),
            dist_base=0,
            dist_node=self._d_node_normal(),
            dist_path=self._d_path_favor_ext(),
        )

    def syscall_lstat(self) -> SyscallGroup:
        # base
        base = self._build_syscall('lstat')
        base.args.extend([
            self._build_arg(
                'path', 'char *',
                self.l_ptr_str_in()
            ),
            self._build_arg(
                'stat', 'void *',
                self.l_ptr_struct_stat_out()
            )
        ])
        base.retv = self._build_ret(
            'int',
            self.l_int_i32_r()
        )
        base.link()
        base.check()

        # derived
        return self._partition_ptr_path_in_optional_fd_r(
            base,
            self._multiplex_ptr_path_in_optional_fd_r(
                base, 0, ret_fd=False
            ),
            dist_base=0,
            dist_node=self._d_node_favor_sym(),
            dist_path=self._d_path_favor_ext(),
        )

    def syscall_fstat(self) -> SyscallGroup:
        # base
        base = self._build_syscall('fstat')
        base.args.extend([
            self._build_arg(
                'fd', 'int',
                self.l_int_i32_in()
            ),
            self._build_arg(
                'stat', 'void *',
                self.l_ptr_struct_stat_out()
            )
        ])
        base.retv = self._build_ret(
            'int',
            self.l_int_i32_r()
        )
        base.link()
        base.check()

        # derived
        return self._partition_fd_in_optional_fd_r(
            base,
            self._multiplex_fd_in_optional_fd_r(
                base, 0, ret_fd=False
            ),
            dist_base=0,
            dist_node=self._d_node_normal(),
            dist_fd=self._d_fd_favor_ext_and_res()
        )

    def syscall_newfstatat(self) -> SyscallGroup:
        # base
        base = self._build_syscall('newfstatat')
        base.args.extend([
            self._build_arg(
                'dirfd', 'int',
                self.l_int_i32_in(),
            ),
            self._build_arg(
                'path', 'char *',
                self.l_ptr_str_in()
            ),
            self._build_arg(
                'stat', 'void *',
                self.l_ptr_struct_stat_out()
            ),
            self._build_arg(
                'flags', 'int',
                self.l_int_const_i32_in(0)
            )
        ])
        base.retv = self._build_ret(
            'int',
            self.l_int_i32_r()
        )
        base.link()
        base.check()

        # derived
        return self._partition_dirfd_in_ptr_path_in_optional_fd_r(
            base,
            self._multiplex_dirfd_in_ptr_path_in_optional_fd_r(
                base, 0, 1, ret_fd=False
            ),
            dist_base=0,
            dist_dirfd=self._d_dirfd_normal(),
            dist_node=self._d_node_normal(),
            dist_path=self._d_path_favor_ext(),
        )

    def syscall_chmod(self) -> SyscallGroup:
        # base
        base = self._build_syscall('chmod')
        base.args.extend([
            self._build_arg(
                'path', 'char *',
                self.l_ptr_str_in()
            ),
            self._build_arg(
                'mode', 'int',
                self.l_int_flag_mode_in()
            )
        ])
        base.retv = self._build_ret(
            'int',
            self.l_int_i32_r()
        )
        base.link()
        base.check()

        # derived
        return self._partition_ptr_path_in_optional_fd_r(
            base,
            self._multiplex_ptr_path_in_optional_fd_r(
                base, 0, ret_fd=False
            ),
            dist_base=0,
            dist_node=self._d_node_normal(),
            dist_path=self._d_path_favor_ext(),
        )

    def syscall_fchmod(self) -> SyscallGroup:
        # base
        base = self._build_syscall('fchmod')
        base.args.extend([
            self._build_arg(
                'fd', 'int',
                self.l_int_i32_in()
            ),
            self._build_arg(
                'mode', 'int',
                self.l_int_flag_mode_in()
            )
        ])
        base.retv = self._build_ret(
            'int',
            self.l_int_i32_r()
        )
        base.link()
        base.check()

        # derived
        return self._partition_fd_in_optional_fd_r(
            base,
            self._multiplex_fd_in_optional_fd_r(
                base, 0, ret_fd=False
            ),
            dist_base=0,
            dist_node=self._d_node_normal(),
            dist_fd=self._d_fd_favor_ext_and_res(),
        )

    def syscall_fchmodat(self) -> SyscallGroup:
        # base
        base = self._build_syscall('fchmodat')
        base.args.extend([
            self._build_arg(
                'dirfd', 'int',
                self.l_int_i32_in(),
            ),
            self._build_arg(
                'path', 'char *',
                self.l_ptr_str_in(),
            ),
            self._build_arg(
                'modes', 'mode_t',
                self.l_int_flag_mode_in(),
            ),
            self._build_arg(
                'flags', 'int',
                self.l_int_const_i32_in(0)
            )
        ])
        base.retv = self._build_ret(
            'int',
            self.l_int_i32_r()
        )
        base.link()
        base.check()

        # derived
        return self._partition_dirfd_in_ptr_path_in_optional_fd_r(
            base,
            self._multiplex_dirfd_in_ptr_path_in_optional_fd_r(
                base, 0, 1, ret_fd=False
            ),
            dist_base=0,
            dist_dirfd=self._d_dirfd_normal(),
            dist_node=self._d_node_normal(),
            dist_path=self._d_path_favor_ext(),
        )

    def syscall_link(self) -> SyscallGroup:
        # base
        base = self._build_syscall('link')
        base.args.extend([
            self._build_arg(
                'oldpath', 'char *',
                self.l_ptr_str_in()
            ),
            self._build_arg(
                'newpath', 'char *',
                self.l_ptr_str_in()
            ),
        ])
        base.retv = self._build_ret(
            'int',
            self.l_int_i32_r()
        )
        base.link()
        base.check()

        # derived
        return self._partition_ptr_path_in_ptr_path_in(
            base,
            self._multiplex_ptr_path_in_ptr_path_in(
                base, 0, 1
            ),
            dist_base=0,
            dist_node_1=self._d_node_favor_file(),
            dist_path_1=self._d_path_favor_ext(),
            dist_node_2=self._d_node_favor_link(),
            dist_path_2=self._d_path_favor_new(),
        )

    def syscall_linkat(self) -> SyscallGroup:
        # base
        base = self._build_syscall('linkat')
        base.args.extend([
            self._build_arg(
                'olddirfd', 'int',
                self.l_int_i32_in(),
            ),
            self._build_arg(
                'oldpath', 'char *',
                self.l_ptr_str_in()
            ),
            self._build_arg(
                'newdirfd', 'int',
                self.l_int_i32_in(),
            ),
            self._build_arg(
                'newpath', 'char *',
                self.l_ptr_str_in()
            ),
            self._build_arg(
                'flags', 'int',
                self.l_int_const_i32_in(0)
            )
        ])
        base.retv = self._build_ret(
            'int',
            self.l_int_i32_r()
        )
        base.link()
        base.check()

        # derived
        return self._partition_dirfd_in_ptr_path_in_dirfd_in_ptr_path_in(
            base,
            self._multiplex_dirfd_in_ptr_path_in_dirfd_in_ptr_path_in(
                base, 0, 1, 2, 3
            ),
            dist_base=0,
            dist_dirfd_1=self._d_dirfd_normal(),
            dist_node_1=self._d_node_favor_file(),
            dist_path_1=self._d_path_favor_ext(),
            dist_dirfd_2=self._d_dirfd_normal(),
            dist_node_2=self._d_node_favor_link(),
            dist_path_2=self._d_path_favor_new(),
        )

    def syscall_symlink(self) -> SyscallGroup:
        # base
        base = self._build_syscall('symlink')
        base.args.extend([
            self._build_arg(
                'oldpath', 'char *',
                self.l_ptr_str_in()
            ),
            self._build_arg(
                'newpath', 'char *',
                self.l_ptr_str_in()
            ),
        ])
        base.retv = self._build_ret(
            'int',
            self.l_int_i32_r()
        )
        base.link()
        base.check()

        # derived
        return self._partition_ptr_path_in_ptr_path_in(
            base,
            self._multiplex_ptr_path_in_ptr_path_in(
                base, 0, 1
            ),
            dist_base=0,
            dist_node_1=self._d_node_normal(),
            dist_path_1=self._d_path_favor_ext(),
            dist_node_2=self._d_node_favor_sym(),
            dist_path_2=self._d_path_favor_new(),
        )

    def syscall_symlinkat(self) -> SyscallGroup:
        # base
        base = self._build_syscall('symlinkat')
        base.args.extend([
            self._build_arg(
                'oldpath', 'char *',
                self.l_ptr_str_in()
            ),
            self._build_arg(
                'dirfd', 'int',
                self.l_int_i32_in(),
            ),
            self._build_arg(
                'newpath', 'char *',
                self.l_ptr_str_in()
            ),
        ])
        base.retv = self._build_ret(
            'int',
            self.l_int_i32_r()
        )
        base.link()
        base.check()

        # derived
        return self._partition_ptr_path_in_dirfd_in_ptr_path_in(
            base,
            self._multiplex_ptr_path_in_dirfd_in_ptr_path_in(
                base, 0, 1, 2
            ),
            dist_base=0,
            dist_node_1=self._d_node_normal(),
            dist_path_1=self._d_path_favor_ext(),
            dist_dirfd=self._d_dirfd_normal(),
            dist_node_2=self._d_node_favor_sym(),
            dist_path_2=self._d_path_favor_new(),
        )

    def syscall_unlink(self) -> SyscallGroup:
        # base
        base = self._build_syscall('unlink')
        base.args.extend([
            self._build_arg(
                'path', 'char *',
                self.l_ptr_str_in()
            ),
        ])
        base.retv = self._build_ret(
            'int',
            self.l_int_i32_r()
        )
        base.link()
        base.check()

        # derived
        return self._partition_ptr_path_in_optional_fd_r(
            base,
            self._multiplex_ptr_path_in_optional_fd_r(
                base, 0, ret_fd=False
            ),
            dist_base=0,
            dist_node=self._d_node_normal(),
            dist_path=self._d_path_favor_ext(),
        )

    def syscall_unlinkat(self) -> SyscallGroup:
        # base
        base = self._build_syscall('unlinkat')
        base.args.extend([
            self._build_arg(
                'dirfd', 'int',
                self.l_int_i32_in(),
            ),
            self._build_arg(
                'path', 'char *',
                self.l_ptr_str_in(),
            ),
            self._build_arg(
                'flags', 'int',
                self.l_int_const_i32_in(0)
            ),
        ])
        base.retv = self._build_ret(
            'int',
            self.l_int_i32_r()
        )
        base.link()
        base.check()

        # derived
        return self._partition_dirfd_in_ptr_path_in_optional_fd_r(
            base,
            self._multiplex_dirfd_in_ptr_path_in_optional_fd_r(
                base, 0, 1, ret_fd=False
            ),
            dist_base=0,
            dist_dirfd=self._d_dirfd_normal(),
            dist_node=self._d_node_normal(),
            dist_path=self._d_path_favor_ext()
        )

    def syscall_rmdir(self) -> SyscallGroup:
        # base
        base = self._build_syscall('rmdir')
        base.args.extend([
            self._build_arg(
                'path', 'char *',
                self.l_ptr_str_in()
            ),
        ])
        base.retv = self._build_ret(
            'int',
            self.l_int_i32_r()
        )
        base.link()
        base.check()

        # derived
        return self._partition_ptr_path_in_optional_fd_r(
            base,
            self._multiplex_ptr_path_in_optional_fd_r(
                base, 0, ret_fd=False
            ),
            dist_base=0,
            dist_node=self._d_node_favor_dir(),
            dist_path=self._d_path_favor_ext(),
        )

    def syscall_rename(self) -> SyscallGroup:
        # base
        base = self._build_syscall('rename')
        base.args.extend([
            self._build_arg(
                'oldpath', 'char *',
                self.l_ptr_str_in()
            ),
            self._build_arg(
                'newpath', 'char *',
                self.l_ptr_str_in()
            ),
        ])
        base.retv = self._build_ret(
            'int',
            self.l_int_i32_r()
        )
        base.link()
        base.check()

        # derived
        return self._partition_ptr_path_in_ptr_path_in(
            base,
            self._multiplex_ptr_path_in_ptr_path_in(
                base, 0, 1
            ),
            dist_base=0,
            dist_node_1=self._d_node_normal(),
            dist_path_1=self._d_path_favor_ext(),
            dist_node_2=self._d_node_normal(),
            dist_path_2=self._d_path_normal(),
        )

    def syscall_renameat2(self) -> SyscallGroup:
        # base
        base = self._build_syscall('renameat2')
        base.args.extend([
            self._build_arg(
                'olddirfd', 'int',
                self.l_int_i32_in(),
            ),
            self._build_arg(
                'oldpath', 'char *',
                self.l_ptr_str_in()
            ),
            self._build_arg(
                'newdirfd', 'int',
                self.l_int_i32_in(),
            ),
            self._build_arg(
                'newpath', 'char *',
                self.l_ptr_str_in()
            ),
            self._build_arg(
                'flags', 'int',
                self.l_int_const_i32_in(0)
            )
        ])
        base.retv = self._build_ret(
            'int',
            self.l_int_i32_r()
        )
        base.link()
        base.check()

        # derived
        return self._partition_dirfd_in_ptr_path_in_dirfd_in_ptr_path_in(
            base,
            self._multiplex_dirfd_in_ptr_path_in_dirfd_in_ptr_path_in(
                base, 0, 1, 2, 3
            ),
            dist_base=0,
            dist_dirfd_1=self._d_dirfd_normal(),
            dist_node_1=self._d_node_normal(),
            dist_path_1=self._d_path_favor_ext(),
            dist_dirfd_2=self._d_dirfd_normal(),
            dist_node_2=self._d_node_normal(),
            dist_path_2=self._d_path_normal(),
        )

    def syscall_dup(self) -> SyscallGroup:
        # base
        base = self._build_syscall('dup')
        base.args.extend([
            self._build_arg(
                'oldfd', 'int',
                self.l_int_i32_in()
            ),
        ])
        base.retv = self._build_ret(
            'int',
            self.l_int_i32_r()
        )
        base.link()
        base.check()

        # derived
        return self._partition_fd_in_optional_fd_r(
            base,
            self._multiplex_fd_in_optional_fd_r(
                base, 0, ret_fd=True
            ),
            dist_base=0,
            dist_node=self._d_node_normal(),
            dist_fd=self._d_fd_favor_ext_and_res(),
        )

    def syscall_dup2(self) -> SyscallGroup:
        # base
        base = self._build_syscall('dup2')
        base.args.extend([
            self._build_arg(
                'oldfd', 'int',
                self.l_int_i32_in()
            ),
            self._build_arg(
                'newfd', 'int',
                self.l_int_i32_in()
            ),
        ])
        base.retv = self._build_ret(
            'int',
            self.l_int_i32_r()
        )
        base.link()
        base.check()

        # derived
        return self._partition_fd_in_fd_in(
            base,
            self._multiplex_fd_in_fd_in(
                base, 0, 1
            ),
            dist_base=0,
            dist_node_1=self._d_node_normal(),
            dist_fd_1=self._d_fd_favor_ext_and_res(),
            dist_node_2=self._d_node_normal(),
            dist_fd_2=self._d_fd_balanced_with_new(),
        )

    def syscall_dup3(self) -> SyscallGroup:
        # base
        base = self._build_syscall('dup3')
        base.args.extend([
            self._build_arg(
                'oldfd', 'int',
                self.l_int_i32_in()
            ),
            self._build_arg(
                'newfd', 'int',
                self.l_int_i32_in()
            ),
            self._build_arg(
                'flags', 'int',
                self.l_int_const_i32_in(0)
            )
        ])
        base.retv = self._build_ret(
            'int',
            self.l_int_i32_r()
        )
        base.link()
        base.check()

        # derived
        return self._partition_fd_in_fd_in(
            base,
            self._multiplex_fd_in_fd_in(
                base, 0, 1
            ),
            dist_base=0,
            dist_node_1=self._d_node_normal(),
            dist_fd_1=self._d_fd_favor_ext_and_res(),
            dist_node_2=self._d_node_normal(),
            dist_fd_2=self._d_fd_balanced_with_new(),
        )

    def syscall_splice(self) -> SyscallGroup:
        # base
        base = self._build_syscall('splice')
        base.args.extend([
            self._build_arg(
                'fd_in', 'int',
                self.l_int_i32_in()
            ),
            self._build_arg(
                'off_in', 'void *',
                self.l_ptr_int_off64_in()
            ),
            self._build_arg(
                'fd_out', 'int',
                self.l_int_i32_in()
            ),
            self._build_arg(
                'off_out', 'void *',
                self.l_ptr_int_off64_in()
            ),
            self._build_arg(
                'flags', 'int',
                self.l_int_flag_splice_in()
            )
        ])
        base.retv = self._build_ret(
            'int',
            self.l_int_i32_r()
        )
        base.link()
        base.check()

        # derived
        return self._partition_fd_in_fd_in(
            base,
            self._multiplex_fd_in_fd_in(
                base, 0, 2
            ),
            dist_base=0,
            dist_node_1=self._d_node_normal(),
            dist_fd_1=self._d_fd_favor_ext_and_res(),
            dist_node_2=self._d_node_normal(),
            dist_fd_2=self._d_fd_favor_ext_and_res(),
        )

    def syscall_sendfile(self) -> SyscallGroup:
        # base
        base = self._build_syscall('sendfile')
        base.args.extend([
            self._build_arg(
                'out_fd', 'int',
                self.l_int_i32_in()
            ),
            self._build_arg(
                'in_fd', 'int',
                self.l_int_i32_in()
            ),
            self._build_arg(
                'offset', 'void *',
                self.l_ptr_int_off64_in()
            ),
            self._build_arg(
                'count', 'size_t',
                self.l_int_range_u64_in(0, SPEC_RAND_SIZE_MAX)
            )
        ])
        base.retv = self._build_ret(
            'ssize_t',
            self.l_int_i64_r()
        )
        base.link()
        base.check()

        # derived
        return self._partition_fd_in_fd_in(
            base,
            self._multiplex_fd_in_fd_in(
                base, 0, 1
            ),
            dist_base=0,
            dist_node_1=self._d_node_normal(),
            dist_fd_1=self._d_fd_favor_ext_and_res(),
            dist_node_2=self._d_node_normal(),
            dist_fd_2=self._d_fd_favor_ext_and_res(),
        )

    def syscall_fsync(self) -> SyscallGroup:
        # base
        base = self._build_syscall('fsync')
        base.args.extend([
            self._build_arg(
                'fd', 'int',
                self.l_int_i32_in()
            ),
        ])
        base.retv = self._build_ret(
            'int',
            self.l_int_i32_r()
        )
        base.link()
        base.check()

        # derived
        return self._partition_fd_in_optional_fd_r(
            base,
            self._multiplex_fd_in_optional_fd_r(
                base, 0, ret_fd=False
            ),
            dist_base=0,
            dist_node=self._d_node_normal(),
            dist_fd=self._d_fd_favor_ext_and_res(),
        )

    def syscall_fdatasync(self) -> SyscallGroup:
        # base
        base = self._build_syscall('fdatasync')
        base.args.extend([
            self._build_arg(
                'fd', 'int',
                self.l_int_i32_in()
            ),
        ])
        base.retv = self._build_ret(
            'int',
            self.l_int_i32_r()
        )
        base.link()
        base.check()

        # derived
        return self._partition_fd_in_optional_fd_r(
            base,
            self._multiplex_fd_in_optional_fd_r(
                base, 0, ret_fd=False
            ),
            dist_base=0,
            dist_node=self._d_node_normal(),
            dist_fd=self._d_fd_favor_ext_and_res(),
        )

    def syscall_syncfs(self) -> SyscallGroup:
        # base
        base = self._build_syscall('syncfs')
        base.args.extend([
            self._build_arg(
                'fd', 'int',
                self.l_int_i32_in()
            ),
        ])
        base.retv = self._build_ret(
            'int',
            self.l_int_i32_r()
        )
        base.link()
        base.check()

        # derived
        return self._partition_fd_in_optional_fd_r(
            base,
            self._multiplex_fd_in_optional_fd_r(
                base, 0, ret_fd=False
            ),
            dist_base=0,
            dist_node=self._d_node_normal(),
            dist_fd=self._d_fd_favor_ext_and_res(),
        )

    def syscall_sync_file_range(self) -> SyscallGroup:
        # base
        base = self._build_syscall('sync_file_range')
        base.args.extend([
            self._build_arg(
                'fd', 'int',
                self.l_int_i32_in()
            ),
            self._build_arg(
                'offset', 'off_t',
                self.l_ptr_int_off64_in()
            ),
            self._build_arg(
                'count', 'size_t',
                self.l_int_range_u64_in(0, SPEC_RAND_SIZE_MAX)
            ),
            self._build_arg(
                'flags', 'int',
                self.l_int_flag_sync_file_range_in()
            )
        ])
        base.retv = self._build_ret(
            'int',
            self.l_int_i32_r()
        )
        base.link()
        base.check()

        # derived
        return self._partition_fd_in_optional_fd_r(
            base,
            self._multiplex_fd_in_optional_fd_r(
                base, 0, ret_fd=False
            ),
            dist_base=0,
            dist_node=self._d_node_normal(),
            dist_fd=self._d_fd_favor_ext_and_res(),
        )

    def syscall_fadvise64(self) -> SyscallGroup:
        # base
        base = self._build_syscall('fadvise64')
        base.args.extend([
            self._build_arg(
                'fd', 'int',
                self.l_int_i32_in()
            ),
            self._build_arg(
                'offset', 'off_t',
                self.l_ptr_int_off64_in()
            ),
            self._build_arg(
                'count', 'size_t',
                self.l_int_range_u64_in(0, SPEC_RAND_SIZE_MAX)
            ),
            self._build_arg(
                'advice', 'int',
                self.l_int_flag_fadvise_in()
            )
        ])
        base.retv = self._build_ret(
            'int',
            self.l_int_i32_r()
        )
        base.link()
        base.check()

        # derived
        return self._partition_fd_in_optional_fd_r(
            base,
            self._multiplex_fd_in_optional_fd_r(
                base, 0, ret_fd=False
            ),
            dist_base=0,
            dist_node=self._d_node_normal(),
            dist_fd=self._d_fd_favor_ext_and_res(),
        )

    def syscall_readahead(self) -> SyscallGroup:
        # base
        base = self._build_syscall('readahead')
        base.args.extend([
            self._build_arg(
                'fd', 'int',
                self.l_int_i32_in()
            ),
            self._build_arg(
                'offset', 'off_t',
                self.l_ptr_int_off64_in()
            ),
            self._build_arg(
                'count', 'size_t',
                self.l_int_range_u64_in(0, SPEC_RAND_SIZE_MAX)
            )
        ])
        base.retv = self._build_ret(
            'ssize_t',
            self.l_int_i64_r()
        )
        base.link()
        base.check()

        # derived
        return self._partition_fd_in_optional_fd_r(
            base,
            self._multiplex_fd_in_optional_fd_r(
                base, 0, ret_fd=False
            ),
            dist_base=0,
            dist_node=self._d_node_normal(),
            dist_fd=self._d_fd_favor_ext_and_res(),
        )

    # precalls
    def precall_mkdir_dir_foo(self) -> Syscall:
        # prep for: path_dir_ext
        base = self._build_syscall('mkdir')
        base.args.extend([
            self._build_arg(
                'path', 'char *',
                self.l_ptr_path_dir_const_in('dir_foo')
            ),
            self._build_arg(
                'modes', 'mode_t',
                self.l_int_const_u32_in(0o777)
            ),
        ])
        base.retv = self._build_ret(
            'int',
            self.l_int_i32_r()
        )
        base.link()
        base.check()

        return base

    def precall_open_dir_foo(self) -> Syscall:
        # prep for: fd_dir_res
        flags = self.Info_flags['open']

        base = self._build_syscall('open')
        base.args.extend([
            self._build_arg(
                'path', 'char *',
                self.l_ptr_path_ext_dir_in(null=False)  # --> dir_foo
            ),
            self._build_arg(
                'flags', 'int',
                self.l_int_const_i32_in(
                    flags['O_DIRECTORY'] | flags['O_RDONLY']
                )
            ),
            self._build_arg(
                'modes', 'mode_t',
                self.l_int_const_u32_in(0o777)
            ),
        ])
        base.retv = self._build_ret(
            'int',
            self.l_fd_dir_r()
        )
        base.link()
        base.check()

        return base

    def precall_dup2_fd_of_dir_foo(self) -> Syscall:
        # prep for: fd_dir_ext
        base = self._build_syscall('dup2')
        base.args.extend([
            self._build_arg(
                'oldfd', 'int',
                self.l_fd_res_dir_in()  # --> fd(dir_foo)
            ),
            self._build_arg(
                'newfd', 'int',
                self.l_fd_dir_const_in(SPEC_FD_LIMIT_MAX - 1)
            ),
        ])
        base.retv = self._build_ret(
            'int',
            self.l_int_i32_r()
        )
        base.link()
        base.check()

        return base

    def precall_creat_file_bar(self) -> Syscall:
        # prep for: path_file_ext, fd_file_res
        base = self._build_syscall('creat')
        base.args.extend([
            self._build_arg(
                'path', 'char *',
                self.l_ptr_path_file_const_in('file_bar')
            ),
            self._build_arg(
                'modes', 'mode_t',
                self.l_int_const_u32_in(0o777)
            ),
        ])
        base.retv = self._build_ret(
            'int',
            self.l_fd_file_r()
        )
        base.link()
        base.check()

        return base

    def precall_dup2_fd_of_file_bar(self) -> Syscall:
        # prep for: fd_file_ext
        base = self._build_syscall('dup2')
        base.args.extend([
            self._build_arg(
                'oldfd', 'int',
                self.l_fd_res_file_in()  # --> fd(file_bar)
            ),
            self._build_arg(
                'newfd', 'int',
                self.l_fd_file_const_in(SPEC_FD_LIMIT_MAX - 2)
            ),
        ])
        base.retv = self._build_ret(
            'int',
            self.l_int_i32_r()
        )
        base.link()
        base.check()

        return base

    def precall_mknod_generic_baz(self) -> Syscall:
        # prep for: path_generic_ext
        base = self._build_syscall('mknod')
        base.args.extend([
            self._build_arg(
                'path', 'char *',
                self.l_ptr_path_generic_const_in('generic_baz')
            ),
            self._build_arg(
                'modes', 'mode_t',
                self.l_int_const_u32_in(0o777)
            ),
            self._build_arg(
                'dev', 'dev_t',
                self.l_int_const_u32_in(0)
            ),
        ])
        base.retv = self._build_ret(
            'int',
            self.l_int_i32_r()
        )
        base.link()
        base.check()

        return base

    def precall_open_generic_baz(self) -> Syscall:
        # prep for: fd_generic_res
        flags = self.Info_flags['open']

        base = self._build_syscall('open')
        base.args.extend([
            self._build_arg(
                'path', 'char *',
                self.l_ptr_path_ext_generic_in(null=False)  # --> generic_baz
            ),
            self._build_arg(
                'flags', 'int',
                self.l_int_const_i32_in(flags['O_PATH'])
            ),
            self._build_arg(
                'modes', 'mode_t',
                self.l_int_const_u32_in(0o777)
            ),
        ])
        base.retv = self._build_ret(
            'int',
            self.l_fd_generic_r()
        )
        base.link()
        base.check()

        return base

    def precall_dup2_fd_of_generic_baz(self) -> Syscall:
        # prep for: fd_generic_ext
        base = self._build_syscall('dup2')
        base.args.extend([
            self._build_arg(
                'oldfd', 'int',
                self.l_fd_res_generic_in()  # --> fd(generic_baz)
            ),
            self._build_arg(
                'newfd', 'int',
                self.l_fd_generic_const_in(SPEC_FD_LIMIT_MAX - 3)
            ),
        ])
        base.retv = self._build_ret(
            'int',
            self.l_int_i32_r()
        )
        base.link()
        base.check()

        return base

    def precall_link_link_bar(self) -> Syscall:
        # prep for: path_link_ext
        base = self._build_syscall('link')
        base.args.extend([
            self._build_arg(
                'oldpath', 'char *',
                self.l_ptr_path_ext_file_in(null=False)  # --> file_bar
            ),
            self._build_arg(
                'newpath', 'char *',
                self.l_ptr_path_link_const_in('link_bar')
            ),
        ])
        base.retv = self._build_ret(
            'int',
            self.l_int_i32_r()
        )
        base.link()
        base.check()

        return base

    def precall_open_link_bar(self) -> Syscall:
        # prep for: fd_link_res
        flags = self.Info_flags['open']

        base = self._build_syscall('open')
        base.args.extend([
            self._build_arg(
                'path', 'char *',
                self.l_ptr_path_ext_link_in(null=False)  # --> link_bar
            ),
            self._build_arg(
                'flags', 'int',
                self.l_int_const_i32_in(flags['O_RDWR'])
            ),
            self._build_arg(
                'modes', 'mode_t',
                self.l_int_const_u32_in(0o777)
            ),
        ])
        base.retv = self._build_ret(
            'int',
            self.l_fd_link_r()
        )
        base.link()
        base.check()

        return base

    def precall_dup2_fd_of_link_bar(self) -> Syscall:
        # prep for: fd_link_ext
        base = self._build_syscall('dup2')
        base.args.extend([
            self._build_arg(
                'oldfd', 'int',
                self.l_fd_res_link_in()  # --> fd(link_bar)
            ),
            self._build_arg(
                'newfd', 'int',
                self.l_fd_link_const_in(SPEC_FD_LIMIT_MAX - 4)
            ),
        ])
        base.retv = self._build_ret(
            'int',
            self.l_int_i32_r()
        )
        base.link()
        base.check()

        return base

    def precall_symlink_sym_foo(self) -> Syscall:
        # prep for: path_sym_ext
        base = self._build_syscall('symlink')
        base.args.extend([
            self._build_arg(
                'oldpath', 'char *',
                self.l_ptr_path_ext_dir_in(null=False)  # --> dir_foo
            ),
            self._build_arg(
                'newpath', 'char *',
                self.l_ptr_path_sym_const_in('sym_foo')
            ),
        ])
        base.retv = self._build_ret(
            'int',
            self.l_int_i32_r()
        )
        base.link()
        base.check()

        return base

    def precall_open_sym_foo(self) -> Syscall:
        # prep for: fd_sym_res
        flags = self.Info_flags['open']

        base = self._build_syscall('open')
        base.args.extend([
            self._build_arg(
                'path', 'char *',
                self.l_ptr_path_ext_sym_in(null=False)  # --> sym_foo
            ),
            self._build_arg(
                'flags', 'int',
                self.l_int_const_i32_in(
                    flags['O_DIRECTORY'] | flags['O_RDONLY']
                )
            ),
            self._build_arg(
                'modes', 'mode_t',
                self.l_int_const_u32_in(0o777)
            ),
        ])
        base.retv = self._build_ret(
            'int',
            self.l_fd_sym_r()
        )
        base.link()
        base.check()

        return base

    def precall_dup2_fd_of_sym_foo(self) -> Syscall:
        # prep for: fd_sym_ext
        base = self._build_syscall('dup2')
        base.args.extend([
            self._build_arg(
                'oldfd', 'int',
                self.l_fd_res_sym_in()  # --> fd(sym_foo)
            ),
            self._build_arg(
                'newfd', 'int',
                self.l_fd_sym_const_in(SPEC_FD_LIMIT_MAX - 5)
            ),
        ])
        base.retv = self._build_ret(
            'int',
            self.l_int_i32_r()
        )
        base.link()
        base.check()

        return base

    @classmethod
    def formulate(cls) -> 'Spec':
        extractor = Extractor()

        cache = os.path.join(extractor.path_info, 'spec')
        if os.path.exists(cache):
            with open(cache, 'rb') as f:
                return cast(Spec, pickle.load(f))

        spec = Spec(extractor)
        with open(cache, 'wb') as f:
            pickle.dump(spec, f)

        return spec
