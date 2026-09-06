"""JPEG container parsing.

Walks the marker segment stream and pulls out the pieces that matter
for metadata: dimensions from the SOF marker, and an Exif block from
APP1 if one is present. This is not a JPEG decoder - it never touches
the entropy-coded scan data, only the markers around it - but it does
validate that the marker structure itself is internally consistent
(lengths that fit in the file, a proper SOI/EOI, no garbage where a
marker byte should be).
"""
from __future__ import annotations

import dataclasses
from typing import List, Optional

from . import exif as exif_module

SOI = 0xFFD8
EOI = 0xFFD9
SOS = 0xFFDA
APP1 = 0xFFE1

# Markers that are a single two-byte code with no length field or payload:
# TEM (0xFF01) and the restart markers RST0-RST7 (0xFFD0-0xFFD7).
_NO_LENGTH_MARKERS = {0xFF01} | {0xFFD0 + i for i in range(8)}

_SOF_MARKERS = {
    0xFFC0, 0xFFC1, 0xFFC2, 0xFFC3,
    0xFFC5, 0xFFC6, 0xFFC7,
    0xFFC9, 0xFFCA, 0xFFCB,
    0xFFCD, 0xFFCE, 0xFFCF,
}

_MARKER_NAMES = {
    0xFFD8: "SOI",
    0xFFD9: "EOI",
    0xFFDA: "SOS",
    0xFFDB: "DQT",
    0xFFC4: "DHT",
    0xFFDD: "DRI",
    0xFFFE: "COM",
    0xFFE0: "APP0",
    0xFFE1: "APP1",
    0xFFE2: "APP2",
    0xFFC0: "SOF0", 0xFFC1: "SOF1", 0xFFC2: "SOF2", 0xFFC3: "SOF3",
    0xFFC5: "SOF5", 0xFFC6: "SOF6", 0xFFC7: "SOF7",
    0xFFC9: "SOF9", 0xFFCA: "SOF10", 0xFFCB: "SOF11",
    0xFFCD: "SOF13", 0xFFCE: "SOF14", 0xFFCF: "SOF15",
}


class JpegParseError(ValueError):
    """Raised when the byte stream does not look like a well-formed JPEG."""


@dataclasses.dataclass
class Segment:
    marker: int
    name: str
    offset: int
    length: Optional[int]  # None for markers with no length field (e.g. EOI)


@dataclasses.dataclass
class JpegFile:
    width: Optional[int]
    height: Optional[int]
    bit_depth: Optional[int]
    num_components: Optional[int]
    segments: List[Segment]
    exif: Optional[exif_module.ExifData]
    warnings: List[str]


def _marker_name(marker: int) -> str:
    return _MARKER_NAMES.get(marker, "0x%04X" % marker)


def parse(data: bytes) -> JpegFile:
    if len(data) < 4:
        raise JpegParseError("file is too small to be a JPEG (%d bytes)" % len(data))
    if data[0] != 0xFF or data[1] != 0xD8:
        raise JpegParseError("missing SOI marker (0xFFD8) at start of file")

    segments: List[Segment] = [Segment(SOI, "SOI", 0, None)]
    warnings: List[str] = []
    width = height = bit_depth = num_components = None
    exif_data = None

    pos = 2
    while True:
        if pos >= len(data):
            warnings.append("stream ended before an EOI marker was found")
            break
        if data[pos] != 0xFF:
            raise JpegParseError(
                "expected marker byte 0xFF at offset %d, found 0x%02X" % (pos, data[pos])
            )

        marker_pos = pos
        pos += 1
        # Markers may be preceded by extra 0xFF fill bytes.
        while pos < len(data) and data[pos] == 0xFF:
            pos += 1
        if pos >= len(data):
            raise JpegParseError("truncated marker at offset %d" % marker_pos)
        marker = 0xFF00 | data[pos]
        pos += 1

        if marker == EOI:
            segments.append(Segment(marker, "EOI", marker_pos, None))
            break

        if marker in _NO_LENGTH_MARKERS:
            segments.append(Segment(marker, _marker_name(marker), marker_pos, None))
            continue

        if pos + 2 > len(data):
            raise JpegParseError("truncated length field for marker at offset %d" % marker_pos)
        seg_len = (data[pos] << 8) | data[pos + 1]
        if seg_len < 2:
            raise JpegParseError(
                "segment at offset %d has an invalid length (%d)" % (marker_pos, seg_len)
            )
        payload_start = pos + 2
        payload_end = payload_start + seg_len - 2
        if payload_end > len(data):
            raise JpegParseError(
                "segment at offset %d claims length %d but file is truncated"
                % (marker_pos, seg_len)
            )

        segments.append(Segment(marker, _marker_name(marker), marker_pos, seg_len))
        payload = data[payload_start:payload_end]

        if marker in _SOF_MARKERS and len(payload) >= 6:
            bit_depth = payload[0]
            height = (payload[1] << 8) | payload[2]
            width = (payload[3] << 8) | payload[4]
            num_components = payload[5]
        elif marker == APP1 and payload.startswith(b"Exif\x00\x00"):
            try:
                exif_data = exif_module.parse(payload[6:])
            except exif_module.ExifParseError as exc:
                warnings.append("could not parse Exif block: %s" % exc)

        if marker == SOS:
            # Compressed scan data follows. Its bytes can themselves contain
            # 0xFF sequences that aren't markers, so we stop walking here.
            break

        pos = payload_end

    return JpegFile(
        width=width,
        height=height,
        bit_depth=bit_depth,
        num_components=num_components,
        segments=segments,
        exif=exif_data,
        warnings=warnings,
    )
