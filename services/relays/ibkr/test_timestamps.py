"""Tests for IBKR-specific timestamp → ISO-8601 conversion."""

import unittest

from .timestamps import bridge_to_iso, flex_to_iso


class TestFlexToIso(unittest.TestCase):

    def test_basic(self) -> None:
        assert flex_to_iso("20250403;153000") == "2025-04-03T15:30:00"

    def test_midnight(self) -> None:
        assert flex_to_iso("20250403;000000") == "2025-04-03T00:00:00"

    def test_wrong_separator_raises(self) -> None:
        with self.assertRaises(ValueError):
            flex_to_iso("20250403-153000")

    def test_dash_not_semicolon_raises(self) -> None:
        with self.assertRaises(ValueError):
            flex_to_iso("20250403-15:30:00")

    def test_empty_raises(self) -> None:
        with self.assertRaises(ValueError):
            flex_to_iso("")

    def test_iso_input_raises(self) -> None:
        with self.assertRaises(ValueError):
            flex_to_iso("2025-04-03T15:30:00")

    def test_invalid_date_raises(self) -> None:
        with self.assertRaises(ValueError):
            flex_to_iso("20251345;153000")  # month 13

    def test_invalid_time_raises(self) -> None:
        with self.assertRaises(ValueError):
            flex_to_iso("20250403;253000")  # hour 25


class TestBridgeToIso(unittest.TestCase):

    def test_basic(self) -> None:
        assert bridge_to_iso("20260411-10:30:00") == "2026-04-11T10:30:00"

    def test_midnight(self) -> None:
        assert bridge_to_iso("20260411-00:00:00") == "2026-04-11T00:00:00"

    def test_semicolon_not_dash_raises(self) -> None:
        with self.assertRaises(ValueError):
            bridge_to_iso("20260411;103000")

    def test_empty_raises(self) -> None:
        with self.assertRaises(ValueError):
            bridge_to_iso("")

    def test_iso_input_raises(self) -> None:
        with self.assertRaises(ValueError):
            bridge_to_iso("2026-04-11T10:30:00")

    def test_invalid_time_raises(self) -> None:
        with self.assertRaises(ValueError):
            bridge_to_iso("20260411-25:30:00")  # hour 25
