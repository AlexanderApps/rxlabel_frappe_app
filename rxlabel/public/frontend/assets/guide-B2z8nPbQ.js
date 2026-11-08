const e=`# How to use RxLabel

## Before you start

You need a Windows computer, a supported label printer connected by USB, the DTPWeb print assistant, and the licence key we sent you.

1. Install and start the **DTPWeb print assistant**. RxLabel prints through it, so it must be running whenever you print.
2. Connect the label printer by USB and switch it on.
3. Run the RxLabel installer and open RxLabel.
4. First-time setup takes three steps:
    1. **License and manager account**: paste your licence key and press Verify. Check the facility name and "valid until" date, then create the manager account (name, email, position, password).
    2. **Facility**: check the name, address and contact printed on your labels.
    3. **Defaults**: choose the date format and whether a sound plays when you print. Read the licence agreement and privacy policy, tick "I agree", and press **Finish setup**.
5. Sign in with the manager account. A list of common medicines is already loaded on the Labels page.

**Accounts.** There are three roles. **Users** print and manage labels, clients and the queue. **Managers** can also add and edit user accounts, make and download backups, export data and see print history. The **admin** account, used by RxLabel support, can also restore backups, import data and change printer settings.

## Printing a label

**From the Labels page** (the fastest way):

1. Search for the medicine (\`Ctrl+K\`, type, \`Enter\`). Names starting with what you type come first, then names containing it. Words can be in any order and needn't be finished: \`para tab\` finds PARACETAMOL 500MG TABLETS. In Settings > Label search you can also allow typing mistakes (\`paracetmol\`), and turn on patterns for advanced searches (\`/^amox.*(250|500)/\`).
2. Check the product, instructions and warning, and edit them on the card if needed. Press **Save** (\`Ctrl+S\`) to keep the change for next time. An edited label shows **Edited**; **Reset** beside it puts back the saved text (Undo for a few seconds).
3. Type the client's name in the toolbar. Every card uses it.
4. Press **Print** (\`Ctrl+P\`), or **Queue** (\`Ctrl+Enter\`) to print it later with others.

**Instructions:** type them as usual, or press the pencil in the corner of the instructions box (\`Ctrl+Shift+B\`) to change them part by part. The parts you can change are underlined: the action, how many, the form, the amount, how often, when and for how long. Everything else stays exactly as written.

- **Change a part:** click it, or press \`Tab\` to go from part to part. Pick another with \`↑\` \`↓\` and \`Enter\`, or type your own: \`7\` in "for how long" gives "SEVEN(7) days", \`2.5\` in the amount gives "2.5ml". "tablet" becomes "tablets" when you choose TWO(2).
- **Only choices that fit** are listed (Instill: drop(s), into eye, ear or nose), but you can type anything.
- **+ When** and **+ For how long** add those parts; "No “when”" and "No end" take them out.
- **Use** replaces the instructions (Undo for a few seconds). A label without a dose starts from a usual one, and **Add to end** keeps what is there.
- **Phrases** tab: saved phrases (managers and admins keep the list) and the instructions your pharmacy uses most; **Edit** opens a dose to change it first.
- **Managers and admins** keep the choices: **Edit options** above a part's choices (**Reset to defaults** brings RxLabel's list back), and **Save "…" as an option** keeps something typed. Labels never change when an option is removed; that wording is just no longer underlined.

The pencil is also in the Add labels windows.

**For a regular client:** open **Clients**, pick the client and keep their own labels there. Select labels and use Print or Queue from the toolbar. To print or queue all of a client's labels, use the row menu on the Clients list.

**The queue:** open it from the Queue badge in the header. Check the labels, then press **Print all**. Labels stay in the queue after printing unless you turn on Settings > Labels & printing > "Remove from the queue after printing". The queue holds 100 labels by default; RxLabel asks before removing the oldest.

**Copies:** turn on Settings > Labels & printing > "Show copies on labels" to get a copies box (1 to 20) next to Print.

**Preview:** the eye button on a label (or \`Ctrl+Shift+P\`) shows it as it will print: "Actual size", or "Larger" to see every printer dot, with any warnings and the text that had to shrink. Print from there, or close it. Image-based printing prints exactly what you see; text-based printing is close. In Settings > Labels & printing you can hide the eye button, or turn on "Show a preview before printing" to see it every time you print (with several labels, step through them with ← and →, then Print all).

**"Print anyway?"** RxLabel asks before printing when:

- the same medicine was printed for the same client in the last 10 minutes, or is twice in the same print job;
- a label has no instructions;
- the text is too long to print at a readable size.

These are reminders only. Cancel is the default; **Print anyway** prints.

Always check each printed label before handing over the medicine.

## Printer status

The badge in the header of every page shows whether you can print. Hover over it to see which printer labels go to.

| Badge | What it means | What to do |
| --- | --- | --- |
| Printer ready | Labels print straight away | Nothing |
| Printing… | A batch is printing; Print buttons wait | Wait for it to finish |
| Printer starting… / restarting (n/3) | RxLabel is starting its print helper | Wait a few seconds |
| Printer not connected | The printer is unplugged or off. Labels still go to the last printer you used and wait in the Windows print queue; a yellow banner reminds you | Plug it in or switch it on; check those labels once they print |
| No printer connected | No printer has ever been connected, so printing is off | Connect the printer by USB and switch it on |
| Print assistant not running | The DTPWeb print assistant is closed | Start it; RxLabel notices by itself, or press **Check again** |
| Printer offline | The print helper stopped and could not restart | Press **Retry**; if it stays offline, contact support |

RxLabel notices a printer being plugged in or out within a couple of seconds. To hear it, turn on Settings > Notifications > **Printer status sound**.

## Settings and admin tasks

**Settings** (gear in the header menu), for everyone:

- **Appearance**: light, dark or system theme, and text size.
- **Labels & printing**: printer (Automatic picks the label printer), label template, text-based or image-based printing, date format, copies box, preview button, preview before printing, remove from queue after printing.
- **Notifications**: printing sound and printer status sound.
- **Privacy & security**: change your password; the admin also sets "Sign out after inactivity" (5 minutes to 24 hours, 8 hours by default).
- **Shortcuts** and **Help** (What's new, this guide, the licence agreement, the privacy policy and open-source licences).

**Admin** page (from the header menu). Managers see Database (backups and export) and Print history; the admin account sees everything:

| Section | What you do there |
| --- | --- |
| Dashboard | Counts of labels, clients, users and queue; Back up now |
| Users | Add, edit and remove accounts (managers can do this too, from Users) |
| Labels | Manage the saved label list |
| Print history | Every label printed in the last 30 days, who printed it and the result; search and Export CSV |
| Database | Backups (automatic schedule, how many to keep, backup passphrase, restore), import and export |
| Settings | Facility details, licence renewal, queue size and how long queue items are kept, label settings, printing calibration, Export diagnostics |

**Backups:** automatic backups run from the first day, with no setup: the first one a few minutes after RxLabel starts, then once a week (change this in Database > Backups). Until you set a backup passphrase they are encrypted with a key kept on this computer, so they can only be restored here. Set a backup passphrase in Database > Backups so a backup can be restored on a new computer. Write it down and keep it safe; it cannot be recovered.

**Printing calibration:** if labels print off-centre, use Admin > Settings > Printing to move the print by up to 3 mm or rotate it, then press **Print test label**.

**Licence:** a banner appears 30 days before the key expires. Renew from the banner or Admin > Settings. After expiry RxLabel is read-only: you can still view, export and back up, but not print.

## Keyboard shortcuts

Press \`?\` (or \`F1\` while typing) on any page to see that page's shortcuts.

| Keys | Labels page | Queue page |
| --- | --- | --- |
| \`Ctrl+K\` | Search | — |
| \`Enter\` (in search) | Go to the first match | — |
| \`Ctrl+↓\` / \`Ctrl+↑\` | Next / previous label | Next / previous label |
| \`Ctrl+Enter\` | Add the label to the queue | Print that label |
| \`Ctrl+P\` | Print the label | Print all |
| \`Ctrl+S\` | Save the label | — |
| \`Ctrl+Shift+P\` | Preview the label | Preview that label |
| \`Ctrl+Shift+B\` | Build the instructions | Build the instructions |
| \`Ctrl+Delete\` | — | Remove the label |
| \`Ctrl+I\` | — | Clear the queue |
| \`Esc\` | Back to search | — |

## Troubleshooting

| Problem | Try this |
| --- | --- |
| Print buttons are greyed out | Hover over them to see why, then check the printer status badge |
| "Printer not connected" but the printer is on | Check the USB cable at both ends, then press **Check again** |
| Label did not print | Check paper and that the cover is closed; the message says what the printer reported |
| Text is cut off or too small | Shorten the instructions, or ask the admin to adjust Admin > Settings > Labels |
| Print is off-centre | Admin > Settings > Printing, then Print test label |
| Signed out unexpectedly | You were inactive longer than the sign-out time |
| Anything else | Admin > Settings > Support > **Export diagnostics**, and send the file to rxlabelapp@gmail.com or WhatsApp +233 54 451 4322. It contains no labels, client details or passwords |
`;export{e as default};
