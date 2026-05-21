"""Tests for the actari init interactive wizard.

The wizard talks to rich.prompt.Prompt/Confirm.ask and to a key validator
that hits NARA. Both are monkey-patched to keep tests fast and offline.
"""

from __future__ import annotations


import pytest
import tomllib
from rich.console import Console

from actari import init_wizard
from actari.init_wizard import WizardAborted, run_wizard


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("ACTARI_HOME", str(home))
    return home


def _scripted_prompt(values):
    """Build a Prompt.ask replacement that returns values in order."""
    iterator = iter(values)

    def ask(prompt_text, *args, **kwargs):
        try:
            return next(iterator)
        except StopIteration:  # pragma: no cover — test bug, fail loudly
            raise AssertionError(f"wizard asked for more input than expected: {prompt_text}")

    return ask


def _scripted_confirm(values):
    iterator = iter(values)

    def ask(prompt_text, *args, **kwargs):
        try:
            return next(iterator)
        except StopIteration:
            raise AssertionError(f"wizard asked for more confirmations: {prompt_text}")

    return ask


def test_wizard_happy_path_writes_valid_toml(isolated_home, monkeypatch):
    monkeypatch.setattr(
        init_wizard,
        "Prompt",
        type(
            "P",
            (),
            {
                "ask": staticmethod(
                    _scripted_prompt(
                        [
                            "kYzAbCdEfGhIjKlMnOpQrStUvWxYz0123456789abc",  # API key
                            str(isolated_home / "out"),  # output dir
                        ]
                    )
                )
            },
        ),
    )
    monkeypatch.setattr(
        init_wizard,
        "Confirm",
        type(
            "C",
            (),
            {
                "ask": staticmethod(
                    _scripted_confirm(
                        [
                            True,  # acknowledge NARA terms
                        ]
                    )
                )
            },
        ),
    )

    written = run_wizard(
        validator=lambda key: (True, "ok"),
        console=Console(quiet=True),
    )
    assert written.exists()
    data = tomllib.loads(written.read_text(encoding="utf-8"))
    assert data["api"]["key"].startswith("kYz")
    assert data["meta"]["nara_terms_acknowledged"] is True
    assert "acknowledged_at" in data["meta"]
    assert data["storage"]["output_dir"].endswith("out")


def test_wizard_retries_on_validation_failure_then_succeeds(isolated_home, monkeypatch):
    monkeypatch.setattr(
        init_wizard,
        "Prompt",
        type(
            "P",
            (),
            {
                "ask": staticmethod(
                    _scripted_prompt(
                        [
                            "bad-key",
                            "r",  # retry
                            "kYzAbCdEfGhIjKlMnOpQrStUvWxYz0123456789abc",
                            str(isolated_home / "out"),
                        ]
                    )
                )
            },
        ),
    )
    monkeypatch.setattr(
        init_wizard, "Confirm", type("C", (), {"ask": staticmethod(_scripted_confirm([True]))})
    )

    calls = []

    def validator(key):
        calls.append(key)
        return (key.startswith("kYz"), "ok" if key.startswith("kYz") else "rejected")

    written = run_wizard(validator=validator, console=Console(quiet=True))
    assert written.exists()
    assert calls == ["bad-key", "kYzAbCdEfGhIjKlMnOpQrStUvWxYz0123456789abc"]


def test_wizard_save_anyway_persists_unvalidated_key(isolated_home, monkeypatch):
    monkeypatch.setattr(
        init_wizard,
        "Prompt",
        type(
            "P",
            (),
            {
                "ask": staticmethod(
                    _scripted_prompt(
                        [
                            "kYzAbCdEfGhIjKlMnOpQrStUvWxYz0123456789abc",
                            "s",  # save anyway
                            str(isolated_home / "out"),
                        ]
                    )
                )
            },
        ),
    )
    monkeypatch.setattr(
        init_wizard, "Confirm", type("C", (), {"ask": staticmethod(_scripted_confirm([True]))})
    )

    written = run_wizard(
        validator=lambda key: (False, "geo-blocked PoP — try a VPN"),
        console=Console(quiet=True),
    )
    assert written.exists()


def test_wizard_aborts_on_user_choice(isolated_home, monkeypatch):
    monkeypatch.setattr(
        init_wizard,
        "Prompt",
        type(
            "P",
            (),
            {
                "ask": staticmethod(
                    _scripted_prompt(
                        [
                            "anything",
                            "a",  # abort
                        ]
                    )
                )
            },
        ),
    )
    monkeypatch.setattr(
        init_wizard, "Confirm", type("C", (), {"ask": staticmethod(_scripted_confirm([]))})
    )

    with pytest.raises(WizardAborted):
        run_wizard(
            validator=lambda key: (False, "rejected"),
            console=Console(quiet=True),
        )
    assert not (isolated_home / "config.toml").exists()


def test_wizard_aborts_when_terms_declined(isolated_home, monkeypatch):
    monkeypatch.setattr(
        init_wizard,
        "Prompt",
        type(
            "P",
            (),
            {
                "ask": staticmethod(
                    _scripted_prompt(
                        [
                            "kYzAbCdEfGhIjKlMnOpQrStUvWxYz0123456789abc",
                            str(isolated_home / "out"),
                        ]
                    )
                )
            },
        ),
    )
    monkeypatch.setattr(
        init_wizard, "Confirm", type("C", (), {"ask": staticmethod(_scripted_confirm([False]))})
    )

    with pytest.raises(WizardAborted):
        run_wizard(validator=lambda k: (True, "ok"), console=Console(quiet=True))


def test_wizard_refuses_overwrite_without_reset(isolated_home, monkeypatch):
    target = isolated_home / "config.toml"
    target.write_text('[api]\nkey = "old"\n', encoding="utf-8")

    monkeypatch.setattr(
        init_wizard, "Prompt", type("P", (), {"ask": staticmethod(_scripted_prompt([]))})
    )
    monkeypatch.setattr(
        init_wizard,
        "Confirm",
        type(
            "C",
            (),
            {
                "ask": staticmethod(
                    _scripted_confirm(
                        [
                            False,  # decline overwrite
                        ]
                    )
                )
            },
        ),
    )

    with pytest.raises(WizardAborted):
        run_wizard(validator=lambda k: (True, "ok"), console=Console(quiet=True))
    # Existing config untouched.
    assert "old" in target.read_text(encoding="utf-8")


def test_validate_api_key_rejects_short(isolated_home):
    ok, msg = init_wizard._validate_api_key("abc")
    assert not ok
    assert "short" in msg.lower()
