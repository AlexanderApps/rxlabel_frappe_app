app_name = "rxlabel"
app_title = "RxLabel"
app_publisher = "Alexander Appiah"
app_description = "RxLabel medication labels in Frappe / ERPNext"
app_email = "alexanderapps6699@gmail.com"
app_license = "Proprietary"
required_apps = ["frappe", "erpnext"]

# The RxLabel app (Vue, built into public/frontend) at /rxlabel.
website_route_rules = [{"from_route": "/rxlabel/<path:app_path>", "to_route": "rxlabel"}]

add_to_apps_screen = [
    {
        "name": "rxlabel",
        "logo": "/assets/rxlabel/frontend/rxlabel-logo.svg",
        "title": "RxLabel",
        "route": "/rxlabel",
        "has_permission": "rxlabel.access.can_use",
    }
]

after_install = "rxlabel.install.after_install"
after_migrate = "rxlabel.install.after_migrate"


# Settle prints the browser never reported and drop history older than 30 days
# (also done whenever someone prints or opens the history).
scheduler_events = {"daily": ["rxlabel.history.daily"]}
