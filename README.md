# RxLabel for Frappe / ERPNext (v16)

RxLabel medication labels inside ERPNext. The same app as RxLabel-Web (the
Vue frontend and `rxlabel_core`, RxLabel's shared rules), with Frappe's
users, roles and database.

- **Branches** are ERPNext Warehouses. Labels print the branch's name,
  address and phone (from the Warehouse, or overridden in RxLabel Branch
  Settings). A user's branches come from their User Permissions on
  Warehouse; the default one is used unless they pick another in RxLabel.
- **Per branch:** clients and their labels, the print queue, print history,
  label settings. **Shared** across the company: the label library and phrases.
- **Roles:** RxLabel Admin (or System Manager), RxLabel Manager, RxLabel User.
- **Licence:** one RxLabel key for the company (RxLabel Settings).
- Printing goes from the browser on the pharmacy PC to the DTPWeb print
  assistant on that PC; the server only builds the jobs.

## Install on a bench

On a dev bench on the same PC (for example WSL), one command bundles the app
and installs it, or updates it if it's already there. Run it with `bench start`
running in another terminal:

```
bash frappe/install-on-bench.sh --bench ~/frappe-bench --site dev.localhost [--demo] [--test]
```

`--demo` adds demo branches and accounts to the site's company; `--test` runs
the app's tests on the site. Then restart `bench start`.

By hand, from RxLabel-Web, make the bench-ready app (rxlabel_core included):

```
python frappe/bundle.py          # frappe/dist/rxlabel (git repository) + frappe/dist/rxlabel-<version>.zip
```

On the bench:

```
bench get-app /path/to/dist/rxlabel                 # or a git URL you pushed it to
bench --site <site> install-app rxlabel
bench --site <site> execute rxlabel.tests.demo.seed # optional: demo branches and accounts
```

Updates: run `install-on-bench.sh` again. By hand: `bundle.py`, move
`apps/rxlabel` aside (bench 5.31's `get-app --overwrite` is broken for local
folders), `bench get-app` again and `bench --site <site> migrate`. Or push the
bundle to a git remote and use `bench update --pull`.

The app is at `https://<site>/rxlabel`. Give users an RxLabel role and a
User Permission on their branch's Warehouse.

## In production

- HTTPS as for any ERPNext site (`bench setup lets-encrypt`, or your own
  certificate). Checked behind bench's nginx with HTTPS: no change needed.
- The browser prints through the print assistant (DTPWeb) on each pharmacy
  PC, at `http://127.0.0.1:15216`. Chrome may ask once per site to let it
  "access other apps and services on this device": allow it. Open
  `https://<site>/rxlabel#/printing-check` on a pharmacy PC to see what the
  browser allows.
- bench's nginx caches `/assets` for a year. The frontend's code files have new
  names on every build; after an update, users get the new version on their
  next page load.
- The app's files must be readable by nginx (a git checkout or the bundle's
  zip is; a copy with private permissions is not: `chmod -R o+rX apps/rxlabel`).

## Without a bench

`frappe/sim` runs this app on a stand-in for Frappe (see its README):
`frappe\sim\run.ps1`, then http://localhost:8001/rxlabel.

## Frontend

Built from `RxLabel-Web/frontend` into `rxlabel/public/frontend` and
`rxlabel/www/rxlabel.html`:

```
cd RxLabel-Web/frontend
npm run build:frappe
```
