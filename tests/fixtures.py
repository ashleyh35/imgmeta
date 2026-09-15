"""Handcrafted byte-level fixtures for JPEG/Exif parsing tests.

Everything here is built field by field with struct.pack rather than
pasted in as a binary blob, so a test failure points at which byte
meant what.
"""
from __future__ import annotations

import struct
from typing import List, Optional, Tuple

Entry = Tuple[int, str, object]  # tag_id, kind ("ascii"/"short"/"long"/"rational"), value


def _encode_value(kind: str, value, endian: str) -> Tuple[int, int, bytes]:
    """Return (exif type id, count, encoded bytes) for one entry value."""
    if kind == "ascii":
        data = value.encode("ascii") + b"\x00"
        return 2, len(data), data
    if kind == "short":
        return 3, 1, struct.pack(endian + "H", value)
    if kind == "long":
        return 4, 1, struct.pack(endian + "I", value)
    if kind == "rational":
        num, den = value
        return 5, 1, struct.pack(endian + "II", num, den)
    raise ValueError("unsupported fixture value kind: %r" % (kind,))


def build_ifd(endian: str, entries: List[Entry], start_offset: int) -> bytes:
    """Encode one IFD (entry table, next-IFD pointer, overflow pool) as it
    would sit at absolute offset `start_offset` inside a TIFF/Exif block.
    """
    encoded = [(tag_id,) + _encode_value(kind, value, endian) for tag_id, kind, value in entries]
    header_size = 2 + len(encoded) * 12 + 4
    pool = bytearray()
    packed = bytearray()
    for tag_id, type_id, count, data in encoded:
        packed += struct.pack(endian + "HHI", tag_id, type_id, count)
        if len(data) <= 4:
            packed += data.ljust(4, b"\x00")
        else:
            offset = start_offset + header_size + len(pool)
            packed += struct.pack(endian + "I", offset)
            pool += data
    return (
        struct.pack(endian + "H", len(encoded))
        + bytes(packed)
        + struct.pack(endian + "I", 0)  # no next IFD
        + bytes(pool)
    )


def build_tiff(
    byte_order: str,
    entries: List[Entry],
    sub_ifd_entries: Optional[List[Entry]] = None,
    sub_ifd_tag: int = 0x8769,
) -> bytes:
    """Build a minimal TIFF/Exif block: header + IFD0, optionally with a
    second IFD (e.g. the Exif sub-IFD) referenced by `sub_ifd_tag`.
    """
    endian = "<" if byte_order == "little" else ">"
    magic = b"II" if byte_order == "little" else b"MM"
    header = magic + struct.pack(endian + "H", 42) + struct.pack(endian + "I", 8)
    main_start = 8

    main_entries = list(entries)
    if sub_ifd_entries is not None:
        main_entries.append((sub_ifd_tag, "long", 0))  # patched once we know the offset

    main_ifd = build_ifd(endian, main_entries, main_start)
    if sub_ifd_entries is None:
        return header + main_ifd

    # The pointer's value is stored inline (a LONG fits in 4 bytes), so
    # rewriting it doesn't change main_ifd's length or layout.
    sub_start = main_start + len(main_ifd)
    sub_ifd = build_ifd(endian, sub_ifd_entries, sub_start)
    main_entries[-1] = (sub_ifd_tag, "long", sub_start)
    main_ifd = build_ifd(endian, main_entries, main_start)
    return header + main_ifd + sub_ifd


def jpeg_segment(marker_byte: int, payload: bytes = b"") -> bytes:
    return bytes([0xFF, marker_byte]) + struct.pack(">H", len(payload) + 2) + payload


def minimal_jpeg(
    width: int = 20,
    height: int = 10,
    bit_depth: int = 8,
    num_components: int = 3,
    exif_block: Optional[bytes] = None,
) -> bytes:
    """A tiny but structurally valid JPEG: SOI, APP0/JFIF, an optional
    APP1/Exif block, SOF0, SOS, then a couple of stand-in scan bytes and
    EOI. The parser stops walking markers at SOS, so the scan bytes never
    need to be real entropy-coded data.
    """
    out = bytearray(b"\xFF\xD8")  # SOI
    out += jpeg_segment(0xE0, b"JFIF\x00" + bytes([1, 1, 0, 0, 1, 0, 1, 0, 0]))
    if exif_block is not None:
        out += jpeg_segment(0xE1, b"Exif\x00\x00" + exif_block)
    components = b"".join(bytes([i + 1, 0x11, 0]) for i in range(num_components))
    sof_payload = (
        bytes([bit_depth])
        + struct.pack(">H", height)
        + struct.pack(">H", width)
        + bytes([num_components])
        + components
    )
    out += jpeg_segment(0xC0, sof_payload)
    sos_payload = bytes([num_components]) + b"\x01\x00" * num_components + bytes([0, 63, 0])
    out += jpeg_segment(0xDA, sos_payload)
    out += b"\x00\x00\xFF\xD9"  # stand-in scan bytes + EOI, never walked by the parser
    return bytes(out)
