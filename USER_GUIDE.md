# SALTO Buddy - User guide

## Getting started

SALTO Buddy reads a GOLD order in SALTO for you and shows everything in one place: stage, devices, people, every tab, every sub-case and every attachment. It can also answer questions about an order in plain language (Ask Buddy).

1. Connect to the Orange network (VPN if you work remotely).
2. Open SALTO Buddy from the Start Menu or the desktop shortcut.
3. In Order explorer, type a GOLD order number (for example 10-1764901) and press Enter.
4. Wait for the green pill 'Connected to SALTO' and the order to appear (a few minutes for a big order: every sub-case is opened).

Firefox works hidden in the background. The first time, the Orange sign-in is done for you; if Orange ever needs your password or MFA, Firefox appears so you can finish it.

## Order explorer

The top of the page shows the order, its stage bar (green done, blue current, grey to come) and key numbers. Below, one tab per job:

- Summary: the key facts - status, stage, dates, scope of work, people, sub-cases.
- Devices: the TS tab - switch between 'Scope of work' and 'All devices'.
- People: every participant of the case and its sub-cases.
- Case tabs: SALTO's own tabs of the main case (Overview, Site, Information...).
- Sub-cases: pick EQP, CONF, SG, INV... on the left; its tabs appear as buttons.
- Files: attachments (download what you need) and your screenshots.

Tables: click a column title to sort, Ctrl+C or right-click to copy rows into Excel.

## Downloads

1. Open the order, then the Files tab.
2. Select the attachments you need (Ctrl+click or Shift+click for several).
3. Click 'Download selected' (or 'Download all').
4. Double-click a downloaded row to open it.

Files keep their format (PDF, Excel, .msg...). E-mails stored in SALTO are saved as PDF.

## Screenshots

- Screenshot: saves the whole SALTO page that is open, not only the visible part.
- Capture a part: click any section, table or field in Firefox to save just that part (needs 'Show the Firefox window' in Settings). Esc cancels.

## Where files are saved

Everything for an order goes to <Save folder>\<GOLD order> - <STC>\ with Downloads\ (one folder per case) and Screenshots\. Export to Excel saves <order>.xlsx there. Change the save folder in Settings (default: Documents\SALTO Buddy). 'Open folder' opens it.

## Ask Buddy (chat)

Ask questions about an order in your own words, for example 'What is the site address?', 'Serial numbers of the devices in creation', 'Who is the local delivery manager?'.

1. Open an order in Order explorer (or just name the order in your question).
2. Go to the Ask Buddy tab and type your question, then Enter.
3. Buddy reads the order and answers, saying which case and tab the answer comes from.

Buddy only uses what SALTO shows. If a field does not exist in SALTO (for example a serial number), it says so and offers the closest fields. Answers come from Claude (Anthropic): your question and the order data it needs are sent there.

### Getting Ask Buddy ready (team key)

1. Open the team's 'SALTO Buddy' SharePoint folder (the link your team lead shared).
2. Click 'Sync' (or 'Add shortcut to My files') so it appears in File Explorer.
3. Restart SALTO Buddy: it finds the team key by itself.
4. Not found? Settings > Ask Buddy > Team key folder > Browse, pick the synced folder, Done.

## Settings

- Save folder for orders.
- Show the Firefox window (normally hidden).
- Open every sub-case / download all attachments automatically / screenshot every tab.
- Check for updates at start.
- Ask Buddy: your own Claude key (optional), or the team key folder.

## Updates

SALTO Buddy checks for a new version every time it starts. When there is one, the header button turns orange ('Update to x.y.z'): click it, read what's new, then 'Download and install'. The app closes, installs and opens again by itself. After an update, a short walkthrough shows what changed.

## Troubleshooting

- Red pill 'Offline - waiting for network': connect the VPN; SALTO Buddy carries on by itself.
- Sign-in does not finish: turn on 'Show the Firefox window' in Settings and complete it there.
- Ask Buddy says it needs a key: get the team key ready (Ask Buddy section above).
- 'SALTO Buddy is already open': it is running - look in the taskbar.
- Anything else: click 'Show activity' at the bottom and send a screenshot of it.
