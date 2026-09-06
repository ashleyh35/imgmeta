"""Command-line entry point: `python -m imgmeta <file> [--json]`."""
from __future__ import annotations

import argparse
import json
import sys

from . import jpeg


def _segment_to_dict(seg: jpeg.Segment) -> dict:
    return {"marker": seg.name, "offset": seg.offset, "length": seg.length}


def to_dict(parsed: jpeg.JpegFile) -> dict:
    return {
        "width": parsed.width,
        "height": parsed.height,
        "bit_depth": parsed.bit_depth,
        "num_components": parsed.num_components,
        "segments": [_segment_to_dict(s) for s in parsed.segments],
        "exif": (
            {"byte_order": parsed.exif.byte_order, "tags": parsed.exif.tags}
            if parsed.exif is not None
            else None
        ),
        "warnings": parsed.warnings,
    }


def pretty_print(parsed: jpeg.JpegFile, path: str) -> str:
    lines = [path]
    if parsed.width and parsed.height:
        lines.append(
            "  dimensions: %dx%d (%d-bit, %s components)"
            % (parsed.width, parsed.height, parsed.bit_depth or 0, parsed.num_components or "?")
        )
    else:
        lines.append("  dimensions: unknown (no SOF marker found)")

    lines.append("  segments: " + ", ".join(s.name for s in parsed.segments))

    if parsed.exif is not None:
        lines.append("  exif (%s-endian):" % parsed.exif.byte_order)
        if parsed.exif.tags:
            for name, value in parsed.exif.tags.items():
                lines.append("    %-20s %s" % (name, value))
        else:
            lines.append("    (no recognized tags)")
    else:
        lines.append("  exif: none")

    if parsed.warnings:
        lines.append("  warnings:")
        for warning in parsed.warnings:
            lines.append("    - %s" % warning)

    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="imgmeta",
        description="Validate and print metadata from an image file.",
    )
    parser.add_argument("path", help="path to a JPEG file")
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

    try:
        parsed = jpeg.parse(data)
    except jpeg.JpegParseError as exc:
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
