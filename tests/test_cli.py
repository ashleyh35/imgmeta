import contextlib
import io
import json
import os
import tempfile
import unittest

from imgmeta import cli

from . import fixtures


class CliTests(unittest.TestCase):
    def _write_temp_jpeg(self, data: bytes) -> str:
        fd, path = tempfile.mkstemp(suffix=".jpg")
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        self.addCleanup(os.remove, path)
        return path

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
        path = self._write_temp_jpeg(b"not a jpeg")

        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            rc = cli.main([path])

        self.assertEqual(rc, 1)
        self.assertIn("missing SOI marker", stderr.getvalue())

    def test_missing_file_returns_nonzero(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            rc = cli.main(["/nonexistent/path/definitely-not-here.jpg"])
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
