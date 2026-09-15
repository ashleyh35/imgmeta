import unittest

from imgmeta import jpeg

from . import fixtures


class JpegParseTests(unittest.TestCase):
    def test_dimensions_and_segment_names(self):
        data = fixtures.minimal_jpeg(width=1024, height=768, bit_depth=8, num_components=3)
        result = jpeg.parse(data)
        self.assertEqual((result.width, result.height), (1024, 768))
        self.assertEqual(result.bit_depth, 8)
        self.assertEqual(result.num_components, 3)
        self.assertEqual([s.name for s in result.segments], ["SOI", "APP0", "SOF0", "SOS"])
        self.assertEqual(result.warnings, [])

    def test_embedded_exif_is_parsed(self):
        exif_block = fixtures.build_tiff("big", [(0x010F, "ascii", "Canon")])
        data = fixtures.minimal_jpeg(exif_block=exif_block)
        result = jpeg.parse(data)
        self.assertIsNotNone(result.exif)
        self.assertEqual(result.exif.byte_order, "big")
        self.assertEqual(result.exif.tags["Make"], "Canon")
        self.assertIn("APP1", [s.name for s in result.segments])

    def test_no_exif_when_app1_absent(self):
        result = jpeg.parse(fixtures.minimal_jpeg())
        self.assertIsNone(result.exif)

    def test_malformed_exif_becomes_a_warning_not_an_exception(self):
        data = fixtures.minimal_jpeg(exif_block=b"\x00\x00garbage")
        result = jpeg.parse(data)
        self.assertIsNone(result.exif)
        self.assertEqual(len(result.warnings), 1)
        self.assertIn("could not parse Exif block", result.warnings[0])

    def test_missing_soi_raises(self):
        data = fixtures.minimal_jpeg()
        with self.assertRaises(jpeg.JpegParseError):
            jpeg.parse(b"\x00\x00" + data[2:])

    def test_truncated_file_raises(self):
        with self.assertRaises(jpeg.JpegParseError):
            jpeg.parse(b"\xFF")

    def test_segment_length_overruns_file_raises(self):
        data = bytearray(fixtures.minimal_jpeg())
        # Bytes 4:6 are APP0's own length field, right after its FF E0 marker.
        data[4:6] = b"\x7F\xFF"
        with self.assertRaises(jpeg.JpegParseError):
            jpeg.parse(bytes(data))

    def test_garbage_marker_byte_raises(self):
        data = bytearray(fixtures.minimal_jpeg())
        data[2] = 0x00  # should be 0xFF to start the APP0 marker
        with self.assertRaises(jpeg.JpegParseError):
            jpeg.parse(bytes(data))

    def test_stream_ending_before_eoi_warns(self):
        data = fixtures.minimal_jpeg()
        truncated = data[: data.index(b"\xFF\xDA")]  # cut off before SOS/EOI
        result = jpeg.parse(truncated)
        self.assertIn("stream ended before an EOI marker was found", result.warnings)


if __name__ == "__main__":
    unittest.main()
