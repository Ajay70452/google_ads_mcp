# Installation Guide — MethodPro Google Ads AI Suite

Standard operating procedure for setting up the Google Ads AI Suite on a teammate's device.

This guide is split into **Windows** and **Mac** sections. Pick the one that matches the user's machine and run through it top-to-bottom. Each section is self-contained — don't mix steps across them.

**Estimated time per setup:** 15–20 minutes.

> **Best practice:** do this on a screen-share / Zoom call with the user. Less room for typos in paths, and you can validate each step in real time.

---

## Before you start (both platforms)

You'll need to give the user three things up front:

1. **GitHub access** to https://github.com/Ajay70452/google_ads_mcp (read access is enough)
2. **The production backend URL** — currently `http://184.33.29.155:8001`
3. **A copy of this guide** open on a second screen

You'll also be running git, so make sure their GitHub account is added as a collaborator on the repo if it's still private.

---

# Windows Installation

## Step 1 — Install prerequisites

Open **PowerShell** (search "PowerShell" in Start menu, right-click → Run as Administrator).

### 1a. Install Python 3.11

Go to https://www.python.org/downloads/ and download Python **3.11.x** (not 3.12+ — the Google Ads SDK has 3.11 as its target).

During the installer:
- ✅ Check **"Add Python to PATH"** (very important — easy to miss)
- Click **Install Now**

Verify in PowerShell:

```powershell
python --version
```

Should print `Python 3.11.x`. If it says "command not found," Python wasn't added to PATH — reinstall and check the box.

### 1b. Install Git

Download from https://git-scm.com/download/win and install with default options.

Verify:

```powershell
git --version
```

### 1c. Install Claude Desktop

Download from https://claude.ai/download → run the installer → sign in with their MethodPro Google account.

## Step 2 — Clone the repo

Pick a permanent home for the code. We'll use `C:\Projects\` as the convention.

```powershell
mkdir C:\Projects -Force
cd C:\Projects
git clone https://github.com/Ajay70452/google_ads_mcp.git
cd google_ads_mcp
```

When git prompts for credentials, the user logs in with their GitHub account. (If it doesn't prompt and just fails, install GitHub Desktop or set up credentials via `gh auth login`.)

## Step 3 — Set up the Python environment

Install **uv** (fast Python package manager — what the repo uses):

```powershell
pip install uv
```

Create the virtual environment and install dependencies:

```powershell
uv sync
```

This will create a `.venv` folder and install ~30 packages. Takes 1–2 minutes.

Verify it worked:

```powershell
.\.venv\Scripts\python.exe -c "from mcp_server import server; print('ok')"
```

Should print `ok`. If it errors, paste the error and stop here — don't proceed until this passes.

## Step 4 — Capture the paths you'll need

Run these and **note down the exact output** — you'll paste them into the config in the next step:

```powershell
# This is the COMMAND path
echo "$(Get-Location)\.venv\Scripts\python.exe"

# This is the PYTHONPATH
Get-Location | Select-Object -ExpandProperty Path
```

Example output:
```
C:\Projects\google_ads_mcp\.venv\Scripts\python.exe
C:\Projects\google_ads_mcp
```

## Step 5 — Create the Claude Desktop config

The config lives at:

```
C:\Users\<username>\AppData\Roaming\Claude\claude_desktop_config.json
```

Open it (or create it if missing):

```powershell
notepad "$env:APPDATA\Claude\claude_desktop_config.json"
```

If Notepad asks "Do you want to create a new file?" → click Yes.

Paste this content, replacing the two paths with what you captured in Step 4:

```json
{
  "mcpServers": {
    "google-ads": {
      "command": "C:/Projects/google_ads_mcp/.venv/Scripts/python.exe",
      "args": ["-m", "mcp_server.server"],
      "env": {
        "BACKEND_URL": "http://184.33.29.155:8001",
        "PYTHONPATH": "C:/Projects/google_ads_mcp"
      }
    }
  }
}
```

**Critical Windows notes:**
- Use **forward slashes** (`/`) in the JSON, not backslashes — JSON treats `\` as an escape character. `C:/Projects/...` works; `C:\Projects\...` will fail to parse
- Use the **full path including drive letter** — no `~` shortcuts
- Save with **File → Save** (`Ctrl+S`), then close Notepad

## Step 6 — Validate the JSON

```powershell
Get-Content "$env:APPDATA\Claude\claude_desktop_config.json" | python -m json.tool
```

If valid, it reprints the JSON formatted. If invalid, it points to the syntax error — fix it.

## Step 7 — Verify paths exist

```powershell
Test-Path "C:\Projects\google_ads_mcp\.venv\Scripts\python.exe"
Test-Path "C:\Projects\google_ads_mcp\mcp_server\server.py"
```

Both should print `True`. If either prints `False`, the path is wrong — fix the config.

## Step 8 — Quit Claude Desktop completely

This trips up everyone. Closing the window doesn't quit Claude — it minimizes to the system tray.

- Look at the **system tray** (bottom-right of screen, click the `^` to expand if hidden)
- Right-click the **Claude icon** → **Quit**
- Wait 5 seconds

## Step 9 — Reopen Claude Desktop and test

Launch Claude Desktop fresh. Open a new chat and type:

> *"List all our Google Ads accounts"*

Expected: a list of 40 clinics. If it works, the install is complete.

## Step 10 — Smoke test the agents end-to-end

Have them try these in sequence to confirm everything wired up:

> *"Show me Apex Dental Group's performance last 7 days"*

> *"Generate the YTD report"*

> *"What search terms are wasting budget for Jaeger Orthodontics?"*

If all three work, the install is verified.

---

# Mac Installation

## Step 1 — Install prerequisites

Open **Terminal** (Cmd+Space → type "Terminal" → Enter).

### 1a. Install Homebrew

If they don't already have it:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Follow the on-screen prompts (it'll ask for their Mac password). After install, it usually prints two lines to add Homebrew to PATH — run those exactly as printed.

Verify:

```bash
brew --version
```

### 1b. Install Python 3.11, Git, and uv

```bash
brew install python@3.11 git uv
```

Verify:

```bash
python3.11 --version
git --version
uv --version
```

### 1c. Install Claude Desktop

Download the macOS `.dmg` from https://claude.ai/download → drag Claude into Applications → open → sign in with MethodPro Google account.

## Step 2 — Clone the repo

We'll put it directly in their home folder for simplicity:

```bash
cd ~
git clone https://github.com/Ajay70452/google_ads_mcp.git
cd google_ads_mcp
```

## Step 3 — Set up the Python environment

```bash
uv sync
```

Takes 1–2 minutes. Verify:

```bash
.venv/bin/python -c "from mcp_server import server; print('ok')"
```

Should print `ok`. If it errors, stop and debug before continuing.

## Step 4 — Capture the paths

```bash
echo "$(pwd)/.venv/bin/python"
echo "$(pwd)"
```

Example output:
```
/Users/pooja/google_ads_mcp/.venv/bin/python
/Users/pooja/google_ads_mcp
```

Note these down — you'll paste them into the config.

## Step 5 — Create the Claude Desktop config

The Mac config location is:

```
~/Library/Application Support/Claude/claude_desktop_config.json
```

Make sure the folder exists, then open the file in nano:

```bash
mkdir -p ~/Library/Application\ Support/Claude
nano ~/Library/Application\ Support/Claude/claude_desktop_config.json
```

Paste this, **replacing the username** with theirs (and adjusting paths if the repo lives elsewhere):

```json
{
  "mcpServers": {
    "google-ads": {
      "command": "/Users/pooja/google_ads_mcp/.venv/bin/python",
      "args": ["-m", "mcp_server.server"],
      "env": {
        "BACKEND_URL": "http://184.33.29.155:8001",
        "PYTHONPATH": "/Users/pooja/google_ads_mcp"
      }
    }
  }
}
```

**Critical Mac notes:**
- Use **forward slashes** (already standard on Mac)
- Use **absolute paths starting with `/Users/...`** — `~` shortcut doesn't expand inside JSON
- The Python path is `.venv/bin/python` (Mac/Linux), **not** `.venv/Scripts/python.exe` (Windows)

Save in nano:
- `Ctrl+O` → Enter (writes the file)
- `Ctrl+X` (exits nano)

## Step 6 — Validate the JSON

```bash
cat ~/Library/Application\ Support/Claude/claude_desktop_config.json | python3 -m json.tool
```

If valid, it reprints formatted. If invalid, it points to the syntax error.

## Step 7 — Verify paths exist

```bash
ls /Users/pooja/google_ads_mcp/.venv/bin/python
ls /Users/pooja/google_ads_mcp/mcp_server/server.py
```

Both should print the path back. If either prints "No such file or directory," fix the config.

## Step 8 — Quit Claude Desktop completely

On Mac, closing the window doesn't quit the app — same trap as Windows.

- With Claude focused: **Cmd+Q**, OR
- Right-click the Claude icon in the **menu bar** (top-right of screen) → **Quit**
- Wait 5 seconds

## Step 9 — Reopen Claude Desktop and test

Launch Claude Desktop fresh from Applications. Open a new chat and type:

> *"List all our Google Ads accounts"*

Expected: a list of 40 clinics.

## Step 10 — Smoke test

Same as Windows step 10:

> *"Show me Apex Dental Group's performance last 7 days"*
> *"Generate the YTD report"*
> *"What search terms are wasting budget for Jaeger Orthodontics?"*

---

# Troubleshooting

If any step above fails, walk through this section.

## "Tools don't appear in Claude Desktop at all"

**Cause:** Claude Desktop didn't load the config, or didn't fully restart.

Fix:
1. Confirm the config file is at the right path (Win: `%APPDATA%\Claude\claude_desktop_config.json`, Mac: `~/Library/Application Support/Claude/claude_desktop_config.json`)
2. Run the JSON validation command from Step 6 — fix any syntax errors
3. Fully quit Claude (system tray on Win, Cmd+Q + menu bar on Mac), wait 10 seconds, reopen

## "Failed to start MCP server" / "google-ads server not connected"

**Cause:** Claude tried to launch the Python process but it crashed or the path was wrong.

Fix:
1. Run the `command` path manually in a terminal:
   - Windows: `& "C:\Projects\google_ads_mcp\.venv\Scripts\python.exe" -m mcp_server.server`
   - Mac: `/Users/pooja/google_ads_mcp/.venv/bin/python -m mcp_server.server`
2. It should sit waiting for input (no error). Press Ctrl+C to exit.
3. If you see an `ImportError`, the venv is broken — re-run `uv sync`
4. If you see "command not found" or "no such file," the path in the config is wrong

## "Connection refused" / "couldn't reach backend"

**Cause:** Their network can't reach the EC2 instance.

Fix:
1. Test reachability:
   - Windows or Mac: `curl http://184.33.29.155:8001/health`
2. Should return `{"status":"ok"}`. If it times out, either:
   - They're on a corporate VPN that blocks the IP — try off-VPN
   - The EC2 instance is down — check from your machine
   - The EC2 security group doesn't allow their IP — currently set to `0.0.0.0/0` so this shouldn't happen, but verify in AWS Console

## "git clone" fails with "permission denied"

**Cause:** Their GitHub account doesn't have repo access.

Fix: Add them as a collaborator at https://github.com/Ajay70452/google_ads_mcp/settings/access. They may need to authenticate via `gh auth login` or the OS credential manager.

## "uv sync" fails

**Cause:** Usually a Python version mismatch or a network issue.

Fix:
1. Confirm Python 3.11 is the active version: `python --version` (Win) or `python3.11 --version` (Mac)
2. If it picks the wrong version, force it: `uv sync --python python3.11`
3. If it's a download timeout, retry. uv caches everything after the first success.

## Claude returns "I don't have access to that tool"

**Cause:** Tools are registered but the user is on the website (claude.ai), not Desktop.

Fix: Make sure they're using the **Claude Desktop app**, not the website. MCP only works through Desktop.

---

# Updating an existing install

When the engineering team pushes new code:

**If only the backend changed (most common):**
- Nothing to do on the user's machine. CI/CD updates the cloud automatically. Their next tool call hits the new code.

**If the MCP server itself changed (rare — like adding a new tool):**

```bash
# Windows or Mac, same commands
cd <repo path>      # C:\Projects\google_ads_mcp or ~/google_ads_mcp
git pull
uv sync             # only if dependencies changed
```

Then quit + reopen Claude Desktop.

---

# Quick reference card

Print this and tape it to the user's monitor.

| Action | Windows | Mac |
|---|---|---|
| Repo location | `C:\Projects\google_ads_mcp` | `~/google_ads_mcp` |
| Config file | `%APPDATA%\Claude\claude_desktop_config.json` | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Python in venv | `.\.venv\Scripts\python.exe` | `.venv/bin/python` |
| Quit Claude Desktop | System tray icon → Quit | Cmd+Q or menu bar icon → Quit |
| Test backend reachable | `curl http://184.33.29.155:8001/health` | same |
| Pull updates | `git pull` then `uv sync` | same |

---

*If the production IP or repo URL changes, update the references in this doc.*
