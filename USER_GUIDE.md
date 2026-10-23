# SALTO Buddy - User guide

## Getting started

SALTO Buddy reads a GOLD order in SALTO for you and shows everything in one place: stage, devices, people, every tab, every sub-case and every attachment. It can also answer questions about an order in plain language (The Friendly SALTO Bot).

1. Connect to the Orange network (VPN if you work remotely).
2. Open SALTO Buddy from the Start Menu or the desktop shortcut.
3. In Order explorer, type a GOLD order number (for example 10-1764901) and press Enter.
4. The order appears in about 20 seconds. Sub-cases and FLIP serial numbers fill in by themselves afterwards (about a minute) - you can already work with what is shown.

SALTO Buddy signs in to SALTO in the background as soon as it opens. An order you have read before appears at once (saved copy) and is refreshed behind it.

Firefox works hidden in the background. When Orange asks you to sign in, SALTO Buddy asks you in its own window how to sign in (Orange PKI, Orange GroupIdentity or Microsoft Professional Account) and does the rest:

- Orange PKI: Firefox's own password window appears for a moment - type your PKI PIN there, as usual. Firefox then goes back out of sight.
- Orange GroupIdentity: type your account and password in the SALTO Buddy window.
- Microsoft Professional Account: type what Microsoft asks in the SALTO Buddy window; if it asks for a phone approval, SALTO Buddy shows the number to tap in Authenticator.

Tick 'Remember my choice' to skip the question next time (change it in Settings > General). Your password and PIN are never saved by SALTO Buddy.

## Home dashboard

Home shows the orders read on this PC at a glance: how many, in progress or completed, new devices, serial numbers found and open sub-cases, two charts (orders by stage, new devices by type) and the recent orders.

- Type an order number at the top and press Enter to open it.
- Double-click a recent order to open it again (instantly, from the saved copy).
- It fills in by itself every time an order has been read.

## Notifications

When a task is done - an order fully read (sub-cases and serial numbers included), a SALTO Bot answer, downloads - a SALTO Buddy card appears at the bottom right of the screen and the taskbar button flashes if you are in another window. Click Open to go straight to it.

- Settings > General: 'Notify me when a task is done' turns them on or off.
- 'Play a sound with notifications' adds a short sound.

## Order explorer

The top of the page shows the order, its stage bar (green done, blue current, grey to come) and key numbers. Below, one tab per job:

- Summary: the key facts - status, stage, dates, scope of work, people, sub-cases.
- Devices: the TS tab - switch between 'Scope of work' and 'All devices'.
- FLIP serial numbers: the serial number of every EQP device, read from FLIP.
- People: every participant of the case and its sub-cases, with their email, job title, manager and manager's email from the Org Chart ('Copy emails' copies them all).
- Case tabs: SALTO's own tabs of the main case (Overview, Site, Information...).
- Sub-cases: pick EQP, CONF, SG, INV... on the left; its tabs appear as buttons.
- Files: attachments (download what you need) and your screenshots.

Tables: click a column title to sort, Ctrl+C or right-click to copy rows into Excel.

## FLIP serial numbers

For every EQP of the order, SALTO Buddy follows the same path you would: EQP > Information > rocket > Intervention Id > FLIP > Work Flow Action Items > Open Part Request > Export. It then matches each SALTO device to its FLIP part with the same OBS name and the device model, so you get the serial number of the device itself (not its power supplies or SFPs).

- FLIP serial numbers tab: one row per device with its serial number, and below it every FLIP part.
- Check column: OK when exactly one part matched; otherwise it tells you what to look at.
- The FLIP export (Excel) is saved in the order folder, Downloads\FLIP.
- The Friendly SALTO Bot can answer it too: 'serial numbers of the devices in creation'.
- Nothing is ever changed in FLIP: only 'Open Part Request' and 'Export' are used.

## HOTO preparation

The HOTO sheet of a LAN project, filled from the order open in Order explorer: one row per device in creation (devices being ceased or modified are left out).

1. Open the order in Order explorer.
2. Go to the HOTO preparation tab: the rows are already filled. Serial numbers fill in as soon as FLIP has been read.
3. Click 'Save HOTO Excel' (saved in the order folder by default), or 'Copy all rows' and paste them into your HOTO document.

The Excel has two sheets. 'HOTO': a ready-to-share template - title, an order block (GOLD ref, customer, site, go-live, project manager, STC case, date), the devices grouped by type with counts, yellow columns to fill in by hand (admin / customer IP), amber serial numbers to check, and a total. 'Plain list': the same rows without layout, to paste anywhere.

- Go Live Date: the case's target delivery date. Change it in Excel if the go-live is planned differently.
- Project Manager: the case's Project Manager participant, empty when there is none.
- City, Country, Site address, Site ID and the local contact come from the Site tab (Primary Contact).
- Device Name is the customer device name; Switch number comes from it (skf-sw-itvil-01_02 -> 01_02). In a stack, member 01 is the Master; the others show their master's name.
- Device Type: SW, AP, WLC, RTR or FW, from the device type.
- Device SN#: from FLIP. A highlighted cell means it is missing, or FLIP lists several serial numbers for the device: check it in the FLIP serial numbers tab.
- Admin and customer IP addresses are not in SALTO: fill them in Excel.

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

## Org Chart (emails and managers)

SALTO Buddy reads the Orange Business Org Chart for you: a person's email, job title, department, phone and who they report to, with every manager's email.

- People tab of an order: filled by itself once the order is read (a few seconds). Customer contacts are not in the Org Chart: their emails are in the Site and Commercial Content tabs.
- Org Chart tab: type a last name, a first name or an email (partial names work) and press Enter. Select a person to see their management chain: manager, 2nd-level manager and so on, with emails.
- The Friendly SALTO Bot: 'What is the email of Ahmed Khairy's manager?' works too.
- Results are kept for a week; 'Refresh' in the People tab reads them again.

## The Friendly SALTO Bot (chat)

Ask questions about an order in your own words, for example 'What is the site address?', 'Serial numbers of the devices in creation', 'Who is the local delivery manager?'.

1. Open an order in Order explorer (or just name the order in your question).
2. Click SALTO Bot in the menu, type your question and press Enter.
3. The bot reads the order and answers as it writes, saying which case and tab the answer comes from.

### Documents

Click the paperclip next to the message box to attach Word (.docx), PDF or text files - a customer request, a HOTO or handover form, an email saved as text. Add a question, or just press Send: the bot reads the document and does what it asks when it can.

- It looks up the orders the document names (and opens them in SALTO if needed), checks the document against SALTO and FLIP (devices, models, serial numbers, sites, contacts) and tells you what matches and what differs.
- It finds people in the Org Chart, prepares the HOTO Excel sheet or exports an order to Excel when the document asks for it. Files it creates appear as 'Open ...' buttons under its answer.
- It never changes anything in SALTO and never sends emails: if the document asks for that, it tells you what to do.
- Old Word files (.doc): open them in Word and save them as .docx first. Attached documents are sent to Claude (Anthropic) with your question.

Chats are saved on this PC and listed on the left, grouped by order number: click one to read it again or to continue it (Buddy remembers the conversation). '+ New chat' starts a fresh one; right-click a chat to delete it.

Answers start with the short answer, then the details: bullets for a few facts, a table for lists (devices, serial numbers, sub-cases...). Click a table's column title to sort it. 'Copy answer' under each answer copies it as clean text: tables paste as columns in Excel and as text in Outlook.

The bot only uses what SALTO shows. If a field does not exist in SALTO (for example a serial number), it says so and offers the closest fields. Answers come from Claude (Anthropic): your question and the order data it needs are sent there.

### The team key (nothing to do)

The bot uses the team's shared Claude key. The first time you ask a question, SALTO Buddy gets it from the team SharePoint folder by itself (about 30 seconds) with your Orange Microsoft account, then keeps it encrypted on your PC. If Microsoft ever asks you to sign in, Firefox appears: sign in once and Buddy carries on.

Have your own key? Settings > SALTO Bot > paste it, Test, Done. Your own key is used first.

## Settings

- Save folder for orders.
- Show the Firefox window (normally hidden).
- Sign in to SALTO with: Ask me, or always the same way (Orange PKI, GroupIdentity, Microsoft).
- Open every sub-case / download all attachments automatically / screenshot every tab.
- Read the full audit history (slower): by default only the latest audit page is read.
- Check for updates at start.
- SALTO Bot: your own Claude key (optional - the team key is used otherwise).

## Updates

SALTO Buddy checks for a new version every time it starts. When there is one, the header button turns orange ('Update to x.y.z'): click it, read what's new, then 'Download and install'. The app closes, installs and opens again by itself. After an update, a short walkthrough shows what changed.

## Troubleshooting

- Red pill 'Offline - waiting for network': connect the VPN; SALTO Buddy carries on by itself.
- Sign-in does not finish: click 'Show Firefox instead' in the sign-in window (or turn on 'Show the Firefox window' in Settings) and complete it there.
- No PKI password window: make sure your Orange smart card or PKI certificate is ready, then open the order again.
- The SALTO Bot cannot get the team key: check you are on the Orange network and can open the team SharePoint folder; or add your own key in Settings.
- 'SALTO Buddy is already open': it is running - look in the taskbar.
- Anything else: click 'Show activity' at the bottom and send a screenshot of it.
