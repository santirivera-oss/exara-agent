"""Detect and redact common API keys / tokens before they reach the model.

Applied centrally by Tool.run() to every ToolResult.output. The model still
sees the structure of the file/output, just with secrets replaced by
`[REDACTED-<kind>]`. Prevents accidental leakage when:
  - read_file shows a `.env` or config file
  - execute_terminal pipes `cat .env` output
  - web_fetch pulls a page that echoes a token
  - an MCP server (filesystem, etc.) returns sensitive contents

NOT a security boundary — a determined model can still ask for the file in
chunks, base64, etc. Its job is to prevent honest-mistake leaks in normal
output.
"""
from __future__ import annotations

import re
from typing import Tuple


# Ordered by specificity — narrowest patterns first so they match before
# generic ones. Each entry: (label, compiled regex). The whole match is
# replaced — never use unbounded prefixes that could swallow surrounding text.
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # OpenRouter
    ("openrouter-key", re.compile(r"sk-or-v[12]-[A-Za-z0-9_-]{32,}")),
    # OpenAI (legacy + project keys)
    ("openai-project-key", re.compile(r"sk-proj-[A-Za-z0-9_-]{20,}")),
    ("openai-key", re.compile(r"sk-[A-Za-z0-9]{20,}")),
    # Anthropic
    ("anthropic-key", re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}")),
    # GitHub
    ("github-pat-fine-grained", re.compile(r"github_pat_[A-Za-z0-9_]{20,}")),
    ("github-pat-classic", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}\b")),
    # GitLab
    ("gitlab-pat", re.compile(r"glpat-[A-Za-z0-9_-]{20,}")),
    # Slack
    ("slack-token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}")),
    # AWS
    ("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("aws-secret-key", re.compile(r"(?i)aws_secret_access_key\s*[:=]\s*['\"]?([A-Za-z0-9/+=]{40})['\"]?")),
    # Google / Firebase
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    # Stripe
    ("stripe-secret", re.compile(r"sk_(?:test|live)_[A-Za-z0-9]{24,}")),
    # Sendgrid
    ("sendgrid-key", re.compile(r"SG\.[A-Za-z0-9_-]{22}\.[A-Za-z0-9_-]{43}")),
    # JWT (loose match — three dot-separated base64url-ish segments)
    # Intentionally narrow length bounds so it doesn't false-positive on file paths.
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_=-]{10,}\.eyJ[A-Za-z0-9_=-]{10,}\.[A-Za-z0-9_=.-]{10,}\b")),
    # Connection strings with embedded passwords
    ("db-url-password",
     re.compile(r"(?P<scheme>postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqps?)://[^:\s/]+:(?P<pw>[^@\s]+)@")),
    # Generic "API_KEY = <value>" patterns when value looks tokenish (last resort)
    ("generic-bearer",
     re.compile(r"\b[Bb]earer\s+[A-Za-z0-9._-]{20,}")),
]


def redact_secrets(text: str) -> Tuple[str, int]:
    """Return (redacted_text, n_redactions).

    Patterns are applied in order, narrowest first. A given substring is
    only redacted once: after the first match, subsequent patterns won't
    re-match because the source string already shows the placeholder.
    """
    if not text or not isinstance(text, str):
        return text, 0

    count = 0

    for label, rx in _PATTERNS:
        def _sub(match: re.Match) -> str:
            nonlocal count
            count += 1
            # For db URLs, redact only the password and keep the rest readable
            if "pw" in match.groupdict():
                return match.group(0).replace(match.group("pw"), "[REDACTED]")
            return f"[REDACTED-{label}]"

        text = rx.sub(_sub, text)

    return text, count
