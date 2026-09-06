"""Exif tag parsing.

An Exif block is a miniature TIFF file: a two-byte byte-order mark, a
magic number, and then a chain of Image File Directories (IFDs), each
holding a flat list of (tag, type, count, value-or-offset) entries. We
only walk IFD0 and, if present, the Exif sub-IFD it points to - that
covers the tags most cameras actually write.
"""
from __future__ import annotations

import dataclasses
import struct
from typing import Any, Dict


class ExifParseError(ValueError):
    """Raised when a block claims to be Exif/TIFF data but isn't well-formed."""


# Tag id -> human readable name, for the tags we bother decoding. This is
# deliberately a small subset of the Exif spec, not the whole registry.
TAG_NAMES = {
    0x010F: "Make",
    0x0110: "Model",
    0x0112: "Orientation",
    0x011A: "XResolution",
    0x011B: "YResolution",
    0x0128: "ResolutionUnit",
    0x0131: "Software",
    0x0132: "DateTime",
    0x8769: "ExifIFDPointer",
    0x829A: "ExposureTime",
    0x829D: "FNumber",
    0x8827: "ISOSpeedRatings",
    0x9003: "DateTimeOriginal",
    0xA002: "PixelXDimension",
    0xA003: "PixelYDimension",
}

# Exif type id -> (struct format char, size in bytes per element).
_TYPE_FORMATS = {
    1: ("B", 1),    # BYTE
    2: ("B", 1),    # ASCII (decoded separately, as a string)
    3: ("H", 2),    # SHORT
    4: ("I", 4),    # LONG
    5: ("II", 8),   # RATIONAL: numerator, denominator
    7: ("B", 1),    # UNDEFINED
    9: ("i", 4),    # SLONG
    10: ("ii", 8),  # SRATIONAL
}


@dataclasses.dataclass
class ExifData:
    byte_order: str  # "little" or "big"
    tags: Dict[str, Any]


def parse(block: bytes) -> ExifData:
    if len(block) < 8:
        raise ExifParseError("TIFF header is truncated (%d bytes)" % len(block))

    if block[:2] == b"II":
        endian = "<"
        byte_order = "little"
    elif block[:2] == b"MM":
        endian = ">"
        byte_order = "big"
    else:
        raise ExifParseError("bad byte-order mark %r" % (block[:2],))

    magic = struct.unpack(endian + "H", block[2:4])[0]
    if magic != 42:
        raise ExifParseError("bad TIFF magic number %d (expected 42)" % magic)

    ifd0_offset = struct.unpack(endian + "I", block[4:8])[0]
    tags: Dict[str, Any] = {}
    _read_ifd(block, ifd0_offset, endian, tags)
    return ExifData(byte_order=byte_order, tags=tags)


def _read_ifd(block: bytes, offset: int, endian: str, out: Dict[str, Any]) -> None:
    if offset <= 0 or offset + 2 > len(block):
        return
    count = struct.unpack(endian + "H", block[offset:offset + 2])[0]
    entry_start = offset + 2
    for i in range(count):
        entry_off = entry_start + i * 12
        if entry_off + 12 > len(block):
            break
        tag_id, type_id, value_count = struct.unpack(
            endian + "HHI", block[entry_off:entry_off + 8]
        )
        raw_value_field = block[entry_off + 8:entry_off + 12]

        fmt = _TYPE_FORMATS.get(type_id)
        if fmt is None:
            continue  # unsupported type (e.g. DOUBLE) - skip rather than guess
        _, elem_size = fmt
        total_size = elem_size * value_count
        if total_size == 0:
            continue

        if total_size <= 4:
            data = raw_value_field[:total_size]
        else:
            value_offset = struct.unpack(endian + "I", raw_value_field)[0]
            if value_offset + total_size > len(block):
                continue
            data = block[value_offset:value_offset + total_size]

        value = _decode_value(data, type_id, value_count, endian)

        if tag_id == 0x8769 and isinstance(value, int):
            _read_ifd(block, value, endian, out)
            continue

        name = TAG_NAMES.get(tag_id)
        if name is not None:
            out[name] = value


def _decode_value(data: bytes, type_id: int, count: int, endian: str):
    if type_id == 2:  # ASCII, null-terminated
        return data.split(b"\x00", 1)[0].decode("ascii", errors="replace")

    fmt_char, elem_size = _TYPE_FORMATS[type_id]
    values = []
    for i in range(count):
        chunk = data[i * elem_size:(i + 1) * elem_size]
        if type_id in (5, 10):  # RATIONAL / SRATIONAL
            num, den = struct.unpack(endian + fmt_char, chunk)
            values.append(num / den if den else float("nan"))
        else:
            values.append(struct.unpack(endian + fmt_char, chunk)[0])
    return values[0] if count == 1 else values
