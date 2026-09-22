"""Command-line entry point: `python -m imgmeta <file> [--json]`."""
from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional

from . import jpeg
from . import png as png_module


def _sniff_format(data: bytes) -> Optional[str]:
    if data[:2] == b"\xFF\xD8":
        return "jpeg"
    if data[:8] == png_module.SIGNATURE:
        return "png"
    return None


def _segment_to_dict(seg: jpeg.Segment) -> dict:
    return {"marker": seg.name, "offset": seg.offset, "length": seg.length}


def _chunk_to_dict(chunk: png_module.Chunk) -> dict:
    return {"type": chunk.type, "offset": chunk.offset, "length": chunk.length}


def _exif_to_dict(exif_data) -> Optional[dict]:
    if exif_data is None:
        return None
    return {"byte_order": exif_data.byte_order, "tags": exif_data.tags}


def jpeg_to_dict(parsed: jpeg.JpegFile) -> dict:
    return {
        "format": "jpeg",
        "width": parsed.width,
        "height": parsed.height,
        "bit_depth": parsed.bit_depth,
        "num_components": parsed.num_components,
        "segments": [_segment_to_dict(s) for s in parsed.segments],
        "exif": _exif_to_dict(parsed.exif),
        "warnings": parsed.warnings,
    }


def png_to_dict(parsed: png_module.PngFile) -> dict:
    return {
        "format": "png",
        "width": parsed.width,
        "height": parsed.height,
        "bit_depth": parsed.bit_depth,
        "color_type": parsed.color_type,
        "chunks": [_chunk_to_dict(c) for c in parsed.chunks],
        "text": parsed.text,
        "exif": _exif_to_dict(parsed.exif),
        "warnings": parsed.warnings,
    }


def _exif_lines(exif_data) -> List[str]:
    if exif_data is None:
        return ["  exif: none"]
    lines = ["  exif (%s-endian):" % exif_data.byte_order]
    if exif_data.tags:
        for name, value in exif_data.tags.items():
            lines.append("    %-20s %s" % (name, value))
    else:
        lines.append("    (no recognized tags)")
    return lines


def _warning_lines(warnings: List[str]) -> List[str]:
    if not warnings:
        return []
    lines = ["  warnings:"]
    for warning in warnings:
        lines.append("    - %s" % warning)
    return lines


def pretty_print_jpeg(parsed: jpeg.JpegFile, path: str) -> str:
    lines = [path]
    if parsed.width and parsed.height:
        lines.append(
            "  dimensions: %dx%d (%d-bit, %s components)"
            % (parsed.width, parsed.height, parsed.bit_depth or 0, parsed.num_components or "?")
        )
    else:
        lines.append("  dimensions: unknown (no SOF marker found)")

    lines.append("  segments: " + ", ".join(s.name for s in parsed.segments))
    lines.extend(_exif_lines(parsed.exif))
    lines.extend(_warning_lines(parsed.warnings))
    return "\n".join(lines)


def pretty_print_png(parsed: png_module.PngFile, path: str) -> str:
    lines = [path]
    if parsed.width and parsed.height:
        lines.append(
            "  dimensions: %dx%d (%d-bit, %s)"
            % (parsed.width, parsed.height, parsed.bit_depth or 0, parsed.color_type or "?")
        )
    else:
        lines.append("  dimensions: unknown (no IHDR chunk found)")

    lines.append("  chunks: " + ", ".join(c.type for c in parsed.chunks))

    if parsed.text:
        lines.append("  text:")
        for keyword, value in parsed.text.items():
            lines.append("    %-20s %s" % (keyword, value))

    lines.extend(_exif_lines(parsed.exif))
    lines.extend(_warning_lines(parsed.warnings))
    return "\n".join(lines)


# Per format: (parse function, error type, dict serializer, pretty printer).
_FORMATS = {
    "jpeg": (jpeg.parse, jpeg.JpegParseError, jpeg_to_dict, pretty_print_jpeg),
    "png": (png_module.parse, png_module.PngParseError, png_to_dict, pretty_print_png),
}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="imgmeta",
        description="Validate and print metadata from an image file.",
    )
    parser.add_argument("path", help="path to a JPEG or PNG file")
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="print machine-readable JSON instead of the human-readable report",
    )
    args = parser.parse_args(argv)

    try:
        with open(args.path, "rb") as fh:
            data = fh.read()
    except OSError as exc:
        print("imgmeta: %s" % exc, file=sys.stderr)
        return 1

    fmt = _sniff_format(data)
    if fmt is None:
        message = "not a recognized JPEG or PNG file"
        if args.as_json:
            print(json.dumps({"error": message, "path": args.path}))
        else:
            print("imgmeta: %s: %s" % (args.path, message), file=sys.stderr)
        return 1

    parse_fn, error_type, to_dict, pretty_print = _FORMATS[fmt]

    try:
        parsed = parse_fn(data)
    except error_type as exc:
        if args.as_json:
            print(json.dumps({"error": str(exc), "path": args.path}))
        else:
            print("imgmeta: %s: %s" % (args.path, exc), file=sys.stderr)
        return 1

    if args.as_json:
        print(json.dumps(to_dict(parsed), indent=2))
    else:
        print(pretty_print(parsed, args.path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
