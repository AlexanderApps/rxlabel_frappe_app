"""RxLabel commands at /api/method/rxlabel.api.<command> (the same names and
replies as the standalone app, so the frontend works unchanged).

Errors reply in RxLabel's format, which the frontend reads:
    {"exc_type": "RxLabelError", "code": "...", "message": "..."} with the
    code's HTTP status; nothing the command did is saved.
"""

from __future__ import annotations

from .base import command  # noqa: F401
from .auth import change_password, get_me, login, logout  # noqa: F401,E402
from .branches import get_branches, set_branch  # noqa: F401,E402
from .setup import accept_terms, check_setup_status, get_terms_status, update_app_license, verify_license_key  # noqa: F401,E402
from .clients import (  # noqa: F401,E402
    add_client, add_client_label, add_client_labels, copy_client_label_to_queue, count_client_labels, count_clients,
    delete_client, delete_client_label, get_client_by_id, get_client_labels, get_clients, update_client,
    update_client_label)
from .labels import create_label, delete_label, get_all_labels, get_labels, update_label  # noqa: F401,E402
from .phrases import (  # noqa: F401,E402
    get_common_instructions, get_instruction_options, get_instruction_phrases, save_instruction_options,
    save_instruction_phrases)
from .queue import add_to_queue, check_queue_room, clear_queue, count_queue, get_queue, remove_from_queue  # noqa: F401,E402
from .settings import (  # noqa: F401,E402
    get_all_aux_settings, get_aux_setting, get_settings, get_theme, save_settings, set_aux_setting, set_theme)
from .printing import (  # noqa: F401,E402
    build_client_print_jobs, build_preview_job, build_print_jobs, build_test_label, check_client_print, check_print,
    get_print_history, list_label_sizes, list_templates, record_print)
from .admin import export_diagnostics, get_general_stats, get_users  # noqa: F401,E402
from .movein import move_in_data  # noqa: F401,E402
