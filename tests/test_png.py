import unittest
import zlib

from imgmeta import png

from . import fixtures


class PngParseTests(unittest.TestCase):
    def test_dimensions_and_color_type(self):
        data = fixtures.minimal_png(width=64, height=32, bit_depth=8, color_type=2)
        result = png.parse(data)
        self.assertEqual((result.width, result.height), (64, 32))
        self.assertEqual(result.bit_depth, 8)
        self.assertEqual(result.color_type, "truecolor")
        self.assertEqual([c.type for c in result.chunks], ["IHDR", "IDAT", "IEND"])
        self.assertEqual(result.warnings, [])

    def test_text_chunk(self):
        data = fixtures.minimal_png(text_chunks=[(b"tEXt", b"Author\x00Jane Doe")])
        result = png.parse(data)
        self.assertEqual(result.text["Author"], "Jane Doe")

    def test_compressed_text_chunk(self):
        comment = "a repeated comment " * 5
        payload = b"Comment\x00\x00" + zlib.compress(comment.encode("latin-1"))
        data = fixtures.minimal_png(text_chunks=[(b"zTXt", payload)])
        result = png.parse(data)
        self.assertEqual(result.text["Comment"], comment)

    def test_international_text_chunk(self):
        # keyword\0 compression_flag compression_method language_tag\0 translated_keyword\0 text
        payload = b"Title\x00\x00\x00\x00\x00" + "café".encode("utf-8")
        data = fixtures.minimal_png(text_chunks=[(b"iTXt", payload)])
        result = png.parse(data)
        self.assertEqual(result.text["Title"], "café")

    def test_compressed_international_text_chunk(self):
        compressed = zlib.compress("café au lait".encode("utf-8"))
        payload = b"Title\x00\x01\x00\x00\x00" + compressed
        data = fixtures.minimal_png(text_chunks=[(b"iTXt", payload)])
        result = png.parse(data)
        self.assertEqual(result.text["Title"], "café au lait")

    def test_embedded_exif_is_parsed(self):
        exif_block = fixtures.build_tiff("big", [(0x010F, "ascii", "Canon")])
        data = fixtures.minimal_png(exif_block=exif_block)
        result = png.parse(data)
        self.assertIsNotNone(result.exif)
        self.assertEqual(result.exif.tags["Make"], "Canon")
        self.assertIn("eXIf", [c.type for c in result.chunks])

    def test_no_exif_when_exif_chunk_absent(self):
        result = png.parse(fixtures.minimal_png())
        self.assertIsNone(result.exif)

    def test_malformed_exif_becomes_a_warning_not_an_exception(self):
        data = fixtures.minimal_png(exif_block=b"garbage")
        result = png.parse(data)
        self.assertIsNone(result.exif)
        self.assertEqual(len(result.warnings), 1)
        self.assertIn("could not parse Exif block", result.warnings[0])

    def test_bad_crc_becomes_a_warning(self):
        data = bytearray(fixtures.minimal_png())
        # 8-byte signature, then IHDR's own 4-byte length + 4-byte type +
        # 13-byte payload, right before IHDR's CRC.
        data[29:33] = b"\x00\x00\x00\x00"
        result = png.parse(bytes(data))
        self.assertEqual(len(result.warnings), 1)
        self.assertIn("bad CRC", result.warnings[0])

    def test_missing_signature_raises(self):
        with self.assertRaises(png.PngParseError):
            png.parse(b"not a png")

    def test_first_chunk_must_be_ihdr(self):
        data = bytearray(fixtures.minimal_png())
        data[12:16] = b"IDAT"  # IHDR's own type field, right after the signature and length
        with self.assertRaises(png.PngParseError):
            png.parse(bytes(data))

    def test_truncated_chunk_raises(self):
        data = bytearray(fixtures.minimal_png())
        data[8:12] = b"\x7F\xFF\xFF\xFF"  # IHDR's own length field, right after the signature
        with self.assertRaises(png.PngParseError):
            png.parse(bytes(data))

    def test_stream_ending_before_iend_warns(self):
        data = fixtures.minimal_png()
        truncated = data[: data.rindex(b"IEND") - 4]  # cut off length field of IEND chunk
        result = png.parse(truncated)
        self.assertIn("stream ended before an IEND chunk was found", result.warnings)


if __name__ == "__main__":
    unittest.main()
