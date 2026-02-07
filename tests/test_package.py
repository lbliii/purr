"""Tests for purr package exports and metadata."""

import purr


class TestPackageMetadata:
    """Package-level exports and metadata."""

    def test_version_string(self) -> None:
        assert isinstance(purr.__version__, str)
        assert "0.1.0" in purr.__version__

    def test_free_threading_declaration(self) -> None:
        assert purr._Py_mod_gil == 0

    def test_all_exports_resolvable(self) -> None:
        for name in purr.__all__:
            if name == "site":
                # site requires initialization — tested in test_site_context.py
                continue
            getattr(purr, name)

    def test_invalid_attribute_raises(self) -> None:
        import pytest

        with pytest.raises(AttributeError, match="no attribute"):
            purr.nonexistent_thing  # type: ignore[attr-defined]  # noqa: B018
