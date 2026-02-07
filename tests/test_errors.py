"""Tests for purr._errors."""

from purr._errors import (
    ConfigError,
    ContentError,
    ExportError,
    PurrError,
    ReactiveError,
)


class TestErrorHierarchy:
    """All purr errors inherit from PurrError."""

    def test_purr_error_is_exception(self) -> None:
        assert issubclass(PurrError, Exception)

    def test_config_error_inherits(self) -> None:
        assert issubclass(ConfigError, PurrError)

    def test_content_error_inherits(self) -> None:
        assert issubclass(ContentError, PurrError)

    def test_reactive_error_inherits(self) -> None:
        assert issubclass(ReactiveError, PurrError)

    def test_export_error_inherits(self) -> None:
        assert issubclass(ExportError, PurrError)

    def test_catch_all_purr_errors(self) -> None:
        """All specific errors are catchable via PurrError."""
        for error_cls in (ConfigError, ContentError, ReactiveError, ExportError):
            try:
                raise error_cls("test")
            except PurrError:
                pass  # Expected — all caught by base class
