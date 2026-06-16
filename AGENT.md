# Agent Install Guide

Two entry points, same install script:

- **GitHub**: `git clone` this repo to a temp directory, `cd` into it
- **Zip**: user drags `交付自检工具_v2.5.7.zip` → extract data.zip to temp → cd into the code directory

Then:

1. Ensure Python 3.11+ with tkinter. Install if not:
   macOS: `brew install python@3.13`
   Windows: `winget install Python.Python.3.13`

2. Run: `python install_agent.py`

3. Parse each JSON line from stdout. Key actions:

   `{"action":"need_sudo","cmd":"...","reason":"..."}`
   → Ask user for password. Run the cmd with sudo. Then re-run with `--continue`.
     Example: `echo "password" | sudo -S <cmd>`

   `{"action":"need_admin","cmd":"...","reason":"..."}`
   → Tell user to Run as Administrator, or use `Start-Process -Verb RunAs`

   `{"action":"done","launch":"Workspace → Scripts → Edit → 交付自检工具"}`
   → Installation complete. Tell user in their language.

   `{"action":"error","reason":"..."}`
   → Report to user, fix the issue, retry.

4. State file at `~/.delivery_checker_install_state.json` enables resume.
   If interrupted, re-run with `--continue`.

5. After install, user launches: DaVinci Resolve → Workspace → Scripts → Edit → 交付自检工具
