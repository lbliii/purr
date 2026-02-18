"""Tests for auth middleware wiring."""

from __future__ import annotations

from pathlib import Path

import pytest

from purr._errors import ConfigError
from purr.app import _resolve_load_user, _wire_auth_middleware
from purr.config import PurrConfig


class TestResolveLoadUser:
    """_resolve_load_user — resolve load_user from module:attr spec."""

    def test_returns_none_when_not_configured(self, tmp_path: Path) -> None:
        config = PurrConfig(root=tmp_path, auth_load_user=None)
        assert _resolve_load_user(config) is None

    def test_returns_none_for_invalid_format(self, tmp_path: Path) -> None:
        config = PurrConfig(root=tmp_path, auth_load_user="no-colon")
        assert _resolve_load_user(config) is None

    def test_raises_when_module_file_missing(self, tmp_path: Path) -> None:
        (tmp_path / "routes").mkdir()
        config = PurrConfig(root=tmp_path, auth_load_user="auth:load_user")
        with pytest.raises(ConfigError, match="not found"):
            _resolve_load_user(config)

    def test_raises_when_attr_not_callable(self, tmp_path: Path) -> None:
        routes = tmp_path / "routes"
        routes.mkdir()
        (routes / "auth.py").write_text("load_user = 42\n")
        config = PurrConfig(root=tmp_path, auth_load_user="auth:load_user")
        with pytest.raises(ConfigError, match="not callable"):
            _resolve_load_user(config)

    def test_resolves_callable_from_routes_module(self, tmp_path: Path) -> None:
        routes = tmp_path / "routes"
        routes.mkdir()
        (routes / "auth.py").write_text(
            "async def load_user(user_id: str):\n    return None\n"
        )
        config = PurrConfig(root=tmp_path, auth_load_user="auth:load_user")
        fn = _resolve_load_user(config)
        assert fn is not None
        assert callable(fn)


class TestWireAuthMiddleware:
    """_wire_auth_middleware — session, auth, CSRF when auth=True."""

    def test_noop_when_auth_false(self, tmp_path: Path) -> None:
        try:
            from chirp import App, AppConfig
        except (ImportError, AttributeError):
            pytest.skip("chirp.App not available (chirp may be mocked)")
        config = PurrConfig(root=tmp_path, auth=False)
        app = App(config=AppConfig(template_dir=tmp_path))
        _wire_auth_middleware(app, config)
        # No exception, app unchanged (no middleware added)

    def test_raises_when_auth_true_without_load_user(self, tmp_path: Path) -> None:
        try:
            from chirp import App, AppConfig
        except (ImportError, AttributeError):
            pytest.skip("chirp.App not available (chirp may be mocked)")
        config = PurrConfig(root=tmp_path, auth=True, auth_load_user=None)
        app = App(config=AppConfig(template_dir=tmp_path))
        with pytest.raises(ConfigError, match="auth_load_user"):
            _wire_auth_middleware(app, config)

    def test_wires_middleware_when_auth_enabled(self, tmp_path: Path) -> None:
        try:
            from chirp import App, AppConfig
        except (ImportError, AttributeError):
            pytest.skip("chirp.App not available (chirp may be mocked)")
        routes = tmp_path / "routes"
        routes.mkdir()
        (routes / "auth.py").write_text(
            "async def load_user(user_id: str):\n    return None\n"
        )
        config = PurrConfig(
            root=tmp_path,
            auth=True,
            auth_load_user="auth:load_user",
            session_secret="test-secret",
        )
        app = App(config=AppConfig(template_dir=tmp_path))
        _wire_auth_middleware(app, config)
        # csrf_field should be registered as template global
        assert "csrf_field" in app._template_globals
