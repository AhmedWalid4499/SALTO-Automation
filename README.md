# SALTO Buddy

Desktop app that drives SALTO (Pega) in Firefox and pulls everything about an order in one click.

## Install

Download `SALTO-Buddy-Setup-<version>.exe` from the
[latest release](https://github.com/AhmedWalid4499/SALTO-Automation/releases/latest) and run it
(no admin rights needed). It installs to `%LOCALAPPDATA%\Programs\SALTO Buddy` and adds Start Menu and desktop shortcuts.

## Use

1. In **Order explorer**, type a GOLD order number and press **Enter** (or **Open order**).
2. SALTO Buddy opens its own Firefox window. It clicks *Login with OpenID* and *professional account* for you.
   If Orange asks for anything else (password, MFA), finish it in that window. The sign-in is remembered.
3. It searches STC Search, opens the first STC and dissects the whole order:
   - every tab of the case;
   - every page of the Audit history;
   - the TS devices: all devices, and the *Scope of work only* view;
   - the participants;
   - every sub-case in the Overview tree (EQP, CONF, SG, INV, PAG...), each with its own stages, people and tabs;
   - all attachments, downloaded. Files are saved as they are; emails are saved as PDF.

| Area | What you get |
|---|---|
| Cards | STC, status, **current stage**, EQPs, scope devices, participants, sub-cases, files |
| Stage bar | completed (green), current (blue), pending (grey) |
| Left list | Summary, Scope of work devices, All devices, Participants, the case and its tabs, Sub-cases (each with its tabs), Downloads, Screenshots, Search results. It follows whatever tabs each order has. |
| Detail view | orange section headings, labels and values that wrap to the window, tables inline |

The **Open every sub-case**, **Download attachments** and **Screenshot every tab** options make a run faster or more complete.
In any table, Ctrl+C or right-click copies rows, ready to paste into Excel. Click a column header to sort.
In Downloads and Screenshots, double-click a row to open the file.

### Screenshots

- **Screenshot SALTO** saves what Firefox shows now.
- **Pick & capture** highlights whatever is under your mouse in Firefox. Click a section, table or field and only that part is saved. Esc cancels.

Files are named `<case>_<tab>_<n>.png`.

### Where files go

Everything for an order is saved in `<Save folder>\<GOLD order> - <STC>\`:

```
10-1234567 - MLAN-123456\
    Downloads\MLAN-123456\...   attachments of the main case
    Downloads\EQP-123456\...    attachments of each sub-case
    Screenshots\...
    10-1234567.xlsx             Export to Excel
```

Change the save folder in **Settings** (the default is `Documents\SALTO Buddy`).

## Updates

Every time SALTO Buddy starts, it checks this repo's latest GitHub release. If a newer version exists,
the header button turns orange (**Update to x.y.z**) and a dialog offers **Download and install**.
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

Each feature is one tab (one job per tab).

1. Create `features/my_feature.py`:

```python
from tkinter import ttk
from .base import Feature

class MyFeature(Feature):
    title = "My feature"

    def build(self, parent):
        btn = ttk.Button(parent, text="Run", style="Accent.TButton",
                         command=lambda: self.run(self.work, self.done, busy_widgets=(btn,)))
        btn.pack(anchor="w")

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
| `salto/case.py` | `open_tab`, `extract` (generic reader for Pega fields and tables), `read_ts`, `read_audit`, `read_attachments`, `open_subcase`, `read_case` |
| `salto/capture.py` | `screenshot_screen`, `pick_and_capture` |
| `salto/files.py` | `order_folder`, `sub`, `numbered`, download helpers |
| `salto/browser.py` | `find_visible(xpath)` and `frame_with_text(...)`, which search across Pega iframes |
| `ui/widgets.py` | `Table`, `DetailView`, `StatusCard`, `Stepper`, `ThinProgress`, `Pill` |
| `ui/theme.py` | design tokens (colours, fonts) and ttk styles |

## Run from source

```
pip install -r requirements.txt
py app.py              # app
py cli.py 10-1234567   # command line
```
