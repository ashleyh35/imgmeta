# imgmeta

A small tool that reads a JPEG or PNG file, walks its container
structure, and reports what it finds: pixel dimensions, the
segment/chunk layout, and any Exif or text metadata embedded in it.

I wanted something that would tell me *why* a file failed to parse
rather than just crashing inside some image library's C extension, and
that I could pipe into other scripts without scraping text. Hence two
output modes from the same parse: a report meant for a terminal, and
JSON meant for a script.

Standard library only. No dependencies, nothing to install beyond
Python itself.

## Usage

```
$ python -m imgmeta photo.jpg
photo.jpg
  dimensions: 4032x3024 (8-bit, 3 components)
  segments: SOI, APP0, APP1, DQT, DQT, SOF0, DHT, DHT, DHT, DHT, SOS, EOI
  exif (big-endian):
    Make                 Canon
    Model                Canon EOS 90D
    Orientation           1
    DateTimeOriginal     2025:11:03 14:22:07
```

```
$ python -m imgmeta photo.jpg --json
{
  "format": "jpeg",
  "width": 4032,
  "height": 3024,
  "bit_depth": 8,
  "num_components": 3,
  "segments": [
    {"marker": "SOI", "offset": 0, "length": null},
    {"marker": "APP1", "offset": 20, "length": 3218},
    ...
  ],
  "exif": {
    "byte_order": "big",
    "tags": {"Make": "Canon", "Model": "Canon EOS 90D", ...}
  },
  "warnings": []
}
```

A malformed file doesn't raise a traceback, it produces a message that
says what looked wrong and where:

```
$ python -m imgmeta corrupt.jpg
imgmeta: corrupt.jpg: segment at offset 20 claims length 900 but file is truncated
```

PNG files work the same way, sniffed from the file's own signature
rather than its extension:

```
$ python -m imgmeta photo.png
photo.png
  dimensions: 1920x1080 (8-bit, truecolor+alpha)
  chunks: IHDR, tEXt, eXIf, IDAT, IEND
  text:
    Comment              edited in darktable
  exif (little-endian):
    Make                 Canon
```

## What it actually parses

- The JPEG marker stream (SOI, APPn, DQT, DHT, SOFn, SOS, EOI, ...),
  validating that segment lengths are internally consistent and that
  the file doesn't end mid-segment. Width, height, bit depth and
  component count come from the SOF marker.
- The PNG chunk stream (IHDR, tEXt/zTXt/iTXt, eXIf, IDAT, IEND, ...),
  validating chunk framing and CRC32s. Width, height, bit depth and
  color type come from IHDR; tEXt/zTXt/iTXt chunks are decoded
  (including zlib decompression where the chunk type calls for it)
  into a flat keyword-to-text mapping.
- The Exif block, if present (APP1 in JPEG, the eXIf chunk in PNG):
  byte order, IFD0, and the handful of common tags listed in
  `imgmeta/exif.py` (Make, Model, Orientation, DateTimeOriginal,
  exposure/ISO fields, and so on).

It does not decode pixel data and it is not trying to become a general
image library - the scope is metadata in, structured data out.

## Layout

```
src/imgmeta/
  jpeg.py   JPEG segment walker, dimension extraction
  png.py    PNG chunk walker, text chunk decoding
  exif.py   TIFF/Exif IFD parser
  cli.py    argparse entry point, format sniffing, pretty printer, JSON serializer
```

## Running from a checkout

```
python -m imgmeta some/file.jpg
```

or install it locally with `pip install -e .` to get the `imgmeta`
console script.

## Tests

```
python -m unittest discover -s tests
```

The tests build their JPEG/PNG/Exif fixtures byte by byte in
`tests/fixtures.py` rather than shipping binary sample files, so it's
obvious from the test itself which byte is under test.
