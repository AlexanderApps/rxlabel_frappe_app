"""F1: labels, phrases, queue, clients and settings, as the standalone app
does them (web/tests), per branch where they belong to a branch."""

import time

import frappe
from frappe.tests import IntegrationTestCase

from rxlabel import api, install

from . import demo
from .utils import KeepsSettings, call, ensure_branch, ensure_user, ok

ADMIN, MANAGER, USER = "rx-admin@example.com", "rx-manager@example.com", "rx-user@example.com"


class F1(KeepsSettings, IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        demo.seed()
        cls.osu = ensure_branch("Osu Pharmacy")
        cls.tema = ensure_branch("Tema Pharmacy")
        frappe.db.commit()

    def setUp(self):
        frappe.set_user("Administrator")
        for doctype in ("RxLabel Queue Item", "RxLabel Client"):
            frappe.db.delete(doctype, {"branch": ["in", [self.osu, self.tema]]})
        frappe.db.delete("RxLabel Client Label", {"client": ["not in", frappe.get_all("RxLabel Client",
                                                                                      pluck="name") or [0]]})
        frappe.db.delete("RxLabel Branch Settings", {"branch": ["in", [self.osu, self.tema]]})
        frappe.db.delete("RxLabel User Settings", {"user": ["in", [ADMIN, MANAGER, USER]]})
        frappe.db.set_single_value("RxLabel Settings", {"license_expires_at": int(time.time()) + 30 * 86400,
                                                        "shared_json": None})
        frappe.db.commit()

    def tearDown(self):
        frappe.set_user("Administrator")

    def as_(self, user, branch=None):
        frappe.set_user(user)
        if branch:
            ok(api.set_branch, branch=branch)

    def add_client(self, name="Ama Mensah", **kw):
        return ok(api.add_client, name=name, contact=kw.get("contact", "024"), email=kw.get("email", ""),
                  home_address=kw.get("home_address"))


class TestLabels(F1):
    def test_seeded_and_searchable(self):
        self.as_(USER)
        found = ok(api.get_labels, search_term=None)
        self.assertEqual(len(found), 60)
        self.assertTrue(all(label["is_custom"] is False for label in found))
        self.assertIn("PARACETAMOL 500MG TABLETS", [l["product"] for l in ok(api.get_labels, search_term="para tab")])
        self.assertTrue(ok(api.get_labels, search_term="paracetamol")[0]["product"].startswith("PARACETAMOL"))

    def test_patterns_only_when_on_for_the_branch(self):
        self.as_(USER)
        self.assertTrue(ok(api.get_labels, search_term="/amox(/")[0]["product"].startswith("AMOX"))
        ok(api.set_aux_setting, key="label_search_patterns", value=True)
        self.assertEqual(call(api.get_labels, search_term="/amox(/")[1]["code"], "INVALID_PATTERN")
        self.as_(MANAGER, self.tema)  # another branch: still off
        self.assertEqual(call(api.get_labels, search_term="/amox(/")[0], 200)

    def test_update_marks_custom_and_the_library_is_shared(self):
        self.as_(USER)
        label = ok(api.get_labels, search_term="paracetamol 500mg tablets")[0]
        ok(api.update_label, id=label["id"], product=label["product"], instructions=label["instructions"],
           warning=label["warning"])
        self.assertIs(ok(api.get_labels, search_term=label["product"])[0]["is_custom"], False)
        try:
            ok(api.update_label, id=label["id"], product=label["product"], instructions="Changed",
               warning=label["warning"])
            self.as_(MANAGER, self.tema)
            changed = ok(api.get_labels, search_term=label["product"])[0]
            self.assertEqual((changed["is_custom"], changed["instructions"]), (True, "Changed"))
        finally:
            frappe.set_user("Administrator")
            frappe.db.set_value("RxLabel Label", label["id"], {"instructions": label["instructions"], "is_custom": 0})
            frappe.db.commit()

    def test_create_delete_and_safe_errors(self):
        self.as_(USER)
        new = ok(api.create_label, product="ZZ TEST SYRUP", instructions="Take 5ml", warning="")
        self.assertTrue(any(l["id"] == new and l["is_custom"] for l in ok(api.get_all_labels)))
        ok(api.delete_label, id=new)
        self.assertFalse(frappe.db.exists("RxLabel Label", new))
        status, reply = call(api.create_label, product="SECRET " * 30, instructions="", warning="")
        self.assertEqual((status, reply["code"]), (417, "VALIDATION"))
        self.assertNotIn("SECRET", reply["message"])
        self.assertEqual(call(api.create_label, product=" ", instructions="", warning="")[1]["message"],
                         "Product is required.")
        self.assertEqual(call(api.update_label, id=99999999, product="X", instructions="", warning="")[1]["code"],
                         "NOT_FOUND")


class TestQueue(F1):
    def test_full_then_make_room(self):
        self.as_(ADMIN, self.osu)
        ok(api.save_settings, data={"queue_size": 2})
        for p in ("A", "B"):
            ok(api.add_to_queue, product=p)
        status, reply = call(api.add_to_queue, product="C")
        self.assertEqual(reply["code"], "QUEUE_FULL")
        self.assertIn("1 oldest", reply["message"])
        ok(api.add_to_queue, product="C", make_room=True)
        self.assertEqual([q["product"] for q in ok(api.get_queue)], ["B", "C"])
        self.assertEqual(ok(api.count_queue), 2)
        self.assertEqual(call(api.check_queue_room, adding=1)[1]["code"], "QUEUE_FULL")

    def test_each_branch_has_its_own(self):
        self.as_(USER)  # Osu
        ok(api.add_to_queue, product="OSU ONLY")
        osu_item = ok(api.get_queue)[0]
        self.as_(MANAGER, self.tema)
        self.assertEqual(ok(api.get_queue), [])
        ok(api.remove_from_queue, id=osu_item["id"])  # not Tema's: nothing happens
        ok(api.clear_queue)
        self.as_(MANAGER, self.osu)
        self.assertEqual([q["product"] for q in ok(api.get_queue)], ["OSU ONLY"])
        ok(api.remove_from_queue, id=osu_item["id"])
        self.assertEqual(ok(api.count_queue), 0)

    def test_old_items_are_dropped(self):
        self.as_(USER)
        ok(api.add_to_queue, product="OLD")
        ok(api.add_to_queue, product="NEW")
        old = frappe.get_all("RxLabel Queue Item", filters={"product": "OLD"}, pluck="name")[0]
        frappe.db.set_value("RxLabel Queue Item", old, "creation",
                            frappe.utils.add_to_date(frappe.utils.now_datetime(), days=-31), update_modified=False)
        frappe.db.commit()
        self.assertEqual([q["product"] for q in ok(api.get_queue)], ["NEW"])


class TestClients(F1):
    def test_crud_and_duplicate_names(self):
        self.as_(USER)
        a = self.add_client("Ama Mensah", home_address="Madina")
        b = self.add_client("Kofi Boateng")
        self.assertEqual([c["name"] for c in ok(api.get_clients)], ["Kofi Boateng", "Ama Mensah"])  # newest first
        self.assertEqual(ok(api.get_client_by_id, id=a)["home_address"], "Madina")
        status, reply = call(api.add_client, name="Ama Mensah", contact="", email="")
        self.assertEqual((reply["code"], reply["message"]), ("CONFLICT", "A client with this name already exists."))
        self.assertEqual(call(api.update_client, id=b, name="Ama Mensah", contact="", email="")[1]["code"],
                         "CONFLICT")
        ok(api.update_client, id=b, name="Kofi B.", contact="055", email="k@x", home_address=None)
        self.assertEqual(ok(api.get_client_by_id, id=b)["contact"], "055")
        self.assertEqual(ok(api.count_clients), 2)
        ok(api.delete_client, id=b)
        self.assertEqual(call(api.delete_client, id=b)[1]["code"], "NOT_FOUND")
        self.assertEqual(call(api.get_client_by_id, id=b)[1]["code"], "NOT_FOUND")

    def test_branches_dont_see_each_others_clients(self):
        self.as_(USER)
        a = self.add_client("Ama Mensah")
        ok(api.add_client_label, client_id=a, product="ORS")
        self.as_(MANAGER, self.tema)
        self.assertEqual(ok(api.get_clients), [])
        self.add_client("Ama Mensah")  # the same name is fine at another branch
        for fn, kw in ((api.get_client_by_id, {"id": a}), (api.delete_client, {"id": a}),
                       (api.update_client, {"id": a, "name": "X", "contact": "", "email": ""}),
                       (api.add_client_label, {"client_id": a, "product": "X"}),
                       (api.copy_client_label_to_queue, {"id": a})):
            self.assertEqual(call(fn, **kw)[1]["code"], "NOT_FOUND", fn.__name__)
        self.assertEqual(ok(api.get_client_labels, client_id=a), [])
        self.assertEqual(ok(api.count_client_labels, client_id=a), 0)

    def test_client_labels(self):
        self.as_(USER)
        c = self.add_client()
        one = ok(api.add_client_label, client_id=c, product="ORS", instructions="Dissolve", warning=None)
        ok(api.add_client_labels, data=[{"client_id": c, "product": "ZINC", "instructions": "x", "warning": None},
                                        {"client_id": c, "product": "PARA", "instructions": "y", "warning": "w"}])
        self.assertEqual([l["product"] for l in ok(api.get_client_labels, client_id=c)], ["ORS", "ZINC", "PARA"])
        ok(api.update_client_label, id=one, product="ORS 2", instructions=None, warning=None)
        ok(api.delete_client_label, id=one)
        self.assertEqual(call(api.delete_client_label, id=one)[1]["code"], "NOT_FOUND")
        self.assertEqual(call(api.update_client_label, id=one, product="x")[1]["code"], "NOT_FOUND")
        self.assertEqual(ok(api.count_client_labels, client_id=c), 2)
        # all or none: a label for a client that doesn't exist stops the lot
        status, reply = call(api.add_client_labels, data=[{"client_id": c, "product": "A"},
                                                          {"client_id": 999999, "product": "B"}])
        self.assertEqual(reply["code"], "NOT_FOUND")
        self.assertEqual(ok(api.count_client_labels, client_id=c), 2)

    def test_copy_to_queue_respects_the_limit(self):
        self.as_(ADMIN, self.osu)
        ok(api.save_settings, data={"queue_size": 3})
        c = self.add_client()
        ok(api.add_client_labels, data=[{"client_id": c, "product": p, "instructions": "i"} for p in ("A", "B")])
        ok(api.add_to_queue, product="OLD")
        ok(api.copy_client_label_to_queue, id=c)
        self.assertEqual([(q["product"], q["client"], q["client_id"]) for q in ok(api.get_queue)],
                         [("OLD", None, None), ("A", "Ama Mensah", c), ("B", "Ama Mensah", c)])
        status, reply = call(api.copy_client_label_to_queue, id=c)
        self.assertEqual(reply["code"], "QUEUE_FULL")
        self.assertIn("remove the 2 oldest", reply["message"])
        ok(api.copy_client_label_to_queue, id=c, make_room=True)
        self.assertEqual([q["product"] for q in ok(api.get_queue)], ["B", "A", "B"])

    def test_deleting_a_client_keeps_queue_items_but_not_saved_labels(self):
        self.as_(USER)
        c = self.add_client()
        ok(api.add_client_label, client_id=c, product="ORS")
        ok(api.add_to_queue, product="BY NAME", client="Ama Mensah")
        ok(api.copy_client_label_to_queue, id=c)
        self.assertEqual([q["client_id"] for q in ok(api.get_queue)], [c, c])
        ok(api.delete_client, id=c)
        self.assertEqual(frappe.db.count("RxLabel Client Label", {"client": c}), 0)
        self.assertEqual([(q["client"], q["client_id"]) for q in ok(api.get_queue)],
                         [("Ama Mensah", None), ("Ama Mensah", None)])

    def test_read_only_when_the_licence_has_expired(self):
        self.as_(USER)
        c = self.add_client()
        frappe.db.set_single_value("RxLabel Settings", "license_expires_at", int(time.time()) - 60)
        frappe.db.commit()
        for fn, kw in ((api.add_client, {"name": "B", "contact": "", "email": ""}), (api.delete_client, {"id": c}),
                       (api.add_to_queue, {"product": "X"}), (api.create_label, {"product": "X", "instructions": "",
                                                                                "warning": ""})):
            self.assertEqual(call(fn, **kw)[1]["code"], "LICENSE_EXPIRED", fn.__name__)
        self.assertEqual(len(ok(api.get_clients)), 1)  # reading still works


class TestPhrases(F1):
    def test_phrases_are_the_companys(self):
        self.as_(USER)
        starter = ok(api.get_instruction_phrases)
        self.assertTrue(starter)
        self.assertEqual(call(api.save_instruction_phrases, phrases=["x"])[1]["code"], "FORBIDDEN")
        self.as_(MANAGER, self.osu)
        saved = ok(api.save_instruction_phrases, phrases=["  Take with food ", "Take with food", "Shake well"])
        self.as_(MANAGER, self.tema)
        self.assertEqual(ok(api.get_instruction_phrases), saved)
        options = ok(api.save_instruction_options, options={"count": ["ONE (1)", "TWO (2)"]})
        self.as_(USER)
        self.assertEqual(ok(api.get_instruction_options), options)

    def test_common_instructions_use_this_branchs_clients(self):
        self.as_(USER)
        c = self.add_client()
        for _ in range(3):
            ok(api.add_client_label, client_id=c, product="ORS", instructions="Osu only instruction")
        texts = [i["text"] if isinstance(i, dict) else i for i in ok(api.get_common_instructions)]
        self.assertIn("Osu only instruction", str(texts))
        self.as_(MANAGER, self.tema)
        self.assertNotIn("Osu only instruction", str(ok(api.get_common_instructions)))


class TestSettings(F1):
    def test_aux_permissions_and_branches(self):
        self.as_(USER)
        ok(api.set_aux_setting, key="printer_model", value="DT60")
        self.assertEqual(call(api.set_aux_setting, key="label_settings", value={})[1]["code"], "FORBIDDEN")
        self.assertEqual(call(api.set_aux_setting, key="anything", value=1)[1]["code"], "FORBIDDEN")
        self.assertEqual(ok(api.get_all_aux_settings)["printer_model"], "DT60")
        self.assertEqual(ok(api.get_aux_setting, key="printer_model"), "DT60")
        self.as_(MANAGER, self.tema)
        self.assertNotIn("printer_model", ok(api.get_all_aux_settings))
        self.as_(ADMIN, self.tema)
        ok(api.set_aux_setting, key="label_settings", value={"client_label": "Patient"})
        ok(api.set_aux_setting, key="idle_timeout_minutes", value=30)  # the company's
        self.as_(USER)
        everything = ok(api.get_all_aux_settings)
        self.assertNotIn("label_settings", everything)
        self.assertEqual(everything["idle_timeout_minutes"], 30)
        ok(api.set_aux_setting, key="printer_model", value=None)
        self.assertIsNone(ok(api.get_aux_setting, key="printer_model"))

    def test_facility_and_date_format(self):
        self.as_(USER)
        before = ok(api.get_settings)
        self.assertEqual((before["facility_name"], before["facility_address"], before["date_format"],
                          before["queue_size"], before["alert_sound"]),
                         ("Osu Pharmacy", "12 Oxford St, Accra", "dt5", 100, 1))
        ok(api.save_settings, data={"facility_name": "Hacked", "queue_size": 5, "date_format": "dt3"})
        after = ok(api.get_settings)
        self.assertEqual((after["facility_name"], after["queue_size"], after["date_format"]),
                         ("Osu Pharmacy", 100, "dt3"))
        self.assertEqual(call(api.save_settings, data={"date_format": "yyyy-MM-dd"})[1]["code"], "VALIDATION")
        self.as_(MANAGER, self.tema)
        self.assertEqual(ok(api.get_settings)["date_format"], "dt5")  # Osu's choice only
        self.as_(ADMIN, self.osu)
        ok(api.save_settings, data={"facility_name": "Osu Main Pharmacy", "facility_contact": "030 200 0001"})
        self.assertEqual(ok(api.get_me)["branch"]["facility_name"], "Osu Main Pharmacy")
        self.assertIsNone(frappe.db.get_value("RxLabel Branch Settings", self.osu, "facility_contact"))
        ok(api.save_settings, data={"facility_name": "Osu Pharmacy"})  # back to the Warehouse's own
        self.assertIsNone(frappe.db.get_value("RxLabel Branch Settings", self.osu, "facility_name"))

    def test_theme_is_each_users(self):
        frappe.set_user("Guest")
        self.assertEqual(ok(api.get_theme), "system")
        ok(api.set_theme, theme="dark")  # kept by the browser
        self.as_(USER)
        self.assertEqual(ok(api.get_theme), "system")
        ok(api.set_theme, theme="dark")
        self.assertEqual(ok(api.get_theme), "dark")
        self.assertEqual(call(api.set_theme, theme="pink")[1]["code"], "VALIDATION")
        self.as_(MANAGER)
        self.assertEqual(ok(api.get_theme), "system")
