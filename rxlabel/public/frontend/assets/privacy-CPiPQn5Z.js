const e=`# RxLabel Privacy Policy

Version 1.0, 31 October 2026

## Summary

RxLabel keeps everything you enter on your own computers, in an encrypted database. We, **RxLabel**, Madina, Accra, Ghana, do not receive or host your labels, clients or users. RxLabel contacts us only to check for updates. We see your data only when you send it to us for support, or when RxLabel support works on an installation to recover data or fix a problem.

- **Your facility decides** what is recorded about clients and staff, and is responsible for it.
- **We are responsible** for how the software handles that data, and for the little information that reaches us (update checks and support contact).

## What RxLabel stores on your computer

All of this stays on the computer where RxLabel is installed. Nothing in this table is sent to us.

| Data | What it contains | How long it is kept |
| --- | --- | --- |
| Facility details | Name, address and contact (from the licence key and Settings), date format and sound settings | Until you change them |
| Licence key | Facility name, address, contact and expiry date | Until replaced |
| User accounts | Name, email, position, role (admin, manager or user) and the password, stored only as an Argon2id hash | Until the account is deleted |
| Clients | Name, phone, email and home address, as entered | Until the client is deleted |
| Labels and client labels | Product, instructions and warnings | Until deleted |
| Print queue | Product, instructions, warning and client name | Until printed or removed; items older than 30 days are deleted by default (admin can set 7 to 90 days, or never) |
| Print history | When, product, client, who printed it, copies and the result | 30 days at most, then deleted automatically |
| Backups | An encrypted copy of the whole database, made automatically (weekly by default) and on request | As many as an admin or manager chooses to keep, in the folder RxLabel uses for backups |
| App logs | Technical events and errors, about 10 MB at most | Oldest entries are overwritten. Logs do not record product names, client names, searches, names typed at sign-in, or the label text sent to the printer |
| Label images | Temporary images of labels for image-based printing | Deleted after printing |

Medicine names next to a client's name can reveal health information, which Ghana's Data Protection Act, 2012 (Act 843) treats as special personal data. Record only what you need on the label.

## What leaves your computer

| When | What is sent | To whom |
| --- | --- | --- |
| Update check | The installed version, operating system and processor type, plus your IP address as part of any internet request. No labels, clients or users | Our update server (rxlabel.pythonanywhere.com, hosted by PythonAnywhere) |
| Printing | The label being printed | The DTPWeb print assistant and your printer, both on your computer. Nothing goes over the internet |
| Diagnostics, only if you send it | Versions, licence status, database health, printer status, record counts, settings and recent logs. No labels, client details or passwords | Whoever you send the file to, usually our support |
| Contacting support | Whatever you write, from your own email, phone or WhatsApp | Us, and the email, phone or WhatsApp provider you use |
| Data export, only if you do it | The tables you choose, as CSV | The file and folder you choose |

We use update-server request logs only to deliver updates and keep the service running. Those logs are kept for no more than 31 days. We do not sell data, show ads or use analytics or tracking in RxLabel.

## How your data is protected

- **Encryption.** The database is encrypted with SQLCipher. Its key is kept in the Windows credential store, not in a file beside the database.
- **Backups.** Backups are encrypted too. Until a backup passphrase is set, they use a random key kept on this computer, so they can only be restored here. Once an admin or manager sets a passphrase, backups can be restored on another computer with it. We cannot recover a lost passphrase.
- **Sign-in.** Passwords are stored only as Argon2id hashes. Repeated wrong passwords are slowed down, and users are signed out after a period of inactivity (8 hours by default, set by the admin).
- **Roles.** Each action is checked against the user's role. Managers cannot create admin accounts or restore backups, and only admins change printer calibration or import data.
- **Expired licence.** RxLabel becomes read-only, so you can still export and back up your data.

**Support access.** RxLabel support has its own sign-in to each installation. We use it only to recover data or fix a problem.

You are responsible for protecting the computer itself: a Windows password, up-to-date security updates, and limiting who can sign in to it.

## Your facility's role and people's rights

Under Act 843, the facility using RxLabel is the **data controller** for client and staff data in it. That data does not normally reach us. When RxLabel support works on an installation to recover data or fix a problem, we act on your behalf and only for that purpose. Your facility should:

- tell clients what is recorded and why, where the law requires it;
- record only what is needed to label medicines safely;
- answer requests from clients and staff to see, correct or delete their data. In RxLabel any signed-in user can edit or delete clients and labels, admins and managers manage user accounts and can export data;
- register with the Data Protection Commission of Ghana if the law requires it.

For information that reaches us (support messages, update-check requests), you can ask us to see, correct or delete it by contacting us below. You can also complain to the Data Protection Commission.

## Changes and contact

This policy is in RxLabel under Settings > Help. We will update it when RxLabel changes what it stores or sends, and note the change in the app's "What's new" notes.

Contact: RxLabel, Madina, Accra, Ghana. rxlabelapp@gmail.com, +233 54 451 4322 (phone and WhatsApp).
`;export{e as default};
