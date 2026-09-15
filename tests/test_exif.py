import unittest

from imgmeta import exif

from . import fixtures


class ExifParseTests(unittest.TestCase):
    def test_ascii_and_short_tags(self):
        block = fixtures.build_tiff(
            "big", [(0x010F, "ascii", "Canon"), (0x0112, "short", 1)]
        )
        result = exif.parse(block)
        self.assertEqual(result.byte_order, "big")
        self.assertEqual(result.tags["Make"], "Canon")
        self.assertEqual(result.tags["Orientation"], 1)

    def test_little_endian_and_indirect_ascii_value(self):
        # "Canon EOS 90D\0" is 14 bytes, too big to fit inline, so this
        # also exercises the value-offset/overflow-pool path.
        block = fixtures.build_tiff("little", [(0x0110, "ascii", "Canon EOS 90D")])
        result = exif.parse(block)
        self.assertEqual(result.byte_order, "little")
        self.assertEqual(result.tags["Model"], "Canon EOS 90D")

    def test_rational_tag(self):
        block = fixtures.build_tiff("big", [(0x829D, "rational", (28, 10))])
        result = exif.parse(block)
        self.assertAlmostEqual(result.tags["FNumber"], 2.8)

    def test_exif_sub_ifd_is_merged_into_tags(self):
        block = fixtures.build_tiff(
            "big",
            [(0x010F, "ascii", "Canon")],
            sub_ifd_entries=[(0x9003, "ascii", "2025:11:03 14:22:07")],
        )
        result = exif.parse(block)
        self.assertEqual(result.tags["Make"], "Canon")
        self.assertEqual(result.tags["DateTimeOriginal"], "2025:11:03 14:22:07")
        self.assertNotIn("ExifIFDPointer", result.tags)

    def test_unrecognized_tag_id_is_ignored(self):
        block = fixtures.build_tiff("big", [(0xABCD, "short", 7)])
        result = exif.parse(block)
        self.assertEqual(result.tags, {})

    def test_truncated_header_raises(self):
        with self.assertRaises(exif.ExifParseError):
            exif.parse(b"MM\x00")

    def test_bad_byte_order_mark_raises(self):
        block = bytearray(fixtures.build_tiff("big", []))
        block[0:2] = b"XX"
        with self.assertRaises(exif.ExifParseError):
            exif.parse(bytes(block))

    def test_bad_magic_number_raises(self):
        block = bytearray(fixtures.build_tiff("big", []))
        block[2:4] = b"\x00\x00"
        with self.assertRaises(exif.ExifParseError):
            exif.parse(bytes(block))


if __name__ == "__main__":
    unittest.main()
