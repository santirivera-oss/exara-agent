#!/usr/bin/env bash
# One-line installer for exara-agent on macOS / Linux.
#
#   curl -sSL https://raw.githubusercontent.com/santirivera-oss/exara-agent/main/scripts/install.sh | bash
#
# What it does:
#   1. Verifies Python >= 3.12
#   2. Installs pipx (in user space) if missing
#   3. Installs exara-agent into an isolated pipx venv
#   4. Adds pipx's bin dir to PATH (best effort, prints instructions otherwise)
#   5. Optionally runs `exara init` to walk you through provider setup
#
# Re-runnable: if exara is already installed, it upgrades to the latest version.

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
ok()    { printf "${GREEN}✓${NC} %s\n" "$*"; }
warn()  { printf "${YELLOW}⚠${NC}  %s\n" "$*"; }
err()   { printf "${RED}✗${NC} %s\n" "$*" >&2; }
info()  { printf "${CYAN}→${NC} %s\n" "$*"; }

# --- 1. Python ---------------------------------------------------------------
PY=""
for candidate in python3.13 python3.12 python3 python; do
  if command -v "$candidate" >/dev/null 2>&1; then
    if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3,12) else 1)' 2>/dev/null; then
      PY="$candidate"
      break
    fi
  fi
done

if [[ -z "$PY" ]]; then
  err "Python >= 3.12 not found."
  echo "  macOS:  brew install python@3.13"
  echo "  Linux:  use pyenv or your distro's package manager"
  exit 1
fi
ok "Found $($PY --version) at $(command -v "$PY")"

# --- 2. pipx -----------------------------------------------------------------
if ! command -v pipx >/dev/null 2>&1; then
  info "Installing pipx (user-level)..."
  "$PY" -m pip install --user --quiet pipx
  "$PY" -m pipx ensurepath
  # The ensurepath call modifies shell rc files but won't affect this process.
  # Find pipx by re-resolving via Python.
  PIPX_BIN="$("$PY" -m site --user-base)/bin"
  export PATH="$PIPX_BIN:$PATH"
  ok "Installed pipx at $PIPX_BIN/pipx"
else
  ok "pipx is already installed"
fi

# --- 3. exara-agent ----------------------------------------------------------
if pipx list 2>/dev/null | grep -q "package exara-agent"; then
  info "exara-agent already installed — upgrading..."
  pipx upgrade exara-agent
else
  info "Installing exara-agent (this can take a minute)..."
  pipx install exara-agent
fi
ok "exara-agent installed"

# --- 4. PATH sanity ----------------------------------------------------------
if ! command -v exara >/dev/null 2>&1; then
  warn "'exara' is not on your PATH. Add this to your shell rc and reopen:"
  echo "    export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

# --- 5. Wizard ---------------------------------------------------------------
echo
if [[ "${EXARA_NO_INIT:-}" == "1" ]]; then
  info "EXARA_NO_INIT=1 — skipping the setup wizard."
  echo "Run it manually later with:  exara init"
else
  if command -v exara >/dev/null 2>&1; then
    info "Launching the setup wizard..."
    exec exara init
  else
    info "Run 'exara init' after re-opening your shell."
  fi
fi
