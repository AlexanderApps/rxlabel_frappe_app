"""Moving a pharmacy's data in from RxLabel desktop or the standalone app:
the plan (what would be added, updated or skipped) and doing it.

- Labels go to the company's shared library. Labels already there with the
  same text are skipped. A preloaded label the pharmacy edited (same
  seed_key, other text) updates the library's, unless the library's was
  already edited here: then both are kept (added as a new label).
- Clients go to the chosen branch. A client whose name is already there is
  matched to that client, not added again.
- Client labels go to their client (old ids are mapped to the new ones);
  one already saved for that client with the same text is skipped, so
  moving the same export twice adds nothing the second time.
- Rows RxLabel can't store (no product or name, a name over 140
  characters) are skipped and counted; their values are never repeated.
"""

from __future__ import annotations

import frappe

from .checks import LONG, SHORT

LABEL, CLIENT, CLIENT_LABEL = "RxLabel Label", "RxLabel Client", "RxLabel Client Label"


def _same(*parts) -> tuple:
    """Text compared as RxLabel shows it: nothing and empty are the same."""
    return tuple(p or "" for p in parts)


def _short_ok(*values) -> bool:
    return all(v is None or len(v) <= SHORT for v in values)


def _long_ok(*values) -> bool:
    return all(v is None or len(v.encode("utf-8")) <= LONG for v in values)


def plan(data: dict, branch: str) -> dict:
    notes: list[str] = []

    # --- labels ------------------------------------------------------------------------
    library = frappe.get_all(LABEL, fields=["name", "product", "instructions", "warning", "is_custom", "seed_key"])
    by_seed = {r.seed_key: r for r in library if r.seed_key}
    texts = {_same(r.product, r.instructions, r.warning) for r in library}
    add_labels, update_labels, kept_both, skipped_labels, bad_labels = [], [], 0, 0, 0
    for row in data["labels"]:
        if not row["product"] or not _short_ok(row["product"]) or not _long_ok(row["instructions"], row["warning"]):
            bad_labels += 1
            continue
        text = _same(row["product"], row["instructions"], row["warning"])
        ours = by_seed.get(row["seed_key"]) if row["seed_key"] else None
        if text in texts:
            skipped_labels += 1
        elif ours is not None and not ours.is_custom:
            update_labels.append({"name": ours.name, **{k: row[k] for k in ("product", "instructions", "warning")}})
            ours.is_custom = 1  # a second edit of it in the same file is kept as its own label
            texts.add(text)
        else:
            if ours is not None:
                kept_both += 1
            add_labels.append({k: row[k] for k in ("product", "instructions", "warning")})
            texts.add(text)
    if bad_labels:
        notes.append(f"{bad_labels} label(s) skipped: no product name, or text too long for RxLabel.")

    # --- clients -----------------------------------------------------------------------
    here = {(c.client_name or "").lower(): c.name
            for c in frappe.get_all(CLIENT, filters={"branch": branch}, fields=["name", "client_name"])}
    add_clients, matched, target, bad_clients = [], [], {}, 0
    new_by_name: dict[str, int] = {}
    for row in data["clients"]:
        name = row["name"]
        if row["id"] is None or not name or not name.strip() or not _short_ok(name, row["contact"], row["email"]) \
                or not _long_ok(row["home_address"]):
            bad_clients += 1
            continue
        key = name.lower()
        if key in here:
            target[row["id"]] = ("existing", here[key])
            matched.append(name)
        elif key in new_by_name:  # the same name twice in the export: one client
            target[row["id"]] = ("new", new_by_name[key])
        else:
            new_by_name[key] = len(add_clients)
            target[row["id"]] = ("new", len(add_clients))
            add_clients.append({k: row[k] for k in ("name", "contact", "email", "home_address")})
    if bad_clients:
        notes.append(f"{bad_clients} client(s) skipped: no name, or details too long for RxLabel.")

    # --- client labels -------------------------------------------------------------------
    saved: dict[str, set] = {}
    add_client_labels, skipped_cl, orphans, bad_cl = [], 0, 0, 0
    for row in data["client_labels"]:
        dest = target.get(row["client_id"])
        if dest is None:
            orphans += 1
            continue
        if not row["product"] or not _short_ok(row["product"]) or not _long_ok(row["instructions"], row["warning"]):
            bad_cl += 1
            continue
        key = f"{dest[0]}:{dest[1]}"
        if key not in saved:
            saved[key] = ({_same(r.product, r.instructions, r.warning) for r in frappe.get_all(
                CLIENT_LABEL, filters={"client": dest[1]}, fields=["product", "instructions", "warning"])}
                if dest[0] == "existing" else set())
        text = _same(row["product"], row["instructions"], row["warning"])
        if text in saved[key]:
            skipped_cl += 1
            continue
        saved[key].add(text)
        add_client_labels.append({"to": dest, **{k: row[k] for k in ("product", "instructions", "warning")}})
    if orphans:
        notes.append(f"{orphans} client label(s) skipped: their client isn't in the export.")
    if bad_cl:
        notes.append(f"{bad_cl} client label(s) skipped: no product name, or text too long for RxLabel.")

    return {
        "branch": branch,
        "labels": {"add": len(add_labels), "update": len(update_labels), "skip": skipped_labels,
                   "kept_both": kept_both},
        "clients": {"add": len(add_clients), "existing": len(matched)},
        "client_labels": {"add": len(add_client_labels), "skip": skipped_cl},
        "existing_clients": sorted(set(matched))[:50],
        "notes": notes,
        "changes": len(add_labels) + len(update_labels) + len(add_clients) + len(add_client_labels),
        "_work": {"add_labels": add_labels, "update_labels": update_labels, "add_clients": add_clients,
                  "add_client_labels": add_client_labels},
    }


def _insert(doctype: str, rows: list[dict]) -> list[int]:
    """Many records at once (checked by plan(), so Frappe's per-record
    checks aren't needed); their new ids, in order."""
    if not rows:
        return []
    stamp, user = frappe.utils.now(), frappe.session.user
    names = [frappe.db.get_next_sequence_val(doctype) for _ in rows]
    fields = ["name", "creation", "modified", "owner", "modified_by", *rows[0]]
    frappe.db.bulk_insert(doctype, fields, [(n, stamp, stamp, user, user, *r.values()) for n, r in zip(names, rows)])
    return names


def apply(p: dict) -> None:
    """Do the plan (in the request's transaction: all of it or none)."""
    w, branch = p["_work"], p["branch"]
    _insert(LABEL, [{"product": r["product"], "instructions": r["instructions"], "warning": r["warning"],
                     "is_custom": 1} for r in w["add_labels"]])
    for row in w["update_labels"]:
        frappe.db.set_value(LABEL, row["name"], {"product": row["product"], "instructions": row["instructions"],
                                                 "warning": row["warning"], "is_custom": 1})
    new_ids = _insert(CLIENT, [{"branch": branch, "client_name": r["name"], "contact": r["contact"],
                                "email": r["email"], "home_address": r["home_address"]} for r in w["add_clients"]])
    _insert(CLIENT_LABEL, [{"client": new_ids[r["to"][1]] if r["to"][0] == "new" else r["to"][1],
                            "product": r["product"], "instructions": r["instructions"], "warning": r["warning"]}
                           for r in w["add_client_labels"]])
