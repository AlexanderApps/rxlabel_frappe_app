"""Moving a pharmacy's data in from RxLabel desktop or the standalone app,
over HTTP with the export's files, as the browser sends them."""

import io
import json
import re
import time
import zipfile
from unittest import mock

import frappe
from frappe.tests.test_api import FrappeAPITestCase, make_request

from rxlabel import api, movein
from rxlabel_core import data_transfer

from . import demo
from .utils import PASSWORD, ensure_branch

ADMIN, MANAGER = "rx-admin@example.com", "rx-manager@example.com"


def csv_of(table, rows):
    columns = [c for c in data_transfer.EXPORT_COLUMNS[table] if c in rows[0]]
    return data_transfer.to_csv(columns, rows, True).encode()


def export_zip(labels, clients, client_labels):
    stamp = "rxlabel_export_20261107_093000"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(f"{stamp}/labels.csv", csv_of("labels", labels))
        z.writestr(f"{stamp}/clients.csv", csv_of("clients", clients))
        z.writestr(f"{stamp}/client_labels.csv", csv_of("client_labels", client_labels))
    return buf.getvalue()


class TestMoveIn(FrappeAPITestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        demo.seed()
        cls.tema = ensure_branch("Tema Pharmacy")
        frappe.db.commit()

    def setUp(self):
        frappe.set_user("Administrator")
        clients = frappe.get_all("RxLabel Client", filters={"branch": self.tema}, pluck="name")
        if clients:
            frappe.db.delete("RxLabel Client Label", {"client": ["in", clients]})
            frappe.db.delete("RxLabel Queue Item", {"branch": self.tema})
            frappe.db.delete("RxLabel Client", {"branch": self.tema})
        frappe.db.delete("RxLabel Label", {"product": ["like", "MOVEIN %"]})
        self.library = frappe.get_all("RxLabel Label", filters={"is_custom": 0, "seed_key": ["is", "set"]},
                                      fields=["name", "product", "instructions", "warning", "seed_key"],
                                      order_by="name asc", limit=2)
        frappe.db.set_single_value("RxLabel Settings", "license_expires_at", int(time.time()) + 30 * 86400)
        frappe.db.commit()

    def tearDown(self):
        frappe.set_user("Administrator")
        frappe.db.set_single_value("RxLabel Settings", "license_expires_at", int(time.time()) + 30 * 86400)
        for label in getattr(self, "library", []):
            frappe.db.set_value("RxLabel Label", label.name, {"instructions": label.instructions, "is_custom": 0})
        frappe.db.commit()
        super().tearDown()

    def sid(self, user=ADMIN):
        r = self.post(self.method("rxlabel.api.login"), {"username": user, "password": PASSWORD})
        self.assertEqual(r.status_code, 200, r.json)
        return re.search(r"sid=([^;]+)", ";".join(r.headers.getlist("Set-Cookie"))).group(1)

    def move(self, sid, files, apply=False, branch=None):
        data = {"sid": sid, "branch": branch or self.tema, "apply": "1" if apply else "0",
                "files": [(io.BytesIO(content), name) for name, content in files]}
        return self.upload(data)

    def upload(self, form):
        # Multipart, as the browser sends files (post() sends JSON).
        return make_request(target=self.TEST_CLIENT.post, args=(self.method("rxlabel.api.move_in_data"),),
                            kwargs={"data": form})

    def export(self):
        edited, same = self.library
        labels = [
            {"id": 1, "product": "MOVEIN SYRUP", "instructions": "Take 5ml", "warning": None, "is_custom": True,
             "seed_key": None},
            {"id": 2, "product": same.product, "instructions": same.instructions, "warning": same.warning,
             "is_custom": False, "seed_key": same.seed_key},  # unchanged preloaded label: already there
            {"id": 3, "product": edited.product, "instructions": "Edited at the pharmacy", "warning": edited.warning,
             "is_custom": True, "seed_key": edited.seed_key},  # their edit of a preloaded label
            {"id": 4, "product": "", "instructions": "x", "warning": None, "is_custom": True, "seed_key": None},
        ]
        clients = [{"id": 7, "name": "Ama Mensah", "contact": "024", "email": "", "home_address": "Madina"},
                   {"id": 8, "name": "Kofi Boateng", "contact": "", "email": "k@x.com", "home_address": ""}]
        client_labels = [{"id": 1, "client_id": 7, "product": "ORS", "instructions": "Dissolve", "warning": ""},
                         {"id": 2, "client_id": 7, "product": "ORS", "instructions": "Dissolve", "warning": None},
                         {"id": 3, "client_id": 8, "product": "ZINC", "instructions": "One daily", "warning": ""},
                         {"id": 4, "client_id": 99, "product": "LOST", "instructions": "", "warning": ""}]
        return [("rxlabel_export_20261107_093000.zip", export_zip(labels, clients, client_labels))]

    def test_check_then_move_then_again(self):
        sid = self.sid()
        before = frappe.db.count("RxLabel Label")
        r = self.move(sid, self.export())
        self.assertEqual(r.status_code, 200, r.json)
        p = r.json["message"]
        self.assertEqual((p["labels"], p["clients"], p["client_labels"]), (
            {"add": 1, "update": 1, "skip": 1, "kept_both": 0}, {"add": 2, "existing": 0}, {"add": 2, "skip": 1}))
        self.assertEqual((p["changes"], p["applied"]), (6, False))
        self.assertEqual(len(p["notes"]), 2)  # a label without a product; a client label without its client
        self.assertNotIn("LOST", json.dumps(p))  # values are never repeated
        self.assertEqual(frappe.db.count("RxLabel Client", {"branch": self.tema}), 0)  # checking changes nothing

        r = self.move(sid, self.export(), apply=True)
        self.assertEqual(r.status_code, 200, r.json)
        self.assertTrue(r.json["message"]["applied"])
        frappe.db.commit()  # a new transaction: MariaDB shows a transaction what it saw when it began
        self.assertEqual(frappe.db.count("RxLabel Label"), before + 1)
        edited = frappe.db.get_value("RxLabel Label", self.library[0].name, ["instructions", "is_custom"], as_dict=True)
        self.assertEqual((edited.instructions, edited.is_custom), ("Edited at the pharmacy", 1))
        clients = {c.client_name: c.name for c in frappe.get_all("RxLabel Client", filters={"branch": self.tema},
                                                                  fields=["name", "client_name"])}
        self.assertEqual(set(clients), {"Ama Mensah", "Kofi Boateng"})
        ama = frappe.get_all("RxLabel Client Label", filters={"client": clients["Ama Mensah"]}, pluck="product")
        kofi = frappe.get_all("RxLabel Client Label", filters={"client": clients["Kofi Boateng"]}, pluck="product")
        self.assertEqual((ama, kofi), (["ORS"], ["ZINC"]))  # linked to the new clients

        again = self.move(sid, self.export(), apply=True).json["message"]  # the same export again: nothing new
        self.assertEqual((again["changes"], again["clients"], again["existing_clients"]),
                         (0, {"add": 0, "existing": 2}, ["Ama Mensah", "Kofi Boateng"]))

    def test_edits_already_made_here_are_kept(self):
        frappe.db.set_value("RxLabel Label", self.library[0].name, {"instructions": "Edited in ERPNext",
                                                                     "is_custom": 1})
        frappe.db.commit()
        p = self.move(self.sid(), self.export()).json["message"]
        frappe.db.commit()
        self.assertEqual(p["labels"], {"add": 2, "update": 0, "skip": 1, "kept_both": 1})

    def test_who_and_when(self):
        r = self.move(self.sid(MANAGER), self.export())
        self.assertEqual((r.status_code, r.json["code"]), (403, "FORBIDDEN"))
        sid = self.sid()
        self.assertEqual(self.move(sid, self.export(), branch="Nowhere - RXT").json["code"], "FORBIDDEN")
        frappe.db.set_single_value("RxLabel Settings", "license_expires_at", int(time.time()) - 60)
        frappe.db.commit()
        self.assertEqual(self.move(sid, self.export()).status_code, 200)  # checking is fine when read-only
        self.assertEqual(self.move(sid, self.export(), apply=True).json["code"], "LICENSE_EXPIRED")

    def test_files_that_cant_be_used(self):
        sid = self.sid()
        r = self.move(sid, [("labels.csv", b"1,PARA,Take,\r\n")])
        self.assertEqual((r.status_code, r.json["code"]), (417, "VALIDATION"))
        self.assertIn("column headers", r.json["message"])
        r = self.upload({"sid": sid, "branch": self.tema})
        self.assertEqual(r.json["message"], "Choose the export's zip, or its files.")


class TestAllOrNothing(TestMoveIn):
    test_check_then_move_then_again = test_edits_already_made_here_are_kept = None
    test_who_and_when = test_files_that_cant_be_used = None

    def test_a_failure_part_way_leaves_nothing(self):
        from rxlabel_core import move_in
        data = move_in.read_export(self.export())
        frappe.set_user(ADMIN)
        plan = movein.plan(data, self.tema)
        real, calls = movein._insert, []

        def failing(doctype, rows):
            calls.append(doctype)
            if doctype == "RxLabel Client Label":  # the last step, after labels and clients went in
                raise RuntimeError("disk full")
            return real(doctype, rows)

        with mock.patch.object(movein, "_insert", failing), self.assertRaises(RuntimeError):
            movein.apply(plan)
        self.assertEqual(calls, ["RxLabel Label", "RxLabel Client", "RxLabel Client Label"])
        frappe.db.rollback()  # what Frappe does when a request fails
        self.assertEqual(frappe.db.count("RxLabel Client", {"branch": self.tema}), 0)
        self.assertEqual(frappe.db.count("RxLabel Label", {"product": "MOVEIN SYRUP"}), 0)

