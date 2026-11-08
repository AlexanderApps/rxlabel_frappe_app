"""Admin > Data > Export: a branch's data in the standalone app's export
format, numbered as a new RxLabel database, and readable by Move data in."""

import csv
import io
import json
import time
import zipfile

import frappe

from rxlabel import api, movein
from rxlabel_core import data_transfer, move_in

from .test_f1 import ADMIN, F1, MANAGER, USER
from .utils import call, ok

ALL = ["labels", "clients", "client_labels", "queue"]


def options(**kw):
    return {"tables": ALL, "format": "csv", "include_headers": True, "include_timestamps": True,
            "separate_files": False, "use_date_filter": False, **kw}


def download(**kw):
    frappe.local.response = frappe._dict()
    api.export_data(options=options(**kw))
    r = frappe.local.response
    assert r.type == "download", r
    return r


def read_zip(r) -> dict:
    z = zipfile.ZipFile(io.BytesIO(r.filecontent))
    return {n.split("/", 1)[1]: z.read(n) for n in z.namelist()}


def csv_rows(data: bytes) -> list[dict]:
    return list(csv.DictReader(io.StringIO(data.decode())))


class TestExport(F1):
    def setUp(self):
        super().setUp()
        self.as_(MANAGER, self.osu)
        ama = self.add_client("Ama Mensah")
        kofi = self.add_client("Kofi Boateng", home_address="12 Ring Road, Accra")
        ok(api.add_client_label, client_id=kofi, product="KOFI DRUG", instructions="Take one daily")
        ok(api.add_client_label, client_id=ama, product="AMA DRUG", warning="May cause drowsiness")
        ok(api.add_to_queue, product="QUEUED FOR KOFI", client="Kofi Boateng")
        ok(api.add_to_queue, product="QUEUED, NO CLIENT")
        self.as_(MANAGER, self.tema)
        self.add_client("Tema Only Client")
        self.as_(MANAGER, self.osu)

    def test_the_branchs_data_numbered_as_a_new_database(self):
        files = read_zip(download())
        self.assertEqual(sorted(files), sorted(f"{t}.csv" for t in ALL))
        for table in ALL:  # the standalone app's columns, in its order
            header = files[f"{table}.csv"].decode().split("\r\n", 1)[0]
            self.assertEqual(header.split(","), list(data_transfer.EXPORT_COLUMNS[table]))

        clients = csv_rows(files["clients.csv"])
        self.assertEqual([(c["id"], c["name"]) for c in clients], [("1", "Ama Mensah"), ("2", "Kofi Boateng")])
        self.assertEqual(clients[1]["home_address"], "12 Ring Road, Accra")
        self.assertRegex(clients[0]["created_at"], r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d$")

        labels = {r["product"]: r for r in csv_rows(files["client_labels.csv"])}
        self.assertEqual((labels["KOFI DRUG"]["client_id"], labels["AMA DRUG"]["client_id"]), ("2", "1"))
        self.assertEqual(sorted(r["id"] for r in labels.values()), ["1", "2"])

        queue = {r["product"]: r for r in csv_rows(files["queue.csv"])}
        self.assertEqual((queue["QUEUED FOR KOFI"]["client"], queue["QUEUED FOR KOFI"]["client_id"]),
                         ("Kofi Boateng", "2"))
        self.assertEqual(queue["QUEUED, NO CLIENT"]["client_id"], "")

        library = csv_rows(files["labels.csv"])  # the company's library
        self.assertEqual(len(library), frappe.db.count("RxLabel Label"))
        self.assertEqual([r["id"] for r in library[:3]], ["1", "2", "3"])
        self.assertTrue(all(r["is_custom"] in ("0", "1") for r in library))

    def test_another_branchs_clients_stay_out(self):
        everything = b"".join(read_zip(download()).values()).decode()
        self.assertNotIn("Tema Only Client", everything)
        self.as_(MANAGER, self.tema)
        clients = csv_rows(download(tables=["clients"]).filecontent)
        self.assertEqual([(c["id"], c["name"]) for c in clients], [("1", "Tema Only Client")])

    def test_one_table_json_and_options(self):
        r = download(tables=["clients"], format="json", include_timestamps=False)
        self.assertEqual(r.content_type, "application/json")
        self.assertRegex(r.filename, r"^clients_\d{8}_\d{6}\.json$")
        rows = json.loads(r.filecontent)
        self.assertEqual(rows[0], {"id": 1, "name": "Ama Mensah", "contact": "024", "email": "",
                                   "home_address": None})
        r = download(tables=["queue"], include_headers=False)
        self.assertRegex(r.filename, r"^queue_\d{8}_\d{6}\.csv$")
        self.assertFalse(r.filecontent.startswith(b"id,"))
        r = download(tables=["clients"], separate_files=True)
        self.assertRegex(r.filename, r"^rxlabel_export_\d{8}_\d{6}\.zip$")

    def test_counts_preview_and_dates(self):
        counts = ok(api.get_export_counts)
        self.assertEqual({k: counts[k] for k in ("clients", "client_labels", "queue")},
                         {"clients": 2, "client_labels": 2, "queue": 2})
        self.assertEqual(counts["labels"], frappe.db.count("RxLabel Label"))
        preview = ok(api.get_export_preview, options={"table": "clients", "include_timestamps": False})
        self.assertEqual(preview["columns"], ["id", "name", "contact", "email", "home_address"])
        self.assertEqual([c["name"] for c in preview["data"]], ["Ama Mensah", "Kofi Boateng"])

        today = frappe.utils.now_datetime().strftime("%Y-%m-%d")
        self.assertEqual(ok(api.get_export_counts, date_from="2000-01-01", date_to="2000-12-31")["clients"], 0)
        self.assertEqual(csv_rows(download(tables=["clients"], use_date_filter=True, date_from="2000-01-01",
                                           date_to="2000-12-31").filecontent), [])
        self.assertGreaterEqual(ok(api.get_export_counts, date_from="2000-01-01", date_to="2100-01-01")["clients"], 2)
        self.assertEqual(call(api.get_export_counts, date_from=today, date_to="2000-01-01")[1]["code"], "VALIDATION")
        self.assertEqual(call(api.export_data, options=options(format="xlsx"))[1]["code"], "VALIDATION")
        self.assertEqual(call(api.export_data, options=options(tables=["users"]))[1]["code"], "VALIDATION")

    def test_who_can_export(self):
        self.as_(USER)
        self.assertEqual(call(api.export_data, options=options())[1]["code"], "FORBIDDEN")
        self.assertEqual(call(api.get_export_counts)[1]["code"], "FORBIDDEN")
        self.as_(ADMIN, self.osu)
        self.assertEqual(len(csv_rows(download(tables=["clients"]).filecontent)), 2)
        # Read-only (expired licence) still lets the pharmacy take its data.
        frappe.db.set_single_value("RxLabel Settings", "license_expires_at", int(time.time()) - 86400)
        frappe.db.commit()
        self.as_(MANAGER, self.osu)
        self.assertEqual(len(csv_rows(download(tables=["clients"]).filecontent)), 2)

    def test_move_data_in_reads_it(self):
        r = download(tables=["labels", "clients", "client_labels"])
        self.as_(ADMIN, self.tema)
        p = movein.plan(move_in.read_export([(r.filename, r.filecontent)]), self.tema)
        self.assertEqual((p["clients"]["add"], p["client_labels"]["add"], p["labels"]["add"], p["labels"]["update"]),
                         (2, 2, 0, 0))  # the library is the company's: already there
        movein.apply(p)
        frappe.db.commit()
        kofi = frappe.get_all("RxLabel Client", filters={"branch": self.tema, "client_name": "Kofi Boateng"},
                              pluck="name")
        self.assertEqual(frappe.get_all("RxLabel Client Label", filters={"client": kofi[0]}, pluck="product"),
                         ["KOFI DRUG"])
