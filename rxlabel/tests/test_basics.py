"""F0: install, roles, sign-in, branches and the error format."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.tests.test_api import FrappeAPITestCase

from rxlabel import api, install
from rxlabel.access import rxlabel_role

from .utils import PASSWORD, call, ensure_branch, ensure_user, ok


class TestBasics(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        install.ensure_roles()
        cls.osu = ensure_branch("Osu Pharmacy", address_line_1="12 Oxford St", city="Accra",
                                phone_no="030 200 0001")
        cls.tema = ensure_branch("Tema Pharmacy", address_line_1="Community 1", city="Tema",
                                 phone_no="030 300 0002")
        cls.user = ensure_user("rx-user@example.com", "RxLabel User", [cls.osu])
        cls.manager = ensure_user("rx-manager@example.com", "RxLabel Manager", [cls.osu, cls.tema], cls.tema)
        cls.admin = ensure_user("rx-admin@example.com", "RxLabel Admin")
        cls.nobody = ensure_user("rx-none@example.com", None, [cls.osu])
        cls.lost = ensure_user("rx-lost@example.com", "RxLabel User")
        # Kept: an error reply rolls back the request's transaction, as in production.
        frappe.db.commit()

    def tearDown(self):
        frappe.set_user("Administrator")

    def test_preloaded_labels_and_roles(self):
        for role in ("RxLabel Admin", "RxLabel Manager", "RxLabel User"):
            self.assertTrue(frappe.db.exists("Role", role))
        rows = install.preloaded_labels()
        self.assertGreater(len(rows), 500)
        self.assertEqual(frappe.db.count("RxLabel Label", {"is_custom": 0}), len(rows))
        self.assertEqual(install.load_preloaded_labels(), 0)  # never twice
        keys = [r[3] for r in rows]
        self.assertEqual(len(keys), len(set(keys)))

    def test_roles_map(self):
        self.assertEqual(rxlabel_role(self.user), "user")
        self.assertEqual(rxlabel_role(self.manager), "manager")
        self.assertEqual(rxlabel_role(self.admin), "admin")
        self.assertEqual(rxlabel_role("Administrator"), "admin")
        self.assertIsNone(rxlabel_role(self.nobody))
        self.assertIsNone(rxlabel_role("Guest"))

    def test_get_me_and_branch(self):
        frappe.set_user(self.user)
        me = ok(api.get_me)
        self.assertEqual((me["id"], me["role"]), (self.user, "user"))
        self.assertEqual(me["branch"]["name"], self.osu)
        self.assertEqual(me["branch"]["facility_name"], "Osu Pharmacy")
        self.assertEqual(me["branch"]["facility_address"], "12 Oxford St, Accra")
        self.assertEqual(me["branch"]["facility_contact"], "030 200 0001")

    def test_default_branch_and_switching(self):
        frappe.set_user(self.manager)
        branches = ok(api.get_branches)
        self.assertEqual(branches["current"], self.tema)  # the default User Permission
        self.assertEqual({c["name"] for c in branches["choices"]}, {self.osu, self.tema})
        ok(api.set_branch, branch=self.osu)
        self.assertEqual(ok(api.get_branches)["current"], self.osu)
        status, reply = call(api.set_branch, branch="Stores - RXT")
        self.assertEqual((status, reply["code"]), (403, "FORBIDDEN"))

    def test_admin_without_permissions_sees_every_branch(self):
        frappe.set_user(self.admin)
        names = {c["name"] for c in ok(api.get_branches)["choices"]}
        self.assertTrue({self.osu, self.tema} <= names)

    def test_branch_settings_override_the_warehouse(self):
        frappe.get_doc({"doctype": "RxLabel Branch Settings", "branch": self.osu,
                        "facility_name": "Osu Main Pharmacy"}).insert(ignore_permissions=True)
        try:
            frappe.set_user(self.user)
            branch = ok(api.get_me)["branch"]
            self.assertEqual(branch["facility_name"], "Osu Main Pharmacy")
            self.assertEqual(branch["facility_address"], "12 Oxford St, Accra")  # still the Warehouse's
        finally:
            frappe.set_user("Administrator")
            frappe.delete_doc("RxLabel Branch Settings", self.osu, force=True)

    def test_errors_in_rxlabel_format(self):
        frappe.set_user("Guest")
        self.assertEqual(call(api.get_me), (401, {"code": "UNAUTHORIZED", "message": "Please sign in."}))
        frappe.set_user(self.nobody)
        status, reply = call(api.get_me)
        self.assertEqual((status, reply["code"]), (403, "FORBIDDEN"))
        frappe.set_user(self.lost)
        self.assertIsNone(ok(api.get_me)["branch"])
        status, reply = call(api.get_branches)
        self.assertEqual(reply["code"], "FORBIDDEN")
        self.assertIn("Warehouse", reply["message"])


class TestOverHttp(FrappeAPITestCase):
    """Sign-in and errors as the browser sees them."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        install.ensure_roles()
        cls.osu = ensure_branch("Osu Pharmacy")
        cls.user = ensure_user("rx-user@example.com", "RxLabel User", [cls.osu])
        cls.nobody = ensure_user("rx-none@example.com", None, [cls.osu])
        frappe.db.commit()

    def post_cmd(self, command, data, **kwargs):
        return self.post(self.method(f"rxlabel.api.{command}"), data, **kwargs)

    def test_login_and_errors(self):
        r = self.post_cmd("get_me", {})
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.json, {"exc_type": "RxLabelError", "code": "UNAUTHORIZED", "message": "Please sign in."})
        r = self.post_cmd("login", {"username": self.user, "password": "wrong-password"})
        self.assertEqual((r.status_code, r.json["code"]), (401, "INVALID_CREDENTIALS"))
        r = self.post_cmd("login", {"username": self.nobody, "password": PASSWORD})
        self.assertEqual((r.status_code, r.json["code"]), (403, "FORBIDDEN"))
        r = self.post_cmd("login", {"username": self.user, "password": PASSWORD})
        self.assertEqual(r.status_code, 200, r.json)
        self.assertTrue(r.json["csrf_token"])
        import re
        sid = re.search(r"sid=([^;]+)", ";".join(r.headers.getlist("Set-Cookie"))).group(1)
        me = self.post_cmd("get_me", {"sid": sid})
        self.assertEqual(me.status_code, 200, me.json)
        self.assertEqual(me.json["message"]["id"], self.user)
        self.assertEqual(me.json["message"]["branch"]["name"], self.osu)
        out = self.post_cmd("logout", {"sid": sid})
        self.assertEqual(out.status_code, 200)
        self.assertEqual(self.post_cmd("get_me", {"sid": sid}).status_code, 401)


class TestEveryCommand(IntegrationTestCase):
    def test_guests_are_turned_away(self):
        """Every command but the sign-in ones answers guests with UNAUTHORIZED."""
        import inspect

        public = {"login", "logout", "check_setup_status", "get_theme", "set_theme"}
        frappe.set_user("Guest")
        try:
            commands = {n: f for n, f in inspect.getmembers(api) if getattr(f, "rxlabel_allow_guest", None) is not None}
            self.assertTrue(commands)
            for name, fn in commands.items():
                self.assertEqual(fn.rxlabel_allow_guest, name in public, name)
                if name not in public:
                    params = inspect.signature(fn).parameters
                    status, reply = call(fn, **{p: None for p in params})
                    self.assertEqual((status, reply["code"]), (401, "UNAUTHORIZED"), name)
        finally:
            frappe.set_user("Administrator")


class TestLicence(IntegrationTestCase):
    def setUp(self):
        from rxlabel import licensing
        from rxlabel_core import license
        from .licensing_keys import TEST_PUBLIC_KEY
        self._orig = licensing.public_key
        licensing.public_key = lambda: TEST_PUBLIC_KEY
        self.addCleanup(setattr, licensing, "public_key", self._orig)
        install.ensure_roles()
        self.admin = ensure_user("rx-admin@example.com", "RxLabel Admin")
        self.user = ensure_user("rx-user@example.com", "RxLabel User", [ensure_branch("Osu Pharmacy")])

    def tearDown(self):
        frappe.set_user("Administrator")

    def test_licence(self):
        from .licensing_keys import make_license
        frappe.db.set_single_value("RxLabel Settings", {"license_key": None, "license_expires_at": None})
        frappe.set_user("Guest")
        self.assertTrue(ok(api.check_setup_status)["is_license_expired"])
        frappe.set_user(self.user)
        self.assertEqual(call(api.update_app_license, data={"license": make_license(days=30)})[1]["code"],
                         "FORBIDDEN")
        frappe.set_user(self.admin)
        self.assertEqual(call(api.update_app_license, data={"license": "NOPE"})[1]["code"], "LICENSE_INVALID")
        self.assertEqual(call(api.update_app_license, data={"license": make_license(days=-1)})[1]["code"],
                         "LICENSE_EXPIRED")
        ok(api.update_app_license, data={"license": make_license(days=30)})
        status = ok(api.check_setup_status)
        self.assertFalse(status["is_license_expired"])
        self.assertTrue(status["is_setup_complete"])
