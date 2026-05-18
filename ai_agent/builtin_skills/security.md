---
name: security
description: Common vulnerabilities to avoid (OWASP-aware)
triggers:
  always: true
---

When writing or reviewing code, check for these. Most app bugs that get
exploited are in this list.

## Injection
- **SQL**: parameterised queries only. Never f-string user input into SQL.
  ```python
  db.execute("SELECT * FROM u WHERE id=?", (user_id,))   # ok
  db.execute(f"SELECT * FROM u WHERE id={user_id}")      # NOT ok
  ```
- **Shell**: `subprocess` with a list of args, never `shell=True` on user input.
  Same for `os.system`.
- **NoSQL** (Mongo, ES): operator injection via dict input. Whitelist allowed keys.
- **Template / XSS**: HTML-escape by default. React/Vue/Jinja autoescape — don't
  bypass with `dangerouslySetInnerHTML` / `safe` / `\| safe` without validation.

## Authn / authz
- Verify auth on **every** endpoint, not in the framework's middleware "usually".
- Authorise per-resource: just because they're logged in doesn't mean they own this row.
- Use libraries for password hashing (`bcrypt`, `argon2`, `passlib`). Never invent.
- Don't roll your own JWT verification — use `pyjwt` / `jose` with explicit alg whitelist.
- Sessions: HTTP-only + Secure cookies, set SameSite (Lax/Strict).

## Secrets
- Never commit `.env`, keys, tokens. `.gitignore` them upfront.
- Don't log secrets even at DEBUG. Redact before logging.
- Don't pass secrets in URL query params (they end up in logs).
- Rotate keys after any incident or sharing accidentally.

## Input validation
- Validate at the trust boundary (HTTP, CLI, file). Inside your code, trust.
- Whitelist > blacklist for accepted inputs.
- For URLs: validate scheme (http/https only), domain (allowlist for SSRF), no `file://`.
- For paths: confine to a base directory, reject `..` and absolute paths.

## File handling
- Uploaded files: validate MIME by content (magic bytes), not the Content-Type header.
- Random filename when storing — never use the uploaded name verbatim.
- Don't serve user-uploaded HTML/JS from the same origin as your app.
- Check size before reading into memory.

## Crypto
- Don't roll your own. Use `cryptography` (Python), Web Crypto API, `libsodium`.
- Use random from `secrets` (Python) / `crypto.randomBytes` (Node), never `random.random()`.
- For tokens: use long random URL-safe strings; don't construct them by hand.

## Logging / errors
- Don't return stack traces to clients. Generic error to user, full trace to logs.
- Log auth failures, but rate-limit to avoid log spam from attackers.

## Dependencies
- Audit periodically: `pip-audit`, `npm audit`, `cargo audit`.
- Pin versions. Lockfile in git.
- Be skeptical of new dependencies; each one is a supply chain risk.
