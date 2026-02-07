"""Tests for purr.site — the site context accessor."""

from pathlib import Path

import pytest


class TestSiteAccessor:
    """Verify purr.site behaves correctly before and after initialization."""

    def test_raises_before_init(self) -> None:
        """Accessing purr.site before _set_site() raises RuntimeError."""
        import purr

        # Reset to ensure clean state
        purr._site_ref = None

        with pytest.raises(RuntimeError, match="accessed before initialization"):
            _ = purr.site  # type: ignore[attr-defined]

    def test_available_after_set(self, tmp_path: Path) -> None:
        """After _set_site(), purr.site returns the Site object."""
        import purr
        from purr import _set_site

        from tests.conftest import make_test_site

        site = make_test_site(tmp_path)
        _set_site(site)

        try:
            assert purr.site is site  # type: ignore[attr-defined]
        finally:
            purr._site_ref = None

    def test_multiple_accesses_same_object(self, tmp_path: Path) -> None:
        """Multiple reads of purr.site return the same object."""
        import purr
        from purr import _set_site

        from tests.conftest import make_test_site

        site = make_test_site(tmp_path)
        _set_site(site)

        try:
            first = purr.site  # type: ignore[attr-defined]
            second = purr.site  # type: ignore[attr-defined]
            assert first is second
        finally:
            purr._site_ref = None

    def test_in_all(self) -> None:
        """``site`` is listed in purr.__all__."""
        import purr

        assert "site" in purr.__all__

    def test_unknown_attr_raises_attribute_error(self) -> None:
        """Accessing a nonexistent attribute raises AttributeError, not RuntimeError."""
        import purr

        with pytest.raises(AttributeError, match="has no attribute"):
            _ = purr.nonexistent_attr  # type: ignore[attr-defined]
