import contextlib
import io
import json
import os
import tempfile
import unittest

from imgmeta import cli

from . import fixtures


class CliTests(unittest.TestCase):
    def _write_temp_file(self, data: bytes, suffix: str) -> str:
        fd, path = tempfile.mkstemp(suffix=suffix)
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        self.addCleanup(os.remove, path)
        return path

    def _write_temp_jpeg(self, data: bytes) -> str:
        return self._write_temp_file(data, ".jpg")

    def test_json_output_round_trips_through_to_dict(self):
        exif_block = fixtures.build_tiff("big", [(0x010F, "ascii", "Canon")])
        path = self._write_temp_jpeg(
            fixtures.minimal_jpeg(width=100, height=50, exif_block=exif_block)
        )

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            rc = cli.main([path, "--json"])

        self.assertEqual(rc, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["width"], 100)
        self.assertEqual(payload["height"], 50)
        self.assertEqual(payload["exif"]["tags"]["Make"], "Canon")

    def test_pretty_output_lists_dimensions_and_no_exif(self):
        path = self._write_temp_jpeg(fixtures.minimal_jpeg(width=100, height=50))

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            rc = cli.main([path])

        self.assertEqual(rc, 0)
        out = stdout.getvalue()
        self.assertIn(path, out)
        self.assertIn("dimensions: 100x50", out)
        self.assertIn("exif: none", out)

    def test_parse_error_prints_to_stderr_and_returns_nonzero(self):
        # Starts with a valid SOI so it sniffs as JPEG, but the very next
        # byte isn't a marker, so jpeg.parse fails once it gets going.
        path = self._write_temp_jpeg(b"\xFF\xD8\x00\x00")

        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            rc = cli.main([path])

        self.assertEqual(rc, 1)
        self.assertIn("expected marker byte", stderr.getvalue())

    def test_missing_file_returns_nonzero(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            rc = cli.main(["/nonexistent/path/definitely-not-here.jpg"])
        self.assertEqual(rc, 1)

    def test_png_json_output(self):
        exif_block = fixtures.build_tiff("big", [(0x010F, "ascii", "Canon")])
        path = self._write_temp_file(
            fixtures.minimal_png(width=64, height=32, exif_block=exif_block), ".png"
        )

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            rc = cli.main([path, "--json"])

        self.assertEqual(rc, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["format"], "png")
        self.assertEqual((payload["width"], payload["height"]), (64, 32))
        self.assertEqual(payload["exif"]["tags"]["Make"], "Canon")

    def test_png_pretty_output_lists_text_chunk(self):
        path = self._write_temp_file(
            fixtures.minimal_png(text_chunks=[(b"tEXt", b"Author\x00Jane Doe")]), ".png"
        )

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            rc = cli.main([path])

        self.assertEqual(rc, 0)
        out = stdout.getvalue()
        self.assertIn("dimensions: 20x10", out)
        self.assertIn("Author", out)
        self.assertIn("Jane Doe", out)

    def test_unrecognized_format_returns_nonzero(self):
        path = self._write_temp_file(b"not an image at all", ".bin")

        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            rc = cli.main([path])

        self.assertEqual(rc, 1)
        self.assertIn("not a recognized JPEG or PNG file", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
