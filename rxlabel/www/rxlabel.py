"""/rxlabel: the RxLabel app (the Vue frontend, built into public/frontend;
rxlabel.html is its index.html, written by the frontend's build:frappe)."""

import frappe

no_cache = 1


def get_context(context):
    # The page sends this with every command (Frappe's CSRF protection).
    context.csrf_token = frappe.sessions.get_csrf_token()
    frappe.db.commit()  # the token is stored with the session
    context.no_cache = 1
    return context
