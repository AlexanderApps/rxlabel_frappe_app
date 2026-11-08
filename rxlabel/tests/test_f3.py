"""F3: users (read-only: ERPNext manages them), the overview, passwords and
the support file."""

import io
import json
import zipfile

import frappe
from frappe.utils.password import check_password, update_password

from rxlabel import api

from .test_f1 import ADMIN, F1, MANAGER, USER
from .utils import PASSWORD, call, ok


class TestUsers(F1):
    def test_who_sees_whom(self):
        self.as_(ADMIN, self.osu)
        users = {u["id"]: u for u in ok(api.get_users)}
        self.assertTrue({ADMIN, MANAGER, USER, "rx-lost@example.com"} <= set(users))
        self.assertNotIn("rx-none@example.com", users)  # no RxLabel role
        self.assertEqual((users[ADMIN]["role"], users[ADMIN]["all_branches"], users[ADMIN]["branches"]),
                         ("admin", True, []))
        self.assertEqual((users[MANAGER]["role"], sorted(users[MANAGER]["branches"])),
                         ("manager", sorted([self.osu, self.tema])))
        self.assertEqual(users[MANAGER]["branches"][0], self.tema)  # the default first
        self.assertEqual((users["rx-lost@example.com"]["branches"], users["rx-lost@example.com"]["all_branches"]),
                         ([], False))
        self.assertIsNone(users[USER]["secret"])
        self.assertRegex(users[USER]["created_at"], r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d$")
        self.as_(MANAGER)
        self.assertNotIn(ADMIN, [u["id"] for u in ok(api.get_users)])  # only an admin sees admins
        self.as_(USER)
        self.assertEqual(call(api.get_users)[1]["code"], "FORBIDDEN")


class TestOverview(F1):
    def test_general_stats(self):
        self.as_(USER)
        self.add_client()
        self.assertEqual(call(api.get_general_stats)[1]["code"], "FORBIDDEN")
        self.as_(MANAGER, self.osu)
        s = ok(api.get_general_stats)
        self.assertEqual((s["host"], s["branch"], s["num_clients"]), ("frappe", self.osu, 1))
        self.assertGreater(s["num_labels"], 1000)
        self.assertGreaterEqual(s["num_users"], 4)
        self.assertTrue(s["app_version"] and s["frappe_version"] and s["erpnext_version"])
        self.as_(MANAGER, self.tema)
        self.assertEqual(ok(api.get_general_stats)["num_clients"], 0)  # this branch's


class TestPassword(F1):
    def tearDown(self):
        frappe.set_user("Administrator")
        update_password(USER, PASSWORD)
        frappe.db.commit()
        super().tearDown()

    def test_change_password(self):
        self.as_(USER)
        reply = call(api.change_password, current_password="wrong", new_password="Another-pass-1")[1]
        self.assertEqual(reply["code"], "INVALID_CREDENTIALS")
        self.assertEqual(call(api.change_password, current_password=PASSWORD, new_password="short")[1]["code"],
                         "VALIDATION")
        ok(api.change_password, current_password=PASSWORD, new_password="Another-pass-1")
        check_password(USER, "Another-pass-1")
        with self.assertRaises(frappe.AuthenticationError):
            check_password(USER, PASSWORD)


class TestDiagnostics(F1):
    def test_support_file_has_no_patient_data(self):
        self.as_(USER)
        self.assertEqual(call(api.export_diagnostics)[1]["code"], "FORBIDDEN")
        self.add_client("Secret Patient Name")
        ok(api.add_to_queue, product="SECRET PRODUCT", client="Secret Patient Name")
        self.as_(ADMIN, self.osu)
        frappe.local.response = frappe._dict()
        api.export_diagnostics(printer_status={"connected": False}, printer_report="DT-108B: not found")
        r = frappe.local.response
        self.assertEqual((r.type, r.content_type), ("download", "application/zip"))
        self.assertTrue(r.filename.startswith("RxLabel-diagnostics-") and r.filename.endswith(".zip"))
        z = zipfile.ZipFile(io.BytesIO(r.filecontent))
        self.assertEqual(sorted(z.namelist()), ["README.txt", "printing.txt", "summary.json"])
        everything = b"".join(z.read(n) for n in z.namelist()).decode()
        self.assertNotIn("Secret", everything)
        self.assertNotIn("SECRET", everything)
        summary = json.loads(z.read("summary.json"))
        self.assertEqual((summary["branch"], summary["counts"]["clients"] if "clients" in summary["counts"]
                          else summary["counts"]["num_clients"], summary["counts"]["queue"]), (self.osu, 1, 1))
        self.assertEqual(summary["printer"], {"status": {"connected": False}})
