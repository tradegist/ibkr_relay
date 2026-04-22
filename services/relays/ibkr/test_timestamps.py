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

    def test_naive_iso(self) -> None:
        assert bridge_to_iso("2026-04-22T15:31:28") == "2026-04-22T15:31:28"

    def test_utc_aware_iso(self) -> None:
        assert bridge_to_iso("2026-04-22T15:31:28+00:00") == "2026-04-22T15:31:28+00:00"

    def test_non_utc_offset_passed_through(self) -> None:
        assert bridge_to_iso("2026-04-22T15:31:28+05:30") == "2026-04-22T15:31:28+05:30"

    def test_z_suffix_passed_through(self) -> None:
        assert bridge_to_iso("2026-04-22T15:31:28Z") == "2026-04-22T15:31:28Z"

    def test_iso_midnight(self) -> None:
        assert bridge_to_iso("2026-04-11T00:00:00") == "2026-04-11T00:00:00"

    def test_iso_invalid_date_raises(self) -> None:
        with self.assertRaises(ValueError):
            bridge_to_iso("2026-13-01T10:00:00")  # month 13

    def test_legacy_basic(self) -> None:
        assert bridge_to_iso("20260411-10:30:00") == "2026-04-11T10:30:00"

    def test_legacy_midnight(self) -> None:
        assert bridge_to_iso("20260411-00:00:00") == "2026-04-11T00:00:00"

    def test_empty_raises(self) -> None:
        with self.assertRaises(ValueError):
            bridge_to_iso("")

    def test_flex_format_raises(self) -> None:
        with self.assertRaises(ValueError):
            bridge_to_iso("20260411;103000")

    def test_legacy_invalid_hour_raises(self) -> None:
        with self.assertRaises(ValueError):
            bridge_to_iso("20260411-25:30:00")

    def test_garbage_raises(self) -> None:
        with self.assertRaises(ValueError):
            bridge_to_iso("not-a-timestamp")
