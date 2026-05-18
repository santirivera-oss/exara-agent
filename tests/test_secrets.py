"""Secret-redaction defensive pass on tool output."""
from __future__ import annotations

import pytest

from ai_agent.utils.secrets import redact_secrets


def _openrouter_key() -> str:
    return "sk-or-v1-" + ("A" * 64)


def _github_pat() -> str:
    return "github_pat_" + ("B" * 64)


# --- direct unit tests on the redactor --------------------------------------

def test_redacts_openrouter_key():
    text = f"AI_AGENT_OPENAI_API_KEY={_openrouter_key()}"
    out, n = redact_secrets(text)
    assert n == 1
    assert "sk-or-v1" not in out
    assert "[REDACTED-openrouter-key]" in out


def test_redacts_openai_project_key():
    text = "key = sk-proj-AAAAAAAAAAAAAAAAAAAAAAAA"
    out, n = redact_secrets(text)
    assert n == 1
    assert "sk-proj-" not in out


def test_redacts_anthropic_key():
    text = 'ANTHROPIC="sk-ant-api03-xyz0123456789abcdefghijklmnopqr"'
    out, n = redact_secrets(text)
    assert n == 1
    assert "sk-ant" not in out
    assert "[REDACTED-anthropic-key]" in out


def test_redacts_github_pat_classic():
    text = "token=ghp_abcdefghijklmnopqrstuvwxyz0123456789AB and another gho_zyxwvutsrqponmlkjihgfedcba9876543210ZA"
    out, n = redact_secrets(text)
    assert n == 2
    assert "ghp_" not in out
    assert "gho_" not in out


def test_redacts_github_pat_fine_grained():
    text = f"GITHUB_PERSONAL_ACCESS_TOKEN={_github_pat()}"
    out, n = redact_secrets(text)
    assert n == 1
    assert "github_pat_" not in out


def test_redacts_aws_keys():
    text = """
    aws_access_key_id = AKIAIOSFODNN7EXAMPLE
    aws_secret_access_key = wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
    """
    out, n = redact_secrets(text)
    assert n == 2
    assert "AKIA" not in out
    assert "wJalrX" not in out


def test_redacts_google_api_key():
    # Real Google API keys are AIza + exactly 35 chars = 39 total.
    text = "GOOGLE_API_KEY=AIzaSyBOkLFAKEFAKEFAKEFAKEFAKEFAKEEXTRA"
    assert len("AIzaSyBOkLFAKEFAKEFAKEFAKEFAKEFAKEEXTRA") == 39
    out, n = redact_secrets(text)
    assert n == 1
    assert "AIza" not in out


def test_redacts_db_url_password_keeps_rest_readable():
    text = "DATABASE_URL=postgresql://admin:s3cr3tp4ss@db.example.com:5432/myapp"
    out, n = redact_secrets(text)
    assert n == 1
    assert "s3cr3tp4ss" not in out
    assert "[REDACTED]" in out
    # Host + db should still be visible for debuggability
    assert "db.example.com" in out
    assert "myapp" in out


def test_redacts_bearer_token():
    text = "Authorization: Bearer abc123def456ghi789jklmnopqrstuvwxyz"
    out, n = redact_secrets(text)
    assert n == 1
    assert "abc123def456" not in out


def test_no_false_positive_on_short_strings():
    # 'sk-12' is too short to be an OpenAI key
    text = "ticker sk-12 was traded"
    out, n = redact_secrets(text)
    assert n == 0
    assert out == text


def test_no_false_positive_on_normal_text():
    text = "The quick brown fox jumps over the lazy dog. Path: /home/user/projects"
    out, n = redact_secrets(text)
    assert n == 0


def test_handles_empty_input():
    assert redact_secrets("") == ("", 0)


def test_handles_non_string_input():
    assert redact_secrets(None) == (None, 0)  # type: ignore[arg-type]


def test_redacts_realistic_env_file_dump():
    """A realistic provider config dump should keep context and redact values."""
    text = """
AI_AGENT_PROVIDER=openai_compat
AI_AGENT_OPENAI_BASE_URL=https://openrouter.ai/api/v1
AI_AGENT_OPENAI_API_KEY={key}
AI_AGENT_OPENAI_MODEL=minimax/minimax-m2.5:free
""".format(key=_openrouter_key())
    out, n = redact_secrets(text)
    assert n == 1
    # Surrounding context preserved
    assert "AI_AGENT_OPENAI_API_KEY" in out
    assert "openrouter" in out
    # Secret value gone
    assert _openrouter_key() not in out
    assert "[REDACTED-openrouter-key]" in out


# --- integration with Tool.run ---------------------------------------------

async def test_built_in_read_file_output_is_redacted(tmp_path):
    """Validates that the central scrubber actually fires on tool output."""
    from ai_agent.tools.base import ToolContext
    from ai_agent.tools.file_ops import ReadFile

    class _DummyLogger:
        def __getattr__(self, _):
            def f(*_a, **_k): ...
            return f

    env = tmp_path / ".env"
    env.write_text(f"AI_AGENT_OPENAI_API_KEY={_openrouter_key()}\n", encoding="utf-8")
    ctx = ToolContext(workspace=tmp_path, settings=None, logger=_DummyLogger())
    result = await ReadFile().run({"path": ".env"}, ctx)
    assert result.success
    assert "sk-or-v1-fakekey" not in result.output
    assert "REDACTED" in result.output
