"""F2: printing, as the standalone app does it (web/tests/test_print_history.py,
test_api.py, test_label_images.py, test_label_checks.py), per branch."""

import base64
import io

import frappe

from rxlabel import api, history

from .test_f1 import ADMIN, F1, MANAGER, USER
from .utils import call, ok

LABEL = {"product": "PARACETAMOL 500MG TABLETS", "instructions": "Swallow TWO(2)", "client": "Ama Mensah"}


def build(labels, **kw):
    return ok(api.build_print_jobs, template="base", print_type="json", vars_list=labels, **kw)


def done(i, held=False):
    return {"index": i, "success": True, "held": held, "code": None}


def bad(i, code="print_failed"):
    return {"index": i, "success": False, "held": False, "code": code}


def png_size(data_url):
    from PIL import Image
    return Image.open(io.BytesIO(base64.b64decode(data_url.split(",", 1)[1]))).size


class F2(F1):
    def setUp(self):
        super().setUp()
        frappe.db.delete("RxLabel Print History", {"branch": ["in", [self.osu, self.tema]]})
        frappe.db.delete("RxLabel Print Batch", {"branch": ["in", [self.osu, self.tema]]})
        frappe.db.commit()

    def full_name(self, user):
        return frappe.db.get_value("User", user, "full_name")


class TestJobs(F2):
    def test_jobs_carry_the_branchs_details_and_calibration(self):
        self.as_(ADMIN, self.osu)
        ok(api.set_aux_setting, key="print_calibration", value={"offset_x": 1.0, "offset_y": 0, "rotation": 0})
        label = {**LABEL, "warning": None, "timestamp": "2026-11-04 05:41", "copies": "2",
                 "facility_name": "Typed by someone", "user_name": "someone else"}
        built = build([label])
        self.assertEqual((built["labels"], [j["label"] for j in built["jobs"]]), (1, [0, 0]))
        page = built["jobs"][0]["job"]["jobPages"][0]
        texts = [el.get("text") for el in page if el["type"] == "text"]
        self.assertIn("Osu Pharmacy", texts)
        self.assertNotIn("Typed by someone", texts)  # the branch's details win
        self.assertTrue(any(self.full_name(ADMIN) in (t or "") for t in texts))
        self.assertEqual(next(el for el in page if el["type"] == "rectangle")["x"], 2.0)  # 1 + calibration
        self.as_(ADMIN, self.tema)  # Tema: its own name, no calibration
        page = build([label])["jobs"][0]["job"]["jobPages"][0]
        self.assertIn("Tema Pharmacy", [el.get("text") for el in page])
        self.assertEqual(next(el for el in page if el["type"] == "rectangle")["x"], 1.0)

    def test_bad_labels_are_refused(self):
        self.as_(USER)
        reply = call(api.build_print_jobs, template="base", vars_list=[{"product": "X"}])[1]
        self.assertEqual(reply["code"], "VALIDATION")
        self.assertIn("could not be prepared", reply["message"])
        self.assertEqual(call(api.build_print_jobs, template="nope", vars_list=[LABEL])[1]["code"], "VALIDATION")
        self.assertEqual(call(api.build_print_jobs, template="base", vars_list=[])[1]["code"], "VALIDATION")
        self.assertEqual(call(api.build_print_jobs, template="base", vars_list=[LABEL], queue_ids=[1, 2])[1]["code"],
                         "VALIDATION")

    def test_image_printing_and_preview(self):
        self.as_(USER)
        built = ok(api.build_print_jobs, template="base", print_type="image", vars_list=[{**LABEL, "copies": "2"}],
                   dpi=300)
        el = built["jobs"][0]["job"]["jobPages"][0][0]
        self.assertEqual((el["type"], el["width"], el["height"]), ("image", 48.0, 54.0))
        self.assertEqual(png_size(el["imageFile"]), (2268, 2552))
        preview = ok(api.build_preview_job, template="base", print_type="image", vars=LABEL, dpi=203)["preview"]
        self.assertEqual(png_size(preview["image"]), (384, 432))
        text = ok(api.build_preview_job, template="base", print_type="json", vars=LABEL)
        self.assertIn("job", text)
        self.assertTrue(text["notes"])
        self.assertEqual(frappe.db.count("RxLabel Print Batch", {"branch": self.osu}), 1)  # previews: none

    def test_templates_sizes_and_test_label(self):
        self.as_(USER)
        self.assertIn("base", ok(api.list_templates))
        self.assertEqual(call(api.list_label_sizes)[1]["code"], "FORBIDDEN")
        self.assertEqual(call(api.build_test_label, print_type="json")[1]["code"], "FORBIDDEN")
        self.as_(ADMIN, self.osu)
        self.assertTrue(ok(api.list_label_sizes))
        texts = [e.get("text") for e in ok(api.build_test_label, print_type="json", printer="DT-108B",
                                           dpi=203)["job"]["jobPages"][0]]
        self.assertIn("RxLabel test label", texts)
        image = ok(api.build_test_label, print_type="image")["job"]
        self.assertEqual(image["jobPages"][0][0]["type"], "image")

    def test_client_jobs(self):
        self.as_(USER)
        c = self.add_client()
        self.assertEqual(call(api.build_client_print_jobs, client_id=c)[1]["code"], "VALIDATION")  # no labels
        ok(api.add_client_label, client_id=c, product="ORS", instructions="Dissolve")
        built = ok(api.build_client_print_jobs, client_id=c, timestamp="2026-11-07 07:00")
        texts = [el.get("text") for el in built["jobs"][0]["job"]["jobPages"][0]]
        self.assertIn("ORS", texts)
        self.assertTrue(any("Ama Mensah" in (t or "") for t in texts))
        self.as_(MANAGER, self.tema)  # not Tema's client
        self.assertEqual(call(api.build_client_print_jobs, client_id=c)[1]["code"], "VALIDATION")
        self.assertEqual(ok(api.check_client_print, client_id=c), [])


class TestHistory(F2):
    def test_batch_is_recorded_once_and_shows_in_history(self):
        self.as_(MANAGER, self.osu)
        built = build([{**LABEL, "copies": "2"}, {"product": "ORS", "instructions": "Dissolve"}])
        self.assertEqual([j["label"] for j in built["jobs"]], [0, 0, 1])
        self.assertEqual(ok(api.record_print, batch=built["batch"], results=[done(0), done(1), bad(2)]),
                         {"recorded": 2})
        self.assertEqual(call(api.record_print, batch=built["batch"], results=[])[1]["code"], "NOT_FOUND")
        found = ok(api.get_print_history, days=1)
        name = self.full_name(MANAGER)
        self.assertEqual([(i["product"], i["client"], i["copies"], i["outcome"], i["user_name"])
                          for i in found["items"]],
                         [("ORS", None, 1, "failed", name), ("PARACETAMOL 500MG TABLETS", "Ama Mensah", 2, "printed",
                                                             name)])
        self.assertEqual((found["total"], found["keep_days"]), (2, 30))
        self.assertRegex(found["items"][0]["printed_at"], r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d$")

    def test_each_branch_has_its_own_history(self):
        self.as_(MANAGER, self.osu)
        built = build([LABEL])
        self.as_(MANAGER, self.tema)  # switched branch before reporting: still Osu's print
        ok(api.record_print, batch=built["batch"], results=[done(0)])
        self.assertEqual(ok(api.get_print_history, days=1)["items"], [])
        self.assertEqual(ok(api.check_print, template="base", vars_list=[LABEL]), [])  # not printed at Tema
        self.as_(MANAGER, self.osu)
        self.assertEqual(len(ok(api.get_print_history, days=1)["items"]), 1)
        self.assertEqual([w["kind"] for w in ok(api.check_print, template="base", vars_list=[LABEL])],
                         ["recently_printed"])

    def test_only_the_printer_can_report_and_staff_see_history(self):
        self.as_(USER)
        built = build([LABEL])
        self.assertEqual(call(api.get_print_history, days=1)[1]["code"], "FORBIDDEN")
        self.as_(MANAGER, self.osu)
        self.assertEqual(call(api.record_print, batch=built["batch"], results=[done(0)])[1]["code"], "NOT_FOUND")

    def test_remove_after_print_drops_printed_queue_items(self):
        self.as_(USER)
        for p in ("A", "B"):
            ok(api.add_to_queue, product=p, instructions="x")
        queue = ok(api.get_queue)
        labels = [{"product": q["product"], "instructions": "x"} for q in queue]
        built = build(labels, queue_ids=[q["id"] for q in queue])
        ok(api.record_print, batch=built["batch"], results=[done(0), bad(1)])
        self.assertEqual(len(ok(api.get_queue)), 2)  # setting off: kept
        ok(api.set_aux_setting, key="queue_remove_after_print", value=True)
        built = build(labels, queue_ids=[q["id"] for q in queue])
        ok(api.record_print, batch=built["batch"], results=[done(0), bad(1)])
        self.assertEqual([q["product"] for q in ok(api.get_queue)], ["B"])  # the failed one stays

    def test_unreported_batches_are_recorded_as_not_printed(self):
        self.as_(MANAGER, self.osu)
        built = build([LABEL])
        frappe.db.set_value("RxLabel Print Batch", built["batch"], "creation",
                            frappe.utils.add_to_date(frappe.utils.now_datetime(), minutes=-31), update_modified=False)
        frappe.db.commit()
        items = ok(api.get_print_history, days=1)["items"]
        self.assertEqual([(i["outcome"], i["error_code"]) for i in items], [("failed", "no_result")])

    def test_daily_job_settles_and_purges(self):
        self.as_(MANAGER, self.osu)
        built = build([LABEL])
        ok(api.record_print, batch=built["batch"], results=[done(0)])
        old = frappe.get_all("RxLabel Print History", filters={"branch": self.osu}, pluck="name")[0]
        frappe.db.set_value("RxLabel Print History", old, "printed_at",
                            frappe.utils.add_to_date(frappe.utils.now_datetime(), days=-31), update_modified=False)
        stale = build([LABEL])["batch"]
        frappe.db.set_value("RxLabel Print Batch", stale, "creation",
                            frappe.utils.add_to_date(frappe.utils.now_datetime(), minutes=-31), update_modified=False)
        frappe.db.commit()
        history.daily()
        rows = frappe.get_all("RxLabel Print History", filters={"branch": self.osu}, fields=["outcome", "error_code"])
        self.assertEqual([(r.outcome, r.error_code) for r in rows], [("failed", "no_result")])
        self.assertFalse(frappe.db.exists("RxLabel Print Batch", stale))


class TestChecks(F2):
    def test_check_print_warnings(self):
        self.as_(ADMIN, self.osu)
        built = build([LABEL])
        ok(api.record_print, batch=built["batch"], results=[done(0)])
        batch = [LABEL, LABEL, {"product": "ORS", "instructions": " "}]
        warnings = ok(api.check_print, template="base", vars_list=batch)
        self.assertEqual([w["kind"] for w in warnings], ["recently_printed", "duplicate_in_batch", "no_instructions"])
        self.assertIn("already printed for Ama Mensah less than a minute ago", warnings[0]["message"])
        settings = {"width_mm": 48.0, "height_mm": 54.0, "readable_main_mm": 3.0, "readable_other_mm": 2.0,
                    "double_print_minutes": 0, "client_label": "Client:", "dispensed_by_label": "Disp by:"}
        ok(api.set_aux_setting, key="label_settings", value=settings)
        self.assertEqual(ok(api.check_print, template="base", vars_list=[LABEL]), [])  # double-print check off

    def test_failed_prints_dont_count_as_recent(self):
        self.as_(USER)
        built = build([LABEL])
        ok(api.record_print, batch=built["batch"], results=[bad(0)])
        self.assertEqual(ok(api.check_print, template="base", vars_list=[LABEL]), [])

    def test_too_long_and_client_checks(self):
        self.as_(USER)
        long = {**LABEL, "product": "PARACETAMOL " * 12}
        kinds = [w["kind"] for w in ok(api.check_print, template="base", vars_list=[long])]
        self.assertIn("too_long", kinds)
        c = self.add_client()
        ok(api.add_client_label, client_id=c, product="ORS", instructions="")
        self.assertEqual([w["kind"] for w in ok(api.check_client_print, client_id=c)], ["no_instructions"])

    def test_preview_allowed_when_read_only(self):
        self.as_(USER)
        frappe.db.set_single_value("RxLabel Settings", "license_expires_at", 1)
        frappe.db.commit()
        self.assertEqual(call(api.build_print_jobs, template="base", vars_list=[LABEL])[1]["code"], "LICENSE_EXPIRED")
        self.assertIn("job", ok(api.build_preview_job, template="base", vars=LABEL))
