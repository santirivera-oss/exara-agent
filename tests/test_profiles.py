"""Profile store + settings overlay."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

# Import config FIRST so its module-level load_dotenv() runs and we know
# which AI_AGENT_* vars came from the user's real .env. Tests below then
# clean those before exercising the loader.
from ai_agent import config as _config_module  # noqa: F401
from ai_agent import profiles


@pytest.fixture
def tmp_profile_path(tmp_path: Path, monkeypatch):
    p = tmp_path / "profiles.json"
    monkeypatch.setenv("AI_AGENT_PROFILES_PATH", str(p))
    return p


# --- store basics -----------------------------------------------------------

def test_load_missing_returns_empty(tmp_profile_path):
    f = profiles.load()
    assert f.active is None
    assert f.profiles == {}


def test_upsert_creates_and_activates_first(tmp_profile_path):
    profile = profiles.Profile(
        provider="openai_compat",
        base_url="https://api.openai.com/v1",
        api_key="sk-123",
        model="gpt-4o-mini",
    )
    f = profiles.upsert("openai", profile)
    assert f.active == "openai"  # first one becomes active automatically
    assert f.profiles["openai"].model == "gpt-4o-mini"


def test_upsert_doesnt_steal_active_unless_asked(tmp_profile_path):
    profiles.upsert("a", profiles.Profile(provider="openai_compat", base_url="x", api_key="x", model="m1"))
    profiles.upsert("b", profiles.Profile(provider="openai_compat", base_url="x", api_key="x", model="m2"))
    f = profiles.load()
    assert f.active == "a"  # still the first
    # explicit activate
    profiles.upsert("b", profiles.Profile(provider="openai_compat", base_url="x", api_key="x", model="m2"), activate=True)
    assert profiles.load().active == "b"


def test_remove_re_picks_another(tmp_profile_path):
    profiles.upsert("a", profiles.Profile(provider="openai_compat", base_url="x", api_key="x", model="m1"))
    profiles.upsert("b", profiles.Profile(provider="openai_compat", base_url="x", api_key="x", model="m2"))
    profiles.activate("b")
    profiles.remove("b")
    assert profiles.load().active == "a"


def test_activate_unknown_raises(tmp_profile_path):
    with pytest.raises(KeyError):
        profiles.activate("nope")


def test_persisted_format_is_clean_json(tmp_profile_path):
    profiles.upsert(
        "openai",
        profiles.Profile(
            provider="openai_compat",
            base_url="https://api.openai.com/v1",
            api_key="sk-123",
            model="gpt-4o-mini",
            extra_headers={"X-Title": "ai-agent"},
        ),
    )
    raw = json.loads(tmp_profile_path.read_text(encoding="utf-8"))
    assert raw["active"] == "openai"
    assert raw["profiles"]["openai"]["api_key"] == "sk-123"


# --- settings overlay -------------------------------------------------------

def test_active_profile_overrides_settings(tmp_profile_path, monkeypatch):
    # Profile says: use OpenAI directly
    profiles.upsert(
        "openai",
        profiles.Profile(
            provider="openai_compat",
            base_url="https://api.openai.com/v1",
            api_key="sk-test-123",
            model="gpt-4o-mini",
        ),
    )
    # Clear env so it doesn't override — keep AI_AGENT_PROFILES_PATH so the
    # test's tmp profile file is found.
    for k in list(os.environ):
        if k.startswith("AI_AGENT_") and k != "AI_AGENT_PROFILES_PATH":
            monkeypatch.delenv(k, raising=False)

    from ai_agent.config import load_settings
    s = load_settings()
    assert s.model.provider == "openai_compat"
    assert s.model.openai_compat.api_key == "sk-test-123"
    assert s.model.openai_compat.model == "gpt-4o-mini"


def test_env_overrides_profile(tmp_profile_path, monkeypatch):
    """If env var is set, it wins over the active profile."""
    # Clean other AI_AGENT_ env vars except profile path so the test is hermetic
    for k in list(os.environ):
        if k.startswith("AI_AGENT_") and k != "AI_AGENT_PROFILES_PATH":
            monkeypatch.delenv(k, raising=False)
    profiles.upsert(
        "openai",
        profiles.Profile(
            provider="openai_compat",
            base_url="https://api.openai.com/v1",
            api_key="sk-test-123",
            model="gpt-4o-mini",
        ),
    )
    monkeypatch.setenv("AI_AGENT_OPENAI_MODEL", "from-env")

    from ai_agent.config import load_settings
    s = load_settings()
    assert s.model.openai_compat.model == "from-env"
    # api_key still from profile (env didn't touch it)
    assert s.model.openai_compat.api_key == "sk-test-123"


def test_no_active_profile_means_no_overlay(tmp_profile_path, monkeypatch):
    # Save profiles but with no active
    f = profiles.ProfileFile(active=None, profiles={})
    profiles.save(f)
    # Settings load shouldn't blow up
    from ai_agent.config import load_settings
    s = load_settings()
    assert s is not None
