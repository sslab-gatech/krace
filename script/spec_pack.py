import struct

from spec_const import SPEC_PTR_SIZE


# int
def _get_int_pack_format(bits: int, signed: bool) -> str:
    if (bits, signed) == (8, False):
        return 'B'
    if (bits, signed) == (8, True):
        return 'b'
    if (bits, signed) == (16, False):
        return 'H'
    if (bits, signed) == (16, True):
        return 'h'
    if (bits, signed) == (32, False):
        return 'I'
    if (bits, signed) == (32, True):
        return 'i'
    if (bits, signed) == (64, False):
        return 'Q'
    if (bits, signed) == (64, True):
        return 'q'
    raise RuntimeError('Invalid bits')


def pack_int(val: int, bits: int, signed: bool = True) -> bytes:
    return struct.pack(_get_int_pack_format(bits, signed), val)


# ptr
def pack_ptr(val: int) -> bytes:
    return pack_int(val, SPEC_PTR_SIZE * 8, False)


# str
def pack_str(val: str) -> bytes:
    return struct.pack('{}s'.format(len(val) + 1), val.encode('charmap'))
