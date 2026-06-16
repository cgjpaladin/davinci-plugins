# Agent Install Guide

Two entry points, same script:

- **GitHub**: `git clone` this repo to a temp directory, `cd` into it
- **Zip**: user drags `交付自检工具_v2.5.7.zip` → unzip outer zip → extract `data.zip` to a temp dir → `cd 交付自检工具 && python install_agent.py`

Then:

1. Ensure Python 3.11+ (with tkinter) is available. Install if not:
   - macOS: `brew install python@3.13`
   - Windows: `winget install Python.Python.3.13` or download from python.org
3. Run: `python install_agent.py`
4. Parse each JSON line. Key actions:
   - `need_sudo` → ask user for password, run the `cmd` with sudo, then re-run with `--continue`
   - `need_admin` → tell user to right-click and run as admin, or use `Start-Process -Verb RunAs`
   - `done` → tell user: "达芬奇里 Workspace → Scripts → Edit → 交付自检工具"
   - `error` → report to user, fix the issue, retry
5. Installer uses a state file at `~/.delivery_checker_install_state.json` for resume.
   If interrupted, just re-run with `--continue`.
6. No other user interaction required.
