"""PNG container parsing.

Walks the chunk stream and pulls out the pieces that matter for
metadata: dimensions and color type from IHDR, embedded text from
tEXt/zTXt/iTXt chunks, and an Exif block from eXIf if one is present.
Like jpeg.py, this never touches the compressed image data (IDAT) -
only chunk framing, so it doesn't need zlib for anything but the
handful of compressed text chunks that use it.
"""
from __future__ import annotations

import dataclasses
import struct
import zlib
from typing import Dict, List, Optional, Tuple

from . import exif as exif_module

SIGNATURE = b"\x89PNG\r\n\x1a\n"

_COLOR_TYPE_NAMES = {
    0: "grayscale",
    2: "truecolor",
    3: "indexed",
    4: "grayscale+alpha",
    6: "truecolor+alpha",
}


class PngParseError(ValueError):
    """Raised when the byte stream does not look like a well-formed PNG."""


@dataclasses.dataclass
class Chunk:
    type: str
    offset: int
    length: int


@dataclasses.dataclass
class PngFile:
    width: Optional[int]
    height: Optional[int]
    bit_depth: Optional[int]
    color_type: Optional[str]
    chunks: List[Chunk]
    text: Dict[str, str]
    exif: Optional[exif_module.ExifData]
    warnings: List[str]


def _read_text_chunk(data: bytes) -> Optional[Tuple[str, str]]:
    if b"\x00" not in data:
        return None
    keyword, text = data.split(b"\x00", 1)
    return keyword.decode("latin-1"), text.decode("latin-1", errors="replace")


def _read_ztxt_chunk(data: bytes) -> Optional[Tuple[str, str]]:
    if b"\x00" not in data:
        return None
    keyword, rest = data.split(b"\x00", 1)
    if len(rest) < 1 or rest[0] != 0:  # only zlib (method 0) is defined
        return None
    try:
        text = zlib.decompress(rest[1:]).decode("latin-1", errors="replace")
    except zlib.error:
        return None
    return keyword.decode("latin-1"), text


def _read_itxt_chunk(data: bytes) -> Optional[Tuple[str, str]]:
    if b"\x00" not in data:
        return None
    keyword, rest = data.split(b"\x00", 1)
    if len(rest) < 2:
        return None
    compression_flag, compression_method = rest[0], rest[1]
    rest = rest[2:]
    if b"\x00" not in rest:
        return None
    _language_tag, rest = rest.split(b"\x00", 1)
    if b"\x00" not in rest:
        return None
    _translated_keyword, text_data = rest.split(b"\x00", 1)
    if compression_flag:
        if compression_method != 0:
            return None
        try:
            text_data = zlib.decompress(text_data)
        except zlib.error:
            return None
    return keyword.decode("latin-1"), text_data.decode("utf-8", errors="replace")


_TEXT_READERS = {
    "tEXt": _read_text_chunk,
    "zTXt": _read_ztxt_chunk,
    "iTXt": _read_itxt_chunk,
}


def parse(data: bytes) -> PngFile:
    if data[:8] != SIGNATURE:
        raise PngParseError("missing PNG signature")

    chunks: List[Chunk] = []
    warnings: List[str] = []
    width = height = bit_depth = color_type = None
    text: Dict[str, str] = {}
    exif_data = None

    pos = 8
    while pos < len(data):
        if pos + 8 > len(data):
            raise PngParseError("truncated chunk header at offset %d" % pos)
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        chunk_type = data[pos + 4:pos + 8]
        try:
            type_name = chunk_type.decode("ascii")
        except UnicodeDecodeError:
            raise PngParseError("chunk type at offset %d is not ASCII" % pos)

        data_start = pos + 8
        data_end = data_start + length
        crc_end = data_end + 4
        if crc_end > len(data):
            raise PngParseError(
                "chunk %r at offset %d claims length %d but file is truncated"
                % (type_name, pos, length)
            )
        if not chunks and type_name != "IHDR":
            raise PngParseError("first chunk is %r, expected IHDR" % type_name)

        payload = data[data_start:data_end]
        declared_crc = struct.unpack(">I", data[data_end:crc_end])[0]
        if zlib.crc32(chunk_type + payload) != declared_crc:
            warnings.append("chunk %r at offset %d has a bad CRC" % (type_name, pos))

        chunks.append(Chunk(type_name, pos, length))

        if type_name == "IHDR" and len(payload) >= 13:
            width, height = struct.unpack(">II", payload[0:8])
            bit_depth = payload[8]
            color_type = _COLOR_TYPE_NAMES.get(payload[9], "unknown (%d)" % payload[9])
        elif type_name in _TEXT_READERS:
            entry = _TEXT_READERS[type_name](payload)
            if entry is not None:
                text[entry[0]] = entry[1]
        elif type_name == "eXIf":
            try:
                exif_data = exif_module.parse(payload)
            except exif_module.ExifParseError as exc:
                warnings.append("could not parse Exif block: %s" % exc)

        pos = crc_end
        if type_name == "IEND":
            break
    else:
        warnings.append("stream ended before an IEND chunk was found")

    return PngFile(
        width=width,
        height=height,
        bit_depth=bit_depth,
        color_type=color_type,
        chunks=chunks,
        text=text,
        exif=exif_data,
        warnings=warnings,
    )
