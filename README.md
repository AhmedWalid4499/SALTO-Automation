# SALTO Buddy

Desktop app that drives SALTO (Pega) in Firefox and pulls everything about an order in one click.

## Install

Download `SALTO-Buddy-Setup-<version>.exe` from the
[latest release](https://github.com/AhmedWalid4499/SALTO-Automation/releases/latest) and run it
(no admin rights needed). It installs to `%LOCALAPPDATA%\Programs\SALTO Buddy` and adds Start Menu and desktop shortcuts.

## Use

1. Type a commercial order reference and press **Enter** (or **Get data**).
2. SALTO Buddy opens its own Firefox window. It clicks *Login with OpenID* and *professional account* for you.
   If Orange asks for anything else (password, MFA), finish it in that window. The sign-in is remembered.
3. It searches STC Search, opens the first STC and reads the whole case.

| Result | What you get |
|---|---|
| Cards | STC, status, **current stage**, EQPs, scope-of-work device count, participants |
| Stage bar | completed (green), current (blue), pending (grey) |
| Summary | all the key facts in one table |
| Scope of work devices | each TS product node with *Scope of work only* ticked: added / modified / ceased counts and the device list |
| Participants | name and role |
| SALTO case tabs | Overview, Commercial Content, Site, Information, Attachments, Audit, Event, each with one inner tab per section or table |
| Search results | every STC Search row for the order |

Turn off **Read all tabs** for a quick lookup (stage and EQPs only).
**Export to Excel** saves everything (one sheet per area).
In any table, Ctrl+C or right-click copies rows, ready to paste into Excel. Click a column header to sort.

## Updates

Every time SALTO Buddy starts, it checks this repo's latest GitHub release. If a newer version exists,
an **Update available** button appears in the sidebar and a dialog offers **Download and install**.
The installer runs silently and SALTO Buddy restarts on the new version.
You can turn the check off, or run it by hand, in **Settings**.

### Publishing a new version

1. Bump `__version__` in `salto/version.py`.
2. Run `.\release.ps1 -Notes "What changed"`. It:
   - builds the installer,
   - commits and pushes the code,
   - tags the commit `vX.Y.Z`,
   - creates the GitHub release with the installer attached.

Before the first release, sign in the GitHub CLI once with `gh auth login`.
To only build the installer without publishing, run `.\build.ps1`.

To build you need Python 3.12 (`pip install -r requirements.txt`) and Inno Setup 6.

## Adding a feature

Each feature is a page in the sidebar.

1. Create `features/my_feature.py`:

```python
import customtkinter as ctk
from ui import theme as T, widgets as W
from .base import Feature

class MyFeature(Feature):
    title = "My feature"

    def build(self, parent):
        btn = ctk.CTkButton(parent, text="Run", fg_color=T.ORANGE,
                            command=lambda: self.run(self.work, self.done, busy_widgets=(btn,)))
        btn.pack(padx=28, pady=22, anchor="w")

    def work(self, b):          # runs on the browser thread; b = SaltoBrowser
        b.ensure_logged_in()
        ...                     # use salto.actions / salto.case helpers
        return result

    def done(self, result):     # back on the GUI thread
        ...
```

2. Add it to `FEATURES` in `features/__init__.py`.

### Building blocks

| Module | Contents |
|---|---|
| `salto/actions.py` | `search_order`, `open_case`, `read_stages`, `read_eqps`, `order_lookup` |
| `salto/case.py` | `open_tab`, `extract` (generic reader for Pega fields and tables), `read_ts_scope`, `read_participants`, `read_case` |
| `salto/browser.py` | `find_visible(xpath)` and `frame_with_text(...)`, which search across Pega iframes |
| `ui/widgets.py` | `table`, `kv_table`, `tabs`, `card`, `stat_card`, `stepper`, `empty` |
| `ui/theme.py` | colours and fonts |

## Run from source

```
pip install -r requirements.txt
py app.py              # app
py cli.py 10-1234567   # command line
```
