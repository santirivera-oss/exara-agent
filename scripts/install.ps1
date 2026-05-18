# One-line installer for exara-agent on Windows.
#
#   iwr https://raw.githubusercontent.com/santirivera-oss/exara-agent/main/scripts/install.ps1 | iex
#
# What it does:
#   1. Verifies Python >= 3.12 (suggests winget install if missing)
#   2. Installs pipx via `python -m pip install --user pipx`
#   3. Installs exara-agent into an isolated pipx venv
#   4. Adds pipx's Scripts dir to the current session PATH
#   5. Runs `exara init`
#
# Re-runnable: if exara is already installed, it upgrades to the latest version.

$ErrorActionPreference = "Stop"

function Write-Ok    ($m) { Write-Host "✓ $m" -ForegroundColor Green }
function Write-Warn  ($m) { Write-Host "⚠ $m" -ForegroundColor Yellow }
function Write-Err   ($m) { Write-Host "✗ $m" -ForegroundColor Red }
function Write-Info  ($m) { Write-Host "→ $m" -ForegroundColor Cyan }

# --- 1. Python ---------------------------------------------------------------
$py = $null
foreach ($candidate in @("python", "py", "python3", "python3.13", "python3.12")) {
    $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
    if ($null -ne $cmd) {
        try {
            $out = & $candidate -c "import sys; print('ok' if sys.version_info >= (3,12) else 'old')" 2>$null
            if ($out -eq "ok") { $py = $candidate; break }
        } catch { }
    }
}

if ($null -eq $py) {
    Write-Err "Python >= 3.12 not found."
    Write-Host "  Install via:  winget install Python.Python.3.13"
    Write-Host "  Or download:  https://python.org/downloads/"
    exit 1
}
Write-Ok "Found $(& $py --version) at $((Get-Command $py).Source)"

# --- 2. pipx -----------------------------------------------------------------
$pipxCmd = Get-Command pipx -ErrorAction SilentlyContinue
if ($null -eq $pipxCmd) {
    Write-Info "Installing pipx (user-level)..."
    & $py -m pip install --user --quiet pipx
    & $py -m pipx ensurepath
    $userBase = (& $py -m site --user-base).Trim()
    $env:PATH = "$userBase\Scripts;$env:PATH"
    Write-Ok "Installed pipx at $userBase\Scripts\pipx.exe"
} else {
    Write-Ok "pipx is already installed"
}

# --- 3. exara-agent ----------------------------------------------------------
$installed = $false
try {
    $list = pipx list 2>$null
    if ($list -match "package exara-agent") { $installed = $true }
} catch { }

if ($installed) {
    Write-Info "exara-agent already installed — upgrading..."
    pipx upgrade exara-agent
} else {
    Write-Info "Installing exara-agent (this can take a minute)..."
    pipx install exara-agent
}
Write-Ok "exara-agent installed"

# --- 4. PATH sanity for the current session ---------------------------------
$exaraCmd = Get-Command exara -ErrorAction SilentlyContinue
if ($null -eq $exaraCmd) {
    Write-Warn "'exara' is not on your PATH for this session."
    Write-Host "    Open a new PowerShell window (pipx already updated PATH for future sessions)."
}

# --- 5. Wizard ---------------------------------------------------------------
Write-Host ""
if ($env:EXARA_NO_INIT -eq "1") {
    Write-Info "EXARA_NO_INIT=1 — skipping the setup wizard."
    Write-Host "Run it manually later with:  exara init"
} else {
    $exaraCmd = Get-Command exara -ErrorAction SilentlyContinue
    if ($null -ne $exaraCmd) {
        Write-Info "Launching the setup wizard..."
        & exara init
    } else {
        Write-Info "Run 'exara init' after re-opening PowerShell."
    }
}
