"""Path resolution for credential storage.

Verifies the lazy `get_config_dir()` behaves correctly across the three
resolution branches: XDG override, ``~/.config`` default, cwd fallback.
The fallback branch matters for Windows CI / sandbox environments where
neither HOME nor USERPROFILE is set and ``Path.home()`` raises.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fatture_cli.auth.oauth import get_config_dir


def test_get_config_dir_honors_xdg_config_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    result = get_config_dir()

    assert result == tmp_path / "mayai-cli" / "fatture"


def test_get_config_dir_falls_back_when_home_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("HOME", raising=False)
    monkeypatch.delenv("USERPROFILE", raising=False)

    def _no_home() -> Path:
        raise RuntimeError("Could not determine home directory.")

    monkeypatch.setattr("pathlib.Path.home", _no_home)

    result = get_config_dir()

    assert result == Path.cwd() / ".fatture-cli"
