# -*- coding: utf-8 -*-
"""Regression tests for pulling upstream Shopvpn features into this fork.

Every upstream merge is a chance to (a) drop the fork's own install/runtime
fixes, or (b) pull in a module that imports a package the lean installer never
installs. Both would show up as a broken install/update on a customer server,
so they are pinned here.
"""
import ast
import pathlib
import re
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKIP_DIRS = {
    ".git",
    ".github",
    "__pycache__",
    "backups",
    "tests",
    "translation-venv",
    "venv",
}

# Packages that ship as dependencies of a declared requirement (fastapi pulls
# both pydantic and starlette), so they never need their own requirements line.
TRANSITIVE_DEPS = {"pydantic", "starlette"}

# dist-name -> import-name for the requirements that differ.
DIST_ALIASES = {
    "python-dotenv": "dotenv",
    "python-bidi": "bidi",
    "pillow": "PIL",
    "pyjwt": "jwt",
    "python-multipart": "multipart",
    "deep-translator": "deep_translator",
    "google-genai": "google",
}

# Modules added by upstream that the fork must keep shipping and wiring up.
UPSTREAM_FEATURE_MODULES = (
    "admin_campaign.py",
    "admin_help.py",
    "ai_admin.py",
    "ai_media.py",
    "ai_text.py",
    "bank_inquiry.py",
    "campaign_ai.py",
    "churn_prediction.py",
    "draft_stream.py",
    "extra_settings_schema.py",
    "db/orders.py",
    # --- upstream batch merged with the next release ---
    "audit_forwarder.py",
    "admin_channel_engage.py",
    "admin_channel_plan.py",
    "admin_channel_posts.py",
    "admin_post_brand.py",
    "channel_ai.py",
    "channel_post_scheduler.py",
    "channel_suggestions.py",
    "gift_card_ai.py",
    "gift_card_handlers.py",
    "gift_card_render.py",
    "gift_cards.py",
    "jarvis_guide.py",
    "leak_admin.py",
    "leak_index.py",
    "leak_scanner.py",
    "post_image.py",
    "price_display.py",
    "product_waitlist.py",
    "userbot.py",
    "userbot_admin.py",
    "db/gift_cards.py",
    "db/leak_store.py",
    "db/userbot_store.py",
    # --- upstream batch: competitive seasons, daily quiz, lootbox engagement,
    # --- smart leak/channel discovery ---
    "daily_quiz.py",
    "engagement.py",
    "engagement_handlers.py",
    "leak_discovery.py",
    "season_quiz_handlers.py",
    "seasons.py",
    "db/engagement.py",
    "db/seasons.py",
    # --- upstream batch: dedicated sub, web store, in-bot updater ---
    "dedicated_sub.py",
    "admin_dedicated_sub.py",
    "db/dedicated_sub.py",
    "sub_server/__init__.py",
    "sub_server/server.py",
    "web_auth.py",
    "web_store/__init__.py",
    "web_store/routes.py",
    "web_store/server.py",
    "updater.py",
    "admin_update.py",
    # --- upstream batch: SSH nodes + unified VPN/SSH quota pools ---
    "quota_reconciler.py",
    "ssh_admin.py",
    "ssh_admin_bot.py",
    "ssh_auto_install.py",
    "ssh_credentials.py",
    "ssh_node_agent.py",
    "ssh_providers.py",
    "ssh_service.py",
    "ssh_uri.py",
    "db/usage.py",
    "config_geo.py",
    "multi_target.py",
    "db/multi_target.py",
    "ssh_hosts.py",
    # --- upstream batch: product targets, panel capabilities, panel resync,
    # --- per-product renewal rules, extra-settings editor in the bot ---
    "product_targets.py",
    "panel_capabilities.py",
    "panel_resync.py",
    "renewal_rules.py",
    "admin_extra_settings.py",
    "check_settings_sync.py",
    "settings_parity_baseline.json",
    # --- upstream batch: W-UI panel, cross-panel user migration, multi
    # --- card-to-card cards ---
    "panel_providers/wui_provider.py",
    "panel_migration.py",
    "admin_panel_migration.py",
    "db/panel_migration.py",
    # --- upstream batch: account naming, buy guide, card UI, admin links,
    # --- multi-channel force-join ---
    "account_naming.py",
    "admin_links.py",
    "buy_guide.py",
    "card_payment_ui.py",
    "force_join_channels.py",
    # --- upstream batch: hourly system cron, signup config gift, emoji prefs,
    # --- Stealth VLESS panel type, web DB manager ---
    "cron_checks.py",
    "welcome_gift.py",
    "emoji_prefs.py",
    "stealth_auto_install.py",
    "panel_providers/stealth_provider.py",
    # --- upstream batch: phone-prefix verification, saved user groups,
    # --- subscriptions page and auto banners ---
    "phone_gate.py",
    "db/user_groups.py",
    "db/subscriptions.py",
    # --- upstream batch: PayG billing, Telegram widgets, bot profile,
    # --- category description media, delivery extras, album copying ---
    "payg.py",
    "widgets.py",
    "widgets_pro.py",
    "widget_html.py",
    "widget_html_pro.py",
    "bot_profile.py",
    "category_media.py",
    "delivery_extras.py",
    "telegram_media.py",
    # --- upstream batch: custom glass-menu buttons, accounting formulas,
    # --- mini-app home tiles, web-panel assistant, web-admin 2FA ---
    "custom_menu_buttons.py",
    "db/custom_menu.py",
    "accounting.py",
    "home_tiles.py",
    "web_assistant.py",
    # --- upstream 9.6.0: hidden web entry path, slash-command registry, ledger,
    # --- web-store customization/maintenance, per-product start mode ---
    "web_entry_gate.py",
    "admin_panel/entry_path_cli.py",
    "admin_panel/telegram_notify.py",
    "bot_commands.py",
    "gear_svg.py",
    "web_store/customize.py",
    "web_store/maintenance_page.py",
    # --- upstream 9.7.0: Doctor DNS panel type, license source offer ---
    "panel_providers/doctordns_provider.py",
    "source_offer.py",
    # --- upstream 9.8.2: tenant context, in-bot Telegram login, Doctor DNS SSH
    # --- bootstrap, quota-pool first use, full-reseller conversion ---
    "tenant_ctx.py",
    "userbot_login.py",
    "doctor_dns_ssh_setup.py",
)

# Upstream keeps re-uploading these with a module-level `from i18n import tr`
# on line 1, which pushes the `# -*- coding: utf-8 -*-` declaration out of the
# legal position. The fork moved the import below the docstring instead.
IMPORT_ORDER_FIXED_FILES = (
    "config_delivery.py",
    "force_join.py",
    "handlers_admin.py",
)


def _iter_project_python_files():
    for path in sorted(ROOT.rglob("*.py")):
        parts = set(path.relative_to(ROOT).parts)
        if parts & SKIP_DIRS:
            continue
        yield path


def _declared_requirement_modules():
    modules = set()
    for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name = re.split(r"[<>=!\[;]", line)[0].strip().lower()
        modules.add(DIST_ALIASES.get(name, name.replace("-", "_")))
    return modules


def _local_importable_names():
    names = set()
    for path in ROOT.rglob("*.py"):
        parts = set(path.relative_to(ROOT).parts)
        if parts & SKIP_DIRS:
            continue
        names.add(path.stem)
        if path.parent != ROOT:
            names.add(path.parent.name)
    return names


def _module_level_imports(path):
    tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                yield node.module.split(".")[0]


def test_payg_widgets_profile_media_and_delivery_extras_are_wired():
    """The 9.3.0 batch: every new module must be reachable from a real entry point."""
    bot_manager = (ROOT / "bot_manager.py").read_text(encoding="utf-8")
    assert "from payg import create_payg_router, PaygEngine" in bot_manager
    assert "dp.include_router(create_payg_router(db, is_main_bot=True))" in bot_manager
    assert "dp.include_router(widgets.create_router(db))" in bot_manager
    assert "import bot_profile" in bot_manager

    # PayG owns its own tables and its user command; orders refresh its quota.
    payg = (ROOT / "payg.py").read_text(encoding="utf-8")
    for table in ("payg_accounts", "payg_services", "payg_transactions",
                  "payg_provision_locks", "payg_provisioned_services"):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in payg
    assert '@router.message(Command("payg"))' in payg
    # 9.4.0 moved the PayG admin surface to the web panel; the bot keeps the user flow.
    assert '@router.callback_query(F.data == "payg:activate")' in payg
    payg_overview = '@app.get("/api/payg/overview")'
    assert payg_overview in (ROOT / "admin_panel/server.py").read_text(encoding="utf-8")
    assert "from payg import refresh_payg_quota" in (ROOT / "db/orders.py").read_text(encoding="utf-8")

    # Widgets are opened from the user account hub and the admin menu.
    keyboards = (ROOT / "keyboards.py").read_text(encoding="utf-8")
    assert "def user_widgets_menu_kb(" in keyboards
    assert "def admin_widgets_menu_kb(" in keyboards
    assert "def _widgets_on(db)" in keyboards
    widgets = (ROOT / "widgets.py").read_text(encoding="utf-8")
    assert "import widget_html" in widgets and "import widgets_pro" in widgets

    # Bot profile (description/short description) reaches Telegram from three processes.
    assert "bot_profile" in (ROOT / "extra_settings_schema.py").read_text(encoding="utf-8")
    assert "apply_profile" in (ROOT / "admin_extra_settings.py").read_text(encoding="utf-8")
    assert "import bot_profile" in (ROOT / "admin_panel/server.py").read_text(encoding="utf-8")
    assert "import bot_profile" in (ROOT / "miniapp/server.py").read_text(encoding="utf-8")

    # Category description + media are stored, edited in the admin and sent to users.
    catalog = (ROOT / "db/catalog.py").read_text(encoding="utf-8")
    assert "def set_category_description(" in catalog
    assert "def set_category_description_media(" in catalog
    handlers_admin = (ROOT / "handlers_admin.py").read_text(encoding="utf-8")
    assert "import category_media" in handlers_admin
    assert "import category_media" in (ROOT / "handlers_user.py").read_text(encoding="utf-8")

    # Delivery extras: per-product text/sticker and VPN files on delivery.
    config_delivery = (ROOT / "config_delivery.py").read_text(encoding="utf-8")
    assert "import delivery_extras" in config_delivery
    assert "def _send_product_extras(" in config_delivery
    assert "import delivery_extras" in (ROOT / "admin_panel/config_delivery_web.py").read_text(encoding="utf-8")

    # Albums are copied without downloading (broadcast + delivery).
    assert "from telegram_media import collect_media_group" in handlers_admin
    assert "def copy_messages(" in (ROOT / "telegram_media.py").read_text(encoding="utf-8")

    # Reads no longer queue behind the single writer connection.
    base = (ROOT / "db/_base.py").read_text(encoding="utf-8")
    assert "def _get_read_conn(" in base
    assert "query_only = ON" in base
    assert "_get_read_conn" in (ROOT / "db/tickets.py").read_text(encoding="utf-8")

    # The delivery-template fields are read dynamically, so they are not dead keys.
    assert 'f"delivery_message_template_{provider_key}"' in config_delivery


def test_upstream_feature_modules_still_shipped_and_wired():
    """The merged upstream modules must exist and stay reachable from the bot."""
    for relative in UPSTREAM_FEATURE_MODULES:
        path = ROOT / relative
        assert path.is_file(), f"{relative} disappeared from the fork"
        assert path.stat().st_size > 0, f"{relative} is empty"

    # Wired into the running bot / admin panel, not just sitting in the tree.
    assert "from churn_prediction import churn_offer_loop" in (ROOT / "bot_manager.py").read_text(encoding="utf-8")
    handlers_admin = (ROOT / "handlers_admin.py").read_text(encoding="utf-8")
    for module in ("admin_campaign", "admin_help", "ai_admin", "ai_media"):
        assert f"import {module}" in handlers_admin, f"{module} is no longer wired into the admin handlers"
    handlers_user = (ROOT / "handlers_user.py").read_text(encoding="utf-8")
    assert "import ai_media" in handlers_user
    assert "from draft_stream import DraftStreamer" in handlers_user

    # Bank inquiry backs the fake-receipt checks, extra settings back both web panels.
    assert "import bank_inquiry" in (ROOT / "receipt_ai_check.py").read_text(encoding="utf-8")
    admin_panel = (ROOT / "admin_panel/server.py").read_text(encoding="utf-8")
    assert "import extra_settings_schema" in admin_panel
    assert "extra_settings_schema" in (ROOT / "miniapp/server.py").read_text(encoding="utf-8")

    # Product waitlist (upstream 90fb055 batch, via origin/main).
    waitlist = (ROOT / "product_waitlist.py").read_text(encoding="utf-8")
    assert "async def notify_waitlist(" in waitlist
    assert "def bot_sender(" in waitlist
    catalog = (ROOT / "db/catalog.py").read_text(encoding="utf-8")
    for needle in ("def add_product_waitlist(", "def get_product_waitlist(", "def remove_product_waitlist("):
        assert needle in catalog, f"db/catalog.py lost {needle}"
    assert "CREATE TABLE IF NOT EXISTS product_waitlist" in (ROOT / "db/_base.py").read_text(encoding="utf-8")
    assert "db.add_product_waitlist" in handlers_user
    assert "product_waitlist.notify_waitlist" in handlers_admin
    assert "product_waitlist.notify_waitlist" in admin_panel
    assert "product_waitlist.notify_waitlist" in (ROOT / "miniapp/server.py").read_text(encoding="utf-8")

    handlers_admin = (ROOT / "handlers_admin.py").read_text(encoding="utf-8")
    assert "import account_naming" in handlers_admin
    assert "import admin_links" in handlers_admin
    assert "from force_join_channels import parse_channels" in handlers_admin
    handlers_user = (ROOT / "handlers_user.py").read_text(encoding="utf-8")
    assert "import card_payment_ui" in handlers_user
    assert "import buy_guide" in handlers_user
    assert "from force_join_channels import parse_channels" in (ROOT / "force_join.py").read_text(encoding="utf-8")
    assert "from force_join_channels import serialize_channels" in (ROOT / "admin_panel/server.py").read_text(encoding="utf-8")



def test_ssh_management_is_wired_end_to_end():
    """The SSH admin bot, shared quota service and config-link migration must stay
    reachable from the admin, mini app, subscription server and renewal path."""
    handlers_admin = (ROOT / "handlers_admin.py").read_text(encoding="utf-8")
    assert "import ssh_admin_bot" in handlers_admin
    assert "ssh_admin_bot.register(router, db" in handlers_admin

    keyboards = (ROOT / "keyboards.py").read_text(encoding="utf-8")
    assert '"adm_ssh_menu"' in keyboards
    assert "adm_ssh_menu_style" in (ROOT / "db/constants.py").read_text(encoding="utf-8")
    assert "adm_ssh_menu" in (ROOT / "admin_help.py").read_text(encoding="utf-8")
    assert "class AdminSSH(StatesGroup):" in (ROOT / "states.py").read_text(encoding="utf-8")

    admin_panel = (ROOT / "admin_panel/server.py").read_text(encoding="utf-8")
    assert '@app.post("/api/ssh/nodes/{node_id}/rename")' in admin_panel
    # The fork's manual node tools must not disappear in a future upstream sync.
    assert '@app.get("/api/ssh/install-package")' in admin_panel
    assert '@app.post("/api/ssh/nodes")' in admin_panel
    admin_js = (ROOT / "admin_panel/static/app.js").read_text(encoding="utf-8")
    assert "/rename`" in admin_js and "data-ssh-rename-node" in admin_js

    miniapp = (ROOT / "miniapp/server.py").read_text(encoding="utf-8")
    for route in ("/api/admin/ssh/overview", "/api/admin/ssh/nodes/auto-install",
                  "/api/admin/ssh/accounts", "/api/admin/ssh/reconcile"):
        assert route in miniapp, f"miniapp lost {route}"
    assert "adminSection === \"ssh\"" in (ROOT / "miniapp/static/app.js").read_text(encoding="utf-8")

    dedicated_sub = (ROOT / "dedicated_sub.py").read_text(encoding="utf-8")
    assert "def quota_info_for_config" in dedicated_sub
    assert "def ssh_uris_for_config" in dedicated_sub
    assert '"ssh://"' in dedicated_sub
    sub_server = (ROOT / "sub_server/server.py").read_text(encoding="utf-8")
    assert "quota_info_for_config" in sub_server
    assert "ssh_uris_for_config" in sub_server

    reconciler = (ROOT / "quota_reconciler.py").read_text(encoding="utf-8")
    assert "async def _sync_vpn_panel_limits" in reconciler
    assert "async def push_pool_expiry" in reconciler
    engine = (ROOT / "renewal_engine.py").read_text(encoding="utf-8")
    assert "async def renew_pooled_service" in engine
    assert "quota_pool_for_custom_config" in engine
    assert "renew_pooled_service" in (ROOT / "renewal_reminders.py").read_text(encoding="utf-8")

    providers = sorted(path.name for path in (ROOT / "panel_providers").glob("*_provider.py"))
    synced = [name for name in providers
              if "supports_data_limit_sync = True" in (ROOT / "panel_providers" / name).read_text(encoding="utf-8")]
    assert len(synced) >= 8, f"panel limit sync is missing from {set(providers) - set(synced)}"

    db_base = (ROOT / "db/_base.py").read_text(encoding="utf-8")
    assert "custom_config_id INTEGER" in db_base
    assert 'ALTER TABLE ssh_accounts ADD COLUMN custom_config_id INTEGER' in db_base
    db_usage = (ROOT / "db/usage.py").read_text(encoding="utf-8")
    for method in ("def link_ssh_account_to_config", "def ssh_accounts_for_config",
                   "def quota_pool_for_custom_config", "def update_ssh_node_name"):
        assert method in db_usage



def test_config_geo_is_wired_end_to_end():
    """Product locations from inventory configs must stay reachable from the web store."""
    assert "async def locate_products(" in (ROOT / "config_geo.py").read_text(encoding="utf-8")
    catalog = (ROOT / "db/catalog.py").read_text(encoding="utf-8")
    assert "def get_config_links_for_geo(" in catalog
    assert "def get_sub_urls_for_geo(" in catalog
    assert "/api/web/network-map" in (ROOT / "web_store/routes.py").read_text(encoding="utf-8")


def test_card_number_gate_is_wired_end_to_end():
    """The card-number display condition (upstream 91961c5/5a14239/63e9939) must
    stay wired: admin UI -> FSM state -> settings -> DB gate -> bot and miniapp.
    Without any of these edges the feature would silently do nothing, because
    both settings default to 0 (= no restriction)."""
    db_payments = (ROOT / "db/payments.py").read_text(encoding="utf-8")
    for needle in (
        'CARD_GATE_METHODS = ("card", "card_auto")',
        "def get_card_gate_settings(",
        "def card_gate_passed(",
        "def card_method_blocked_for_user(",
    ):
        assert needle in db_payments, f"db/payments.py lost {needle!r}"

    # Both settings exist and default to "off", so no existing install changes.
    db_constants = (ROOT / "db/constants.py").read_text(encoding="utf-8")
    assert '"card_gate_min_purchases": "0"' in db_constants
    assert '"card_gate_min_days": "0"' in db_constants

    # Admin entry point: button -> keyboard -> FSM state -> handler.
    keyboards = (ROOT / "keyboards.py").read_text(encoding="utf-8")
    assert "def card_gate_kb(" in keyboards
    assert 'callback_data="adm_cardgate"' in keyboards
    assert "adm_cardgate_edit:card_gate_min_purchases" in keyboards
    assert "adm_cardgate_edit:card_gate_min_days" in keyboards
    # The user-facing keyboard must consult the gate for the given user.
    assert "user_id: int = None" in keyboards
    assert "db.card_method_blocked_for_user(user_id, method_key)" in keyboards

    handlers_admin = (ROOT / "handlers_admin.py").read_text(encoding="utf-8")
    assert 'F.data == "adm_cardgate"' in handlers_admin
    assert 'F.data.startswith("adm_cardgate_edit:")' in handlers_admin
    assert "AdminCardGate.waiting_value" in handlers_admin
    assert "card_gate_setting" in handlers_admin  # admin action is logged

    states = (ROOT / "states.py").read_text(encoding="utf-8")
    assert "class AdminCardGate(StatesGroup):" in states

    # Bot side: both the order and the wallet-topup error paths check the gate,
    # and the renewal entry points re-check it before showing the card.
    handlers_user = (ROOT / "handlers_user.py").read_text(encoding="utf-8")
    assert handlers_user.count("db.card_method_blocked_for_user") >= 4, (
        "the card gate is no longer enforced on the bot payment paths"
    )
    assert '_order_payment_method_error(order, "card")' in handlers_user
    assert '_order_payment_method_error(order, "card_auto")' in handlers_user
    assert '_wallet_topup_method_error(amount, "card", call.from_user.id)' in handlers_user
    assert '_wallet_topup_method_error(amount, "card_auto", call.from_user.id)' in handlers_user

    # Mini app side: the card number must be withheld from the API response.
    miniapp = (ROOT / "miniapp/server.py").read_text(encoding="utf-8")
    assert "def _card_info(" in miniapp
    assert "if not db.card_gate_passed(user_id):" in miniapp
    assert '"card_number": None, "card_holder": None' in miniapp
    assert miniapp.count("**_card_info(db, tg_id)") >= 4, (
        "a miniapp endpoint still returns the raw card number"
    )
    assert "db.card_gate_passed(tg_id)" in miniapp  # card_to_card_enabled flag


def test_telegram_caption_limit_and_nginx_upload_budget_survive_merges():
    """Telegram rejects captions over 1024 chars, and nginx rejects bodies over
    1 MB - both were merged from upstream and must not be lost together."""
    admin_panel = (ROOT / "admin_panel/server.py").read_text(encoding="utf-8")
    assert "if len(text) > 1024:" in admin_panel
    assert 'media_type not in ("photo", "voice")' in admin_panel

    app_js = (ROOT / "admin_panel/static/app.js").read_text(encoding="utf-8")
    assert "res.status === 413" in app_js
    assert "client_max_body_size" in app_js

    # Every nginx server block we generate must accept large uploads, otherwise
    # the 413 message above is all the user ever sees.
    install = (ROOT / "install.sh").read_text(encoding="utf-8")
    manage = (ROOT / "manage.sh").read_text(encoding="utf-8")
    assert install.count("client_max_body_size 100m;") == 1
    assert manage.count("client_max_body_size 100m;") == manage.count("server_name $DOMAIN;"), (
        "a manage.sh nginx server block is missing the upload limit"
    )
    for script, text in (("install.sh", install), ("manage.sh", manage)):
        assert text.count("proxy_read_timeout 600s;") == text.count("client_max_body_size 100m;"), (
            f"{script}: upload limit and read timeout are out of sync"
        )


@pytest.mark.parametrize("relative", IMPORT_ORDER_FIXED_FILES)
def test_coding_declaration_stays_on_the_first_line(relative):
    """A PEP 263 coding line only counts on line 1 or 2 — keep it there."""
    lines = (ROOT / relative).read_text(encoding="utf-8").splitlines()
    assert lines and lines[0].startswith("# -*- coding: utf-8 -*-"), (
        f"{relative}: the coding declaration is no longer the first line"
    )
    for index, line in enumerate(lines):
        if line.startswith("from i18n import tr"):
            assert index > 1, f"{relative}: `from i18n import tr` back on the coding lines"
            break


def test_language_selection_migration_survives_upstream_merges():
    """New users are asked for fa/en once; existing users are never re-asked."""
    assert "ALTER TABLE users ADD COLUMN language_selected" in (ROOT / "db/_base.py").read_text(encoding="utf-8")
    assert "def is_user_language_selected" in (ROOT / "db/users.py").read_text(encoding="utf-8")
    assert "is_user_language_selected" in (ROOT / "force_join.py").read_text(encoding="utf-8")


def test_module_level_imports_are_declared():
    """Nothing imported at module level may be missing from a lean install.

    Imports inside functions are allowed to be optional (they are wrapped in
    try/except or only run for an explicitly enabled feature).
    """
    declared = _declared_requirement_modules()
    stdlib = set(sys.stdlib_module_names)
    local = _local_importable_names()

    undeclared = {}
    for path in _iter_project_python_files():
        for root in _module_level_imports(path):
            if root in stdlib or root in declared or root in local or root in TRANSITIVE_DEPS:
                continue
            undeclared.setdefault(root, []).append(str(path.relative_to(ROOT)))

    assert not undeclared, (
        "module-level imports that requirements.txt does not install: "
        + ", ".join(f"{mod} ({files[0]})" for mod, files in sorted(undeclared.items()))
    )


@pytest.mark.parametrize("relative,needle", [
    ("jalali.py", "Esfand (month 12)"),
    ("admin_panel/server.py", "is_language_enabled, LANGUAGE_CATALOG"),
    ("handlers_admin.py", "call.bot.send_message(uid, notification)"),
    ("cleanup_loop.py", "async def _notify_user(bot: Bot, db, user_id: int"),
])
def test_fork_runtime_fixes_survive_upstream_merges(relative, needle):
    """Fixes that upstream keeps re-introducing as bugs must not be lost."""
    assert needle in (ROOT / relative).read_text(encoding="utf-8")


def test_fork_runtime_fixes_survive_upstream_merges_multi():
    keyboards = (ROOT / "keyboards.py").read_text(encoding="utf-8")
    assert keyboards.count("def blupal_settings_kb(") == 1, "duplicate keyboard definition came back"

    handlers_user = (ROOT / "handlers_user.py").read_text(encoding="utf-8")
    assert handlers_user.count("call.bot, db,") >= 2, "undefined `bot` came back in the config-delete alerts"


def test_lean_install_flags_survive_upstream_merges():
    """Upstream's plain `pip install -r requirements.txt` must not sneak back in."""
    for script in ("manage.sh", "install.sh", "update.sh"):
        text = (ROOT / script).read_text(encoding="utf-8")
        assert "--no-cache-dir" in text or "PIP_NO_CACHE_DIR=1" in text, (
            f"{script} lost the disk-lean pip flag"
        )
    # CPU-only torch keeps the venv around 1.3 GB instead of pulling the CUDA build.
    assert "download.pytorch.org/whl/cpu" in (ROOT / "manage.sh").read_text(encoding="utf-8")



def test_new_upstream_features_stay_wired():
    """The merged upstream batch (userbot, leak scanner, gift cards, channel
    tools, payment-gate conditions): presence is not enough — each feature must
    stay reachable from a start-up task, handler, dispatcher or DB path, or it
    silently does nothing on a real server."""
    main_py = (ROOT / "main.py").read_text(encoding="utf-8")
    assert "import userbot" in main_py
    assert "userbot.run(main_db, BOT_TOKEN)" in main_py
    assert "import leak_index" in main_py
    assert "leak_index.run(main_db)" in main_py

    # Gift cards hook both config-delivery paths and register their routers.
    assert "from gift_card_handlers import deliver_gift_order" in (ROOT / "config_delivery.py").read_text(encoding="utf-8")
    web = (ROOT / "admin_panel/config_delivery_web.py").read_text(encoding="utf-8")
    assert "gift_get_order" in web and "gift_mark_order_delivered" in web
    bot_manager = (ROOT / "bot_manager.py").read_text(encoding="utf-8")
    assert "from gift_card_handlers import create_gift_router" in bot_manager
    assert "from userbot_admin import create_userbot_router" in bot_manager
    assert "from leak_admin import create_leak_router" in bot_manager
    assert "from channel_post_scheduler import channel_post_loop" in bot_manager
    assert "from audit_forwarder import audit_forward_loop" in bot_manager
    handlers_user = (ROOT / "handlers_user.py").read_text(encoding="utf-8")
    assert "from gift_card_handlers import redeem_gift_for_message" in handlers_user

    # Payment-gate conditions: admin callback -> FSM state -> settings -> DB.
    handlers_admin = (ROOT / "handlers_admin.py").read_text(encoding="utf-8")
    assert 'F.data == "adm_pmgate"' in handlers_admin
    assert "AdminPmGate.waiting_value" in handlers_admin
    assert "from price_display import price_range" in handlers_admin
    assert "import product_waitlist" in handlers_admin
    states = (ROOT / "states.py").read_text(encoding="utf-8")
    assert "class AdminPmGate(StatesGroup):" in states

    # Channel tools must stay imported AND registered on the admin router —
    # an import without register() is a menu button that does nothing.
    for module in ("admin_channel_posts", "admin_channel_engage", "admin_channel_plan"):
        assert f"import {module}" in handlers_admin, f"{module} import disappeared"
        assert f"{module}.register(router, db, senior_admin_only, deny_mid)" in handlers_admin, (
            f"{module} is imported but no longer registered on the admin router"
        )
    assert "import channel_suggestions" in (ROOT / "channel_post_scheduler.py").read_text(encoding="utf-8")
    keyboards = (ROOT / "keyboards.py").read_text(encoding="utf-8")
    assert "from price_display import price_label_plain" in keyboards
    assert "def pm_gate_list_kb(" in keyboards
    assert "def admin_category_item_keys(" in keyboards
    assert "USER_SCREENS = {" in keyboards

    # Channel-post CRUD lives in the DB layer the scheduler claims from.
    db_system = (ROOT / "db/system.py").read_text(encoding="utf-8")
    assert "def create_channel_post(" in db_system
    assert "def claim_channel_post(" in db_system

    # Multi-target extra panels + SSH admin menu (upstream 4.21 batch).
    assert "from multi_target import delete_linked_panel_users" in handlers_user
    assert "class MultiTargetMixin" in (ROOT / "db/multi_target.py").read_text(encoding="utf-8")
    assert "MultiTargetMixin," in (ROOT / "db/__init__.py").read_text(encoding="utf-8")
    assert "import ssh_admin_bot" in handlers_admin
    assert "ssh_admin_bot.register(router, db" in handlers_admin
    assert '"adm_ssh_menu"' in keyboards
    assert "import ssh_hosts" in (ROOT / "ssh_service.py").read_text(encoding="utf-8")
    assert "def build_ssh_uri(" in (ROOT / "ssh_uri.py").read_text(encoding="utf-8")


def test_payment_method_gate_is_wired_end_to_end():
    """Per-gateway activation conditions (pm_gate) must stay reachable.

    The admin sets "after N purchases / N days" per gateway; until then the
    gateway is hidden in the bot and the mini app, so every edge of that chain
    has to keep existing or the setting silently does nothing.
    """
    db_payments = (ROOT / "db/payments.py").read_text(encoding="utf-8")
    for needle in (
        "def payment_gate_setting_keys(",
        "def get_payment_gate_settings(",
        "def payment_gate_passed(",
    ):
        assert needle in db_payments, f"db/payments.py lost {needle!r}"

    keyboards = (ROOT / "keyboards.py").read_text(encoding="utf-8")
    assert "def pm_gate_list_kb(" in keyboards
    assert "def pm_gate_method_kb(" in keyboards
    assert 'callback_data="adm_pmgate"' in keyboards or '"adm_pmgate"' in keyboards

    handlers_admin = (ROOT / "handlers_admin.py").read_text(encoding="utf-8")
    assert 'F.data == "adm_pmgate"' in handlers_admin
    assert "AdminPmGate.waiting_value" in handlers_admin
    assert "class AdminPmGate(StatesGroup):" in (ROOT / "states.py").read_text(encoding="utf-8")

    miniapp = (ROOT / "miniapp/server.py").read_text(encoding="utf-8")
    assert miniapp.count("db.payment_gate_passed(") >= 4


def test_seasons_quiz_and_lootbox_stay_wired():
    """The seasons / daily-quiz / lootbox batch must stay reachable end to end.

    Presence is not wiring: a season loop that is never scheduled, a router
    that is imported but not included, or a lootbox order only the bot can
    approve all look perfectly healthy in a diff and do nothing on a server.
    """
    bot_manager = (ROOT / "bot_manager.py").read_text(encoding="utf-8")
    assert "import daily_quiz" in bot_manager
    assert "import seasons" in bot_manager
    assert "from season_quiz_handlers import create_season_quiz_router" in bot_manager
    assert "from engagement_handlers import create_engagement_router" in bot_manager
    # 4.38.0: upstream routes these through `full_access` (main bot + full
    # resellers) instead of the raw `is_main_bot` flag. The wiring edge is the
    # same; only the gate variable changed, so assert the edge, not the name.
    assert "dp.include_router(create_season_quiz_router(db, is_main_bot=full_access))" in bot_manager
    assert "dp.include_router(create_engagement_router(db, is_main_bot=full_access))" in bot_manager
    assert "full_access = bool(db.is_full_access_bot(is_main_bot))" in bot_manager
    assert "asyncio.create_task(seasons.season_loop(db, bot))" in bot_manager
    assert "asyncio.create_task(daily_quiz.quiz_loop(db, bot))" in bot_manager


    # Streak/points bookkeeping is triggered from the blocked-user touch path.
    blocked_user = (ROOT / "blocked_user.py").read_text(encoding="utf-8")
    assert "import engagement" in blocked_user
    assert 'engagement.schedule_touch(self.db, data["bot"], user.id)' in blocked_user

    # The mixins must ride on the Database class or their tables are unreachable.
    db_init = (ROOT / "db/__init__.py").read_text(encoding="utf-8")
    for needle in (
        "from .seasons import SeasonsMixin",
        "from .engagement import EngagementMixin",
        "    SeasonsMixin,",
        "    EngagementMixin,",
    ):
        assert needle in db_init, f"db/__init__.py lost {needle!r}"

    db_seasons = (ROOT / "db/seasons.py").read_text(encoding="utf-8")
    for needle in (
        "class SeasonsMixin",
        "def season_get_active(",
        "def season_standings(",
        "def season_user_stats(",
        "def badge_list(",
    ):
        assert needle in db_seasons, f"db/seasons.py lost {needle!r}"

    db_engagement = (ROOT / "db/engagement.py").read_text(encoding="utf-8")
    for needle in (
        "class EngagementMixin",
        "def approve_lootbox_order(",
        "def box_type_get(",
        "def box_type_allows_payment_method(",
    ):
        assert needle in db_engagement, f"db/engagement.py lost {needle!r}"

    seasons_py = (ROOT / "seasons.py").read_text(encoding="utf-8")
    for needle in ("def season_loop(", "def enabled(", "def mask_name(", "def prize_lines(",
                   "def fmt_local("):
        assert needle in seasons_py, f"seasons.py lost {needle!r}"

    daily_quiz = (ROOT / "daily_quiz.py").read_text(encoding="utf-8")
    assert "def quiz_loop(" in daily_quiz
    assert "def answer_quiz_for_message(" in daily_quiz
    assert "def schedule_touch(" in (ROOT / "engagement.py").read_text(encoding="utf-8")

    season_handlers = (ROOT / "season_quiz_handlers.py").read_text(encoding="utf-8")
    assert "def create_season_quiz_router(" in season_handlers
    assert "def show_season_for_message(" in season_handlers
    engagement_handlers = (ROOT / "engagement_handlers.py").read_text(encoding="utf-8")
    for needle in (
        "def create_engagement_router(",
        "def notify_lootbox_delivered(",
        "def show_lootbox_for_message(",
        "def show_progress_for_message(",
    ):
        assert needle in engagement_handlers, f"engagement_handlers.py lost {needle!r}"

    # Bot side: the account-hub entries and the lootbox payment-method gate.
    handlers_user = (ROOT / "handlers_user.py").read_text(encoding="utf-8")
    assert "from daily_quiz import answer_quiz_for_message" in handlers_user
    assert "from season_quiz_handlers import show_season_for_message" in handlers_user
    assert "from engagement_handlers import show_lootbox_for_message, show_progress_for_message" in handlers_user
    for action in ('"__open_season__"', '"__open_lootbox__"', '"__open_progress__"',
                   '"__quiz_answer__:"'):
        assert action in handlers_user, f"the account-hub entry {action} disappeared"
    assert "db.box_type_allows_payment_method" in handlers_user
    assert 'order["lootbox_type_id"]' in handlers_user

    # All three approval surfaces must keep telling the buyer about the boxes.
    handlers_admin = (ROOT / "handlers_admin.py").read_text(encoding="utf-8")
    assert "db.approve_lootbox_order" in handlers_admin
    assert "from engagement_handlers import notify_lootbox_delivered" in handlers_admin
    assert "kb.user_group_stats_kb" in handlers_admin
    payment_delivery = (ROOT / "payment_delivery.py").read_text(encoding="utf-8")
    assert 'if order["lootbox_type_id"]:' in payment_delivery
    assert "db.approve_lootbox_order(order_id)" in payment_delivery
    assert "notify_lootbox_delivered(" in payment_delivery
    assert '"lootbox_type_id" in keys and order["lootbox_type_id"]' in (
        ROOT / "extra_gateway_user.py").read_text(encoding="utf-8")

    # Schema, settings and ledger labels the feature needs to function at all.
    db_base = (ROOT / "db/_base.py").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS leak_candidates" in db_base
    assert "CREATE TABLE IF NOT EXISTS leak_queries" in db_base
    assert '("orders", "lootbox_type_id", "INTEGER")' in db_base
    db_constants = (ROOT / "db/constants.py").read_text(encoding="utf-8")
    assert '"acct_show_lootbox"' in db_constants
    assert '"acct_lootbox": {"label"' in db_constants
    assert '"acct_orders", "acct_tutorial", "acct_referral", "acct_wallet", "acct_lootbox"' in db_constants
    db_orders = (ROOT / "db/orders.py").read_text(encoding="utf-8")
    for needle in ('"season_prize"', '"lootbox_buy"', '"milestone_prize"'):
        assert needle in db_orders, f"db/orders.py lost {needle}"

    keyboards = (ROOT / "keyboards.py").read_text(encoding="utf-8")
    assert "def user_group_stats_kb(" in keyboards
    assert '"acct_lootbox": ("acct_show_lootbox", "lb_menu")' in keyboards
    assert '("adm_season_quiz"' in keyboards
    assert '("adm_engage"' in keyboards
    assert '"wal_progress"' in keyboards

    # Mini app: the season endpoint feeds the season card in the account page.
    miniapp = (ROOT / "miniapp/server.py").read_text(encoding="utf-8")
    assert '@app.get("/api/season")' in miniapp
    assert "season_logic.enabled(db)" in miniapp
    assert "db.season_standings(" in miniapp
    app_js = (ROOT / "miniapp/static/app.js").read_text(encoding="utf-8")
    assert "/api/season" in app_js
    assert "function seasonCard(" in app_js


def test_leak_discovery_stays_wired():
    """Upstream's smart channel discovery must keep its crawler, store and admin UI."""
    leak_discovery = (ROOT / "leak_discovery.py").read_text(encoding="utf-8")
    for needle in ("class Discovery", "def message_text(", "def collect_refs(", "KEY_ENABLED"):
        assert needle in leak_discovery, f"leak_discovery.py lost {needle!r}"

    leak_scanner = (ROOT / "leak_scanner.py").read_text(encoding="utf-8")
    assert "import leak_discovery as ld" in leak_scanner
    assert "def install_realtime(" in leak_scanner
    assert "async def run_dedicated(" in leak_scanner
    assert "ld.Discovery(" in leak_scanner
    assert "events.MessageEdited" in leak_scanner  # edited posts are re-scanned

    main_py = (ROOT / "main.py").read_text(encoding="utf-8")
    assert "import leak_scanner" in main_py
    assert "leak_scanner.run_dedicated(main_db, BOT_TOKEN)" in main_py

    db_leak_store = (ROOT / "db/leak_store.py").read_text(encoding="utf-8")
    for needle in (
        "def upsert_leak_candidate(",
        "def ensure_leak_queries(",
        "def list_prunable_leak_channels(",
        "def record_leak_query_run(",
    ):
        assert needle in db_leak_store, f"db/leak_store.py lost {needle!r}"

    leak_admin = (ROOT / "leak_admin.py").read_text(encoding="utf-8")
    assert "import leak_discovery as ld" in leak_admin
    assert '"adm_leak_d"' in leak_admin
    assert "ld.KEY_ENABLED" in leak_admin  # the discovery settings menu

    # Review callbacks must survive the report-group ownership check.
    report_router = (ROOT / "report_router.py").read_text(encoding="utf-8")
    assert '"lk:rot:", "lk:warn:", "lk:ign:",' in report_router
    assert '"adm_user_configs:",' in report_router


def test_ssh_nodes_and_shared_quota_stay_wired():
    """The merged SSH-node / shared-quota feature must stay reachable end to end.

    A node-agent module on disk does nothing unless an admin route can install
    or register a node, a paid product can provision against it, the quota
    worker runs at start-up, and the buyer can fetch the credentials.
    """
    # Start-up: one reconciler per database (main bot + every reseller tenant).
    main_py = (ROOT / "main.py").read_text(encoding="utf-8")
    assert "from quota_reconciler import QuotaReconciler" in main_py
    assert "QuotaReconciler(main_db).run_forever()" in main_py
    assert "QuotaReconciler(reseller_db).run_forever()" in main_py

    # DB layer: the mixin is part of Database and owns the tables/columns.
    db_init = (ROOT / "db/__init__.py").read_text(encoding="utf-8")
    assert "from .usage import UsageMixin" in db_init
    assert "UsageMixin," in db_init
    base = (ROOT / "db/_base.py").read_text(encoding="utf-8")
    for table in ("quota_pools", "quota_pool_members", "quota_pool_adjustments",
                  "quota_enforcement_state", "usage_snapshots", "ssh_nodes", "ssh_accounts"):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in base, f"{table} schema disappeared"
    assert '"products", "provision_ssh_node_id"' in base
    assert "provision_ssh_node_id=?" in (ROOT / "db/catalog.py").read_text(encoding="utf-8")

    # Provisioning: SSH-only and combined VPN+SSH products must reach a provider.
    provision = (ROOT / "direct_panel_provision.py").read_text(encoding="utf-8")
    assert "provision_ssh_direct(db, product" in provision
    assert "await _provision_combined(db, product" in provision
    assert "db.attach_custom_config_to_quota_pool(pool_id, cc_id)" in provision
    for module in ("handlers_admin.py", "handlers_user.py", "payment_delivery.py",
                   "miniapp/server.py", "admin_panel/server.py"):
        assert "provision_ssh_node_id" in (ROOT / module).read_text(encoding="utf-8"), (
            f"{module} no longer routes SSH products to provisioning"
        )

    # Buyer-facing delivery: /myssh reads the account row and the shared usage.
    handlers_user = (ROOT / "handlers_user.py").read_text(encoding="utf-8")
    assert 'Command("myssh")' in handlers_user
    assert "db.list_ssh_accounts" in handlers_user
    assert "db.get_quota_usage" in handlers_user

    # Admin panel: routes the UI calls, plus the two SSH screens themselves.
    server = (ROOT / "admin_panel/server.py").read_text(encoding="utf-8")
    for route in ("/api/ssh/nodes-lite", "/api/ssh/install-package", "/api/ssh/overview",
                  "/api/ssh/nodes/auto-install", "/api/ssh/pools", "/api/ssh/accounts",
                  "/api/ssh/reconcile-once"):
        assert f'"{route}"' in server, f"{route} route disappeared"
    app_js = (ROOT / "admin_panel/static/app.js").read_text(encoding="utf-8")
    assert "renderSSHManagement" in app_js and "renderSSHInstall" in app_js
    assert "provision_ssh_node_id" in app_js

    # The agent ships with the installer that uploads it, or auto-install dies.
    installer = (ROOT / "ssh_auto_install.py").read_text(encoding="utf-8")
    for asset in ("ssh_node_agent.py", "deploy/install-shopvpn-ssh-agent.sh",
                  "deploy/shopvpn-ssh-agent.service", "deploy/shopvpn-sshd@.service"):
        assert asset in installer, f"{asset} is no longer uploaded by the installer"
        path = ROOT / asset
        assert path.is_file() and path.stat().st_size > 0, f"{asset} is missing"

    # ssh:// configs must stay recognisable as subscriptions.
    assert '"ssh://"' in (ROOT / "sub_info.py").read_text(encoding="utf-8")

    # The SSH password key is generated next to the project at runtime.
    assert ".ssh_credential_key" in (ROOT / ".gitignore").read_text(encoding="utf-8")


def test_rejected_upstream_paths_stay_out():
    """Upstream re-uploads its own install scripts, docs and a root-level test on
    every push. Those were rejected on purpose, so they must not creep back in."""
    assert not (ROOT / "test_leak_discovery.py").exists(), "upstream's root test came back"
    assert not (ROOT / "_.gitignore.txt").exists(), "upstream's gitignore dump came back"
    assert not (ROOT / "deploy/Test").exists(), "upstream's empty deploy/Test file came back"

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Config Leak Detection & Smart Discovery" not in readme, (
        "an upstream README section replaced the fork's documentation"
    )

    manage = (ROOT / "manage.sh").read_text(encoding="utf-8")
    assert "telegram_accounts_menu()" not in manage, "upstream's manage.sh menu came back"
    extra = (ROOT / "manage_extra_cli.sh").read_text(encoding="utf-8")
    assert "setup_web_store()" in extra
    assert "setup_dedicated_sub()" in extra
    assert "telegram_accounts_menu()" not in extra
    assert "menu_item 33 menu_33" in manage
    assert "manage_extra_cli.sh" in manage
    assert "32) doctor; pause ;;" in manage
    # …while the fork's own service helpers are still there.
    assert "wait_for_service_ready()" in manage
    assert "restart_service_and_wait()" in manage

    # Telegram session files hold live credentials and must never be committable.
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "userbot_session.json" in gitignore
    assert "leak_session.json" in gitignore


def test_dedicated_sub_web_store_and_updater_stay_wired():
    """Dedicated subscription, website auth/store, and updater must stay reachable."""
    handlers_admin = (ROOT / "handlers_admin.py").read_text(encoding="utf-8")
    assert "import admin_dedicated_sub" in handlers_admin
    assert "import admin_update" in handlers_admin
    assert "admin_dedicated_sub.register(router, db, senior_admin_only, deny_mid, replace_admin_view)" in handlers_admin
    assert "admin_update.register(router, db, senior_admin_only, deny_mid, replace_admin_view)" in handlers_admin

    handlers_user = (ROOT / "handlers_user.py").read_text(encoding="utf-8")
    assert "import web_auth" in handlers_user
    assert "import dedicated_sub" in handlers_user
    assert "web_auth.confirm_login" in handlers_user
    assert "dedicated_sub.dedicated_link_for_upstream" in handlers_user

    bot_manager = (ROOT / "bot_manager.py").read_text(encoding="utf-8")
    assert "import updater" in bot_manager
    assert "updater.check_loop(bot, db)" in bot_manager

    config_delivery = (ROOT / "config_delivery.py").read_text(encoding="utf-8")
    assert "import dedicated_sub" in config_delivery
    assert "dedicated_sub.dedicated_link_for_upstream" in config_delivery

    db_init = (ROOT / "db/__init__.py").read_text(encoding="utf-8")
    assert "from .dedicated_sub import DedicatedSubMixin" in db_init

    miniapp = (ROOT / "miniapp/server.py").read_text(encoding="utf-8")
    assert "import web_auth" in miniapp
    assert "import dedicated_sub" in miniapp
    assert "web_auth.session_user" in miniapp

    admin_panel = (ROOT / "admin_panel/server.py").read_text(encoding="utf-8")
    assert "import dedicated_sub as ds" in admin_panel
    assert "api_web_store_preview_url" in admin_panel

    sub_server = (ROOT / "sub_server/server.py").read_text(encoding="utf-8")
    assert "import dedicated_sub as ds" in sub_server
    web_store = (ROOT / "web_store/server.py").read_text(encoding="utf-8")
    assert "from web_store.routes import router as web_router" in web_store

    updater_src = (ROOT / "updater.py").read_text(encoding="utf-8")
    assert 'FORK_GITHUB_OWNER = "amir12120"' in updater_src
    assert 'UPSTREAM_GITHUB_OWNER = "mehdirafatpanah"' in updater_src
    assert 'os.getenv("SHOPVPN_UPDATE_OWNER", "mehdirafatpanah")' not in updater_src
    assert 'raw.githubusercontent.com/{REPO_OWNER}' in updater_src


def test_project_update_runner_stays_next_to_the_bot():
    """The in-bot project updater shells out to ``update_runner.sh``.

    An upstream merge once dropped that file while ``updater.py`` kept calling
    it, so the admin panel's "update project" button always answered
    "فایل update_runner.sh کنار پروژه پیدا نشد" (installer not found). The file
    must exist, must deploy this fork's repo, and must keep its safety net.
    """
    runner = ROOT / "update_runner.sh"
    assert runner.is_file(), (
        "update_runner.sh is missing; the in-bot update button will fail with "
        "'installer not found'"
    )
    src = runner.read_text(encoding="utf-8")
    assert src.strip(), "update_runner.sh is empty"
    for needle in (
        'MODE="${1:-update}"',       # updater.py passes update/rollback as $1
        "REPO_OWNER",                 # archive fallback target
        "git fetch",                  # normal fast-forward path
        "code_before_update_",        # code snapshot for rollback
        '"$SNAP.head"',               # commit that matches the code snapshot
        "LAST_HEAD",                  # manual rollback pins that commit
        "db_before_update_",          # database snapshot for rollback
        "NR_BEFORE",                  # auto-restart baseline (no false rollback)
        "restart_all",                # restarts the bot service last
        "write_result ok",            # updater.py reads update_result.txt
    ):
        assert needle in src, f"update_runner.sh lost its {needle!r} step"

    # The runner must never fall back to the upstream owner by default.
    assert "mehdirafatpanah" not in src
    assert '"${REPO_OWNER:-amir12120}"' in src

    updater_src = (ROOT / "updater.py").read_text(encoding="utf-8")
    assert 'RUNNER = os.path.join(BASE_DIR, "update_runner.sh")' in updater_src
    assert "os.path.isfile(RUNNER)" in updater_src


def test_storefront_network_map_stays_wired():
    """The live network map is a storefront feature, not a dead asset.

    It must be loaded on the home page, served as a static asset, and backed by
    the same server-side world-map cache the admin dashboard uses.
    """
    js = ROOT / "web_store/static/assets/network-map.js"
    css = ROOT / "web_store/static/assets/network-map.css"
    assert js.is_file() and js.stat().st_size > 10000
    assert css.is_file() and css.stat().st_size > 5000
    assert "window.ShopVPNNetworkMap" in js.read_text(encoding="utf-8")

    index = (ROOT / "web_store/static/index.html").read_text(encoding="utf-8")
    assert "/assets/network-map.css" in index
    assert "/assets/network-map.js" in index

    app_js = (ROOT / "web_store/static/assets/app.js").read_text(encoding="utf-8")
    assert "window.ShopVPNNetworkMap.create" in app_js

    routes = (ROOT / "web_store/routes.py").read_text(encoding="utf-8")
    assert '@router.get("/api/web/world-map")' in routes
    assert "world_map.get_world_map()" in routes


def test_product_targets_capabilities_resync_and_renewal_rules_are_wired():
    """Upstream's product targets, panel capabilities, panel resync and per-product
    renewal rules must stay reachable from the bot, the admin panel and the mini app.
    File existence alone is not enough: each module needs a real caller."""
    handlers_admin = (ROOT / "handlers_admin.py").read_text(encoding="utf-8")
    assert "import renewal_rules" in handlers_admin
    assert "import admin_extra_settings" in handlers_admin
    assert "admin_extra_settings.register(router, db" in handlers_admin
    assert "from product_targets import build_target_config" in handlers_admin
    assert "from panel_capabilities import all_panels_support" in handlers_admin

    # Capability source of truth replaced the per-module provider lookups.
    user_limit = (ROOT / "user_limit.py").read_text(encoding="utf-8")
    assert "from panel_capabilities import product_capabilities" in user_limit
    provision = (ROOT / "direct_panel_provision.py").read_text(encoding="utf-8")
    assert "panel_capabilities" in provision
    # The startup repair keeps older products in sync with real panel capabilities.
    base = (ROOT / "db/_base.py").read_text(encoding="utf-8")
    assert "repair_product_capabilities()" in base
    assert "ADD COLUMN target_config TEXT" in base

    # Product-scoped destinations are exposed by both web surfaces.
    admin_panel = (ROOT / "admin_panel/server.py").read_text(encoding="utf-8")
    assert '@app.get("/api/panel-servers/{server_id}/product-targets")' in admin_panel
    assert "from product_targets import list_product_targets" in admin_panel
    miniapp = (ROOT / "miniapp/server.py").read_text(encoding="utf-8")
    assert '/api/admin/panel-servers/{server_id}/product-targets' in miniapp
    assert "build_target_config" in miniapp
    assert "from panel_capabilities import all_panels_support" in miniapp

    # Panel resync repairs configs that lost their template/groups on the panel.
    sub_server = (ROOT / "sub_server/server.py").read_text(encoding="utf-8")
    assert "import panel_resync" in sub_server
    assert "panel_resync.heal_config(db, cc)" in sub_server

    # Per-product renewal rules reach the DB, the bot menu and the web forms.
    catalog = (ROOT / "db/catalog.py").read_text(encoding="utf-8")
    assert "from renewal_rules import normalize, RULE_KEYS" in catalog
    handlers_user = (ROOT / "handlers_user.py").read_text(encoding="utf-8")
    assert "renewal_rules.filter_products(" in handlers_user
    assert "renewal_rules.order_flags(" in handlers_user
    keyboards = (ROOT / "keyboards.py").read_text(encoding="utf-8")
    assert "def admin_renew_rules_kb(" in keyboards
    assert '"adm_prodrr:' in keyboards
    assert "waiting_renew_rules = State()" in (ROOT / "states.py").read_text(encoding="utf-8")
    assert "renew_rules: Optional[dict] = None" in admin_panel

    # The bot's extra-settings editor drives the same schema as web and mini app.
    assert 'SURFACE = "bot"' in (ROOT / "admin_extra_settings.py").read_text(encoding="utf-8")
    schema = (ROOT / "extra_settings_schema.py").read_text(encoding="utf-8")
    assert '"bot": True' in schema

    # check_settings_sync.py demands the two settings_schema.py copies stay identical.
    assert (ROOT / "settings_schema.py").read_text(encoding="utf-8") == (
        ROOT / "admin_panel/static/settings_schema.py").read_text(encoding="utf-8")


def test_wui_panel_migration_and_multi_cards_are_wired():
    """Upstream 9298ad8: W-UI panel type, user migration between panels, several
    card-to-card cards with weighted display, and the W-UI dedicated-sub page.

    The upstream upload also re-added a 9k-line root ``app.js`` duplicate and a
    Persian "what we merged" note; the fork keeps neither, and the merge must not
    silently bring back the upload duplicates.
    """
    providers = (ROOT / "panel_providers/__init__.py").read_text(encoding="utf-8")
    assert "from .wui_provider import WUIProvider" in providers
    assert '"wui": WUIProvider' in providers
    assert '"wui": "W-UI"' in providers
    template_line = next(
        line for line in providers.splitlines() if line.startswith("TEMPLATE_BASED_PANEL_TYPES = ")
    )
    assert '"wui"' in template_line, "W-UI templates come from an existing customer"
    wui = (ROOT / "panel_providers/wui_provider.py").read_text(encoding="utf-8")
    for method in ("def get_config_files(", "def get_sub_info(", "def get_login_profiles("):
        assert method in wui, f"W-UI provider lost {method.strip()}"

    # Migration is reachable from the bot and its history tables are part of the DB.
    assert "PanelMigrationMixin" in (ROOT / "db/__init__.py").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS panel_migrations" in (
        ROOT / "db/panel_migration.py").read_text(encoding="utf-8")
    handlers_admin = (ROOT / "handlers_admin.py").read_text(encoding="utf-8")
    assert "import admin_panel_migration" in handlers_admin
    assert "admin_panel_migration.register(router, db, senior_admin_only, deny_mid, replace_admin_view)" in handlers_admin
    assert "async def run_migration(" in (ROOT / "panel_migration.py").read_text(encoding="utf-8")

    # Several manual card numbers with weights, and receipt matching that sees them.
    base = (ROOT / "db/_base.py").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS payment_cards" in base
    assert "CREATE TABLE IF NOT EXISTS payment_card_assignments" in base
    assert "def get_manual_card_for_user(" in (ROOT / "db/payments.py").read_text(encoding="utf-8")
    assert "payment_cards" in (ROOT / "db/orders.py").read_text(encoding="utf-8")
    assert '@router.callback_query(F.data == "adm_pcards")' in handlers_admin
    assert "def payment_cards_kb(" in (ROOT / "keyboards.py").read_text(encoding="utf-8")
    assert "class AdminPayCard(StatesGroup)" in (ROOT / "states.py").read_text(encoding="utf-8")

    # W-UI subscribers get their WireGuard/OpenVPN files and login profiles in the
    # dedicated sub page; secrets are fetched per item, never rendered into HTML.
    assert "def vpn_secret(" in (ROOT / "dedicated_sub.py").read_text(encoding="utf-8")
    assert "def vpn_items_for_page(" in (ROOT / "dedicated_sub.py").read_text(encoding="utf-8")
    assert "def wui_dsub_warning(" in (ROOT / "dedicated_sub.py").read_text(encoding="utf-8")
    sub_server = (ROOT / "sub_server/server.py").read_text(encoding="utf-8")
    assert "async def _wui_bundle(" in sub_server
    assert "connect-src 'self'" in sub_server
    assert "provider.get_login_profiles(" in sub_server

    # The fork does not resurrect upstream's upload duplicates.
    assert not (ROOT / "app.js").exists(), "the 9k-line root app.js upload duplicate came back"


def test_cron_welcome_gift_emoji_and_stealth_are_wired():
    """The 4.25.0 upstream batch must stay reachable, not just present on disk.

    File existence is not wiring: each of these modules has to be imported and
    actually reached from a loop, a handler, a route or a DB path.
    """
    bot_manager = (ROOT / "bot_manager.py").read_text(encoding="utf-8")
    # hourly system cron and the signup config gift both run as real tasks
    assert "from cron_checks import cron_loop" in bot_manager
    assert "from welcome_gift import welcome_gift_loop" in bot_manager
    assert "asyncio.create_task(cron_loop(bot, db))" in bot_manager
    assert "asyncio.create_task(welcome_gift_loop(bot, db))" in bot_manager
    assert '"cron_task": cron_task' in bot_manager
    assert '"welcome_gift_task": welcome_gift_task' in bot_manager
    # ...and both are stopped with the rest of the tasks
    assert '"cron_task", "daily_report_task"' in bot_manager
    assert '"signup_gift_task", "welcome_gift_task"' in bot_manager

    # the cron state is exposed to the web panel, and can be triggered from it
    server = (ROOT / "admin_panel/server.py").read_text(encoding="utf-8")
    assert '@app.get("/api/cron/status")' in server
    assert '@app.post("/api/cron/run")' in server
    assert "import cron_checks" in server
    assert "cron_checks.load_state(db)" in server
    assert "cron_checks.request_run(db)" in server

    # the gift queue is a real table with real DB methods
    base = (ROOT / "db/_base.py").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS welcome_gift_queue" in base
    system = (ROOT / "db/system.py").read_text(encoding="utf-8")
    for method in ("enqueue_welcome_gift", "claim_due_welcome_gifts", "save_welcome_gift_result",
                   "retry_welcome_gift_delivery", "finish_welcome_gift", "retry_or_fail_welcome_gift",
                   "welcome_gift_stats", "get_welcome_gift_status"):
        assert f"def {method}(" in system, f"welcome gift DB method {method} is missing"
    # settings the gift loop reads must exist as defaults
    constants = (ROOT / "db/constants.py").read_text(encoding="utf-8")
    for key in ("welcome_gift_enabled", "welcome_gift_product_id", "welcome_gift_delay_minutes"):
        assert f'"{key}"' in constants, f"default setting {key} is missing"

    # the gift is reachable from the bot: admin editor + user claim button
    handlers_admin = (ROOT / "handlers_admin.py").read_text(encoding="utf-8")
    assert '@router.callback_query(F.data == "adm_welcome_gift")' in handlers_admin
    assert '@router.callback_query(F.data == "adm_wgift_toggle")' in handlers_admin
    handlers_user = (ROOT / "handlers_user.py").read_text(encoding="utf-8")
    assert '@router.callback_query(F.data == "welcome_gift_claim")' in handlers_user
    assert "class AdminWelcomeGift(StatesGroup)" in (ROOT / "states.py").read_text(encoding="utf-8")

    # configurable emojis: module -> admin menu -> keyboards -> category rows
    assert "import emoji_prefs" in handlers_admin
    assert '@router.callback_query(F.data == "adm_emoji_menu")' in handlers_admin
    keyboards = (ROOT / "keyboards.py").read_text(encoding="utf-8")
    assert "def admin_emoji_menu_kb(" in keyboards
    catalog = (ROOT / "db/catalog.py").read_text(encoding="utf-8")
    assert "def set_category_emoji(" in catalog
    for key in ("emoji_product_in_stock", "emoji_category", "emoji_test_plan"):
        assert f'"{key}"' in constants, f"emoji default {key} is missing"

    # Stealth VLESS is a registered provider type, token-only and setup-free
    providers = (ROOT / "panel_providers/__init__.py").read_text(encoding="utf-8")
    assert "from .stealth_provider import StealthProvider" in providers
    assert '"stealth": StealthProvider' in providers
    assert '"stealth": "stealth"' in providers
    assert 'NO_SETUP_PANEL_TYPES = {"stealth"}' in providers
    assert '"stealth": "Stealth VLESS"' in providers
    # the web panel honours the no-setup list and offers the auto-install route
    assert "NO_SETUP_PANEL_TYPES" in server
    assert '@app.post("/api/stealth/nodes/auto-install")' in server
    assert '@app.get("/api/stealth/nodes/install-jobs/{job_id}")' in server
    # the module upstream forgot to ship exists and exposes the same contract
    stealth = (ROOT / "stealth_auto_install.py").read_text(encoding="utf-8")
    assert "class InstallError(Exception)" in stealth
    assert "def start_install(" in stealth
    assert "def get_job(" in stealth
    # the installer and agent it uploads are shipped with the fork
    assert (ROOT / "deploy/install-shopvpn-stealth.py").exists()
    assert (ROOT / "deploy/shopvpn-stealth-agent.py").exists()

    # the web DB manager is owner-only and audited
    for route in ("/api/database/tables", "/api/database/table/{table_name}",
                  "/api/database/schema/{table_name}", "/api/database/backup",
                  "/api/database/audit"):
        assert f'@app.get("{route}")' in server, f"DB manager route {route} is missing"
    assert "require_owner" in server
    assert "_shopvpn_db_audit" in server


def test_per_user_test_limit_and_config_search_are_wired():
    """The per-user test cap and the config search/manage flow must reach the UI."""
    system = (ROOT / "db/system.py").read_text(encoding="utf-8")
    assert "def get_effective_test_limit(" in system
    assert "def set_user_test_limit_override(" in system
    # the AI support tool must honour the per-user cap, not the global constant
    ai_support = (ROOT / "ai_support.py").read_text(encoding="utf-8")
    assert "db.get_effective_test_limit(user_tg_id)" in ai_support
    assert "test_max_per_user" in (ROOT / "db/constants.py").read_text(encoding="utf-8")

    handlers_admin = (ROOT / "handlers_admin.py").read_text(encoding="utf-8")
    assert '@router.callback_query(F.data.startswith("adm_user_test_limit:"))' in handlers_admin
    assert '@router.callback_query(F.data == "adm_cfg_search")' in handlers_admin
    states = (ROOT / "states.py").read_text(encoding="utf-8")
    assert "class AdminUserTestLimit(StatesGroup)" in states
    assert "class AdminConfigSearch(StatesGroup)" in states

    dedicated = (ROOT / "db/dedicated_sub.py").read_text(encoding="utf-8")
    assert "def search_custom_configs(" in dedicated
    assert "def search_bank_configs(" in dedicated
    keyboards = (ROOT / "keyboards.py").read_text(encoding="utf-8")
    assert "def admin_cfg_search_results_kb(" in keyboards
    assert "def admin_cfg_danger_confirm_kb(" in keyboards


def test_admin_hub_layout_and_search_are_wired():
    """The sectioned admin hub and the settings search must stay reachable."""
    keyboards = (ROOT / "keyboards.py").read_text(encoding="utf-8")
    assert "ADMIN_HUB_SECTIONS" in keyboards
    assert "def resolve_admin_category(" in keyboards
    assert "def admin_hub_text(" in keyboards
    assert "def admin_search_results(" in keyboards
    # exactly one definition: upstream re-uploads a duplicate that shadows the first
    assert keyboards.count("def blupal_settings_kb(") == 1, (
        "duplicate blupal_settings_kb definition came back from upstream"
    )
    handlers_admin = (ROOT / "handlers_admin.py").read_text(encoding="utf-8")
    assert '@router.callback_query(F.data.startswith("adm_hub:"))' in handlers_admin
    assert '@router.callback_query(F.data == "adm_search")' in handlers_admin
    assert "@router.message(AdminPanelSearch.waiting_query)" in handlers_admin
    assert "class AdminPanelSearch(StatesGroup)" in (ROOT / "states.py").read_text(encoding="utf-8")
    admin_help = (ROOT / "admin_help.py").read_text(encoding="utf-8")
    assert "def hub_for_back(" in admin_help
    assert "def track(" in admin_help
    # the fork's reseller-section toggle survives the new hub routing
    assert "reseller_section.TOGGLE_CALLBACK" in handlers_admin
    assert "adm_reseller_section_toggle" in keyboards


def test_broadcast_targeting_and_product_layout_are_wired():
    """Broadcast targeting, config management and the product layout toggle."""
    users = (ROOT / "db/users.py").read_text(encoding="utf-8")
    assert "def get_user_ids_by_service_state(" in users
    handlers_admin = (ROOT / "handlers_admin.py").read_text(encoding="utf-8")
    for cb in ("adm_broadcast_adv", "adm_broadcast_fwd", "adm_broadcast_status",
               "adm_broadcast_stop", "adm_broadcast_single", "adm_broadcast_channel"):
        assert f'F.data == "{cb}"' in handlers_admin, f"broadcast callback {cb} is missing"
    assert '@router.callback_query(F.data.startswith("adm_broadcast_target:"))' in handlers_admin
    assert '@router.message(Command("pin"))' in handlers_admin
    assert '@router.message(Command("unpin"))' in handlers_admin
    assert "def admin_broadcast_advanced_kb(" in (ROOT / "keyboards.py").read_text(encoding="utf-8")

    constants = (ROOT / "db/constants.py").read_text(encoding="utf-8")
    for key in ("buy_product_layout", "buy_product_order", "btn_subcat_select_style"):
        assert f'"{key}"' in constants, f"layout setting {key} is missing"
    assert '@router.callback_query(F.data == "adm_buyflow_layout_toggle")' in handlers_admin
    assert '@router.callback_query(F.data == "adm_buyflow_order_toggle")' in handlers_admin

    # test plans are provisioned through the product path, not the legacy one
    tcp = (ROOT / "test_config_provision.py").read_text(encoding="utf-8")
    assert "def plan_to_product(" in tcp
    assert "direct_panel_provision.provision_direct(" in tcp
    assert "async def _provision_like_product(" in tcp


def test_stealth_install_scripts_do_not_touch_the_fork_install_flow():
    """The Stealth node scripts are standalone; the lean install flow is untouched."""
    for name in ("install.sh", "manage.sh", "update.sh", "preflight.sh", "cleanup.sh",
                 "setup_local_translation.sh", "check_upstream.sh"):
        text = (ROOT / name).read_text(encoding="utf-8", errors="replace")
        assert "shopvpn-stealth" not in text, f"{name} must not reference the Stealth node scripts"
        assert "stealth_auto_install" not in text, f"{name} must not reference stealth_auto_install"
    # cleanup.sh still sweeps the heavy caches after an install
    cleanup = (ROOT / "cleanup.sh").read_text(encoding="utf-8")
    assert "while IFS= read -r h" in cleanup
    assert "journalctl --vacuum-size=" in cleanup
    assert "SHOPVPN_JOURNAL_MAX" in cleanup


def test_phone_gate_user_groups_and_subscriptions_are_wired():
    """Upstream 9.1.0 features must be reachable, not just present as files."""
    phone_gate = (ROOT / "phone_gate.py").read_text(encoding="utf-8")
    assert "class PhoneGateMiddleware" in phone_gate
    assert "def is_enabled(" in phone_gate
    assert "def match_country(" in phone_gate
    assert "def describe_allowed(" in phone_gate
    bot_manager = (ROOT / "bot_manager.py").read_text(encoding="utf-8")
    assert "from phone_gate import PhoneGateMiddleware" in bot_manager
    assert "PhoneGateMiddleware(db)" in bot_manager
    assert "outer_middleware(" in bot_manager
    miniapp = (ROOT / "miniapp/server.py").read_text(encoding="utf-8")
    assert "import phone_gate" in miniapp
    assert '@app.get("/api/phone/status")' in miniapp
    assert '@app.post("/api/phone/request")' in miniapp
    handlers_user = (ROOT / "handlers_user.py").read_text(encoding="utf-8")
    assert "import phone_gate" in handlers_user
    assert "def phone_gate_contact(" in handlers_user

    db_init = (ROOT / "db/__init__.py").read_text(encoding="utf-8")
    assert "from .user_groups import UserGroupsMixin" in db_init
    assert "from .subscriptions import SubscriptionsMixin" in db_init
    user_groups = (ROOT / "db/user_groups.py").read_text(encoding="utf-8")
    assert "class UserGroupsMixin" in user_groups
    assert "def list_user_groups(" in user_groups
    subscriptions = (ROOT / "db/subscriptions.py").read_text(encoding="utf-8")
    assert "def search_subscriptions(" in subscriptions

    server = (ROOT / "admin_panel/server.py").read_text(encoding="utf-8")
    for route in ('@app.get("/api/subscriptions")',
                  '@app.post("/api/subscriptions/ssh/{account_id}/action")',
                  '@app.get("/api/user-groups")',
                  '@app.post("/api/user-groups")'):
        assert route in server, f"missing upstream route {route}"
    constants = (ROOT / "db/constants.py").read_text(encoding="utf-8")
    assert "DEFAULT_AUTO_BANNERS" in constants
    app_js = (ROOT / "admin_panel/static/app.js").read_text(encoding="utf-8")
    assert "stealthNodeSettingsModal" in app_js
    assert "function renderSSHInstall()" in app_js  # fork's SSH install page survived


def test_custom_menu_accounting_home_tiles_and_web_2fa_are_wired():
    """9.4.0 batch: every new module is reachable from a real entry point."""
    # Custom glass-menu buttons: admin editor -> DB -> inline keyboard -> mini app click.
    handlers_admin = (ROOT / "handlers_admin.py").read_text(encoding="utf-8")
    assert "import custom_menu_buttons" in handlers_admin
    assert "custom_menu_buttons.register(" in handlers_admin
    db_init = (ROOT / "db/__init__.py").read_text(encoding="utf-8")
    assert "from .custom_menu import CustomMenuMixin" in db_init
    assert "CustomMenuMixin," in db_init
    base = (ROOT / "db/_base.py").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS custom_menu_buttons" in base
    custom_menu = (ROOT / "db/custom_menu.py").read_text(encoding="utf-8")
    for method in ("def cm_list(", "def cm_create(", "def cm_delete(", "def cm_add_click("):
        assert method in custom_menu, f"custom menu lost {method}"
    keyboards = (ROOT / "keyboards.py").read_text(encoding="utf-8")
    assert "def custom_menu_button(" in keyboards
    orders_db = (ROOT / "db/orders.py").read_text(encoding="utf-8")
    assert "custom_menu:" in orders_db  # the custom keys survive menu reordering

    # Mini-app: custom button click, home tiles and home icons all hit the DB.
    miniapp = (ROOT / "miniapp/server.py").read_text(encoding="utf-8")
    assert "import home_tiles" in miniapp
    assert "home_tiles.tile_rows(" in miniapp
    assert "def api_custom_button_click(" in miniapp
    assert "def api_home_config(" in miniapp
    assert "def api_admin_save_home_icons(" in miniapp
    assert "def api_support_state(" in miniapp
    assert "def api_reopen_my_ticket(" in miniapp
    system_db = (ROOT / "db/system.py").read_text(encoding="utf-8")
    assert "def get_home_icons(" in system_db and "def set_home_icons(" in system_db

    # Tickets/live chat: priority, service reference and reopen reachable from bot + web.
    tickets_db = (ROOT / "db/tickets.py").read_text(encoding="utf-8")
    assert "def normalize_priority(" in tickets_db
    assert "def set_ticket_priority(" in tickets_db
    assert "def reopen_ticket(" in tickets_db
    assert "def set_support_reference(" in tickets_db
    assert '("tickets", "priority", ' in base or "tickets\", \"priority\"" in base
    handlers_user = (ROOT / "handlers_user.py").read_text(encoding="utf-8")
    assert "db.reopen_ticket" in handlers_user
    assert "kb.ticket_services_kb(" in handlers_user
    assert "def ticket_services_kb(" in keyboards
    schema = (ROOT / "extra_settings_schema.py").read_text(encoding="utf-8")
    assert "tickets_default_sort" in schema and "support_default_sort" in schema

    # Accounting formulas back the PayG panel-cost endpoints.
    server = (ROOT / "admin_panel/server.py").read_text(encoding="utf-8")
    assert "import accounting" in server
    assert '@app.get("/api/accounting/panel-costs")' in server
    accounting = (ROOT / "accounting.py").read_text(encoding="utf-8")
    assert "def panel_costs(" in accounting
    assert "def evaluate(" in accounting  # the formula engine behind every price
    assert "def suggest(" in accounting

    # Web assistant: chat/tab navigation/confirmed actions behind the panel API.
    assert "import web_assistant" in server
    assert "web_assistant.chat(" in server
    assert "web_assistant.take_pending(" in server
    assert "def chat(" in (ROOT / "web_assistant.py").read_text(encoding="utf-8")

    # Web-admin 2FA: TOTP primitives stored on web_admins and enforced on login.
    security = (ROOT / "admin_panel/security.py").read_text(encoding="utf-8")
    assert "def generate_totp_secret(" in security
    assert "def verify_totp(" in security
    assert "def refresh_session_token(" in security
    assert "verify_totp(" in server
    assert "refresh_session_token(" in server
    assert "def set_web_admin_totp_pending(" in system_db
    assert "def consume_web_admin_backup_code(" in system_db
    # Upstream 9.6.0: hidden web-panel entry path (gate + CLI behind it).
    assert "import web_entry_gate" in server
    assert '@app.get("/api/security/entry-path")' in server
    assert '@app.post("/api/security/entry-path")' in server
    gate = (ROOT / "web_entry_gate.py").read_text(encoding="utf-8")
    assert "def validate_slug(" in gate
    assert "def with_entry_path(" in gate
    entry_cli = (ROOT / "admin_panel/entry_path_cli.py").read_text(encoding="utf-8")
    assert "web_entry_gate" in entry_cli and "--set" in entry_cli
    assert "import web_entry_gate" in (ROOT / "admin_links.py").read_text(encoding="utf-8")

    # Central slash-command registry drives set_my_commands for users and admins.
    bot_manager = (ROOT / "bot_manager.py").read_text(encoding="utf-8")
    assert "import bot_commands" in bot_manager
    assert "bot_commands.schedule_sync(" in bot_manager
    commands = (ROOT / "bot_commands.py").read_text(encoding="utf-8")
    assert "def schedule_sync(" in commands
    assert "USER_COMMANDS" in commands and "ADMIN_COMMANDS" in commands
    assert "BotCommandScopeChat" in commands

    # Accounting ledger: entries CRUD + summary/CSV behind the web panel API.
    assert '@app.post("/api/accounting/ledger/entries")' in server
    assert '@app.get("/api/accounting/ledger/summary")' in server
    assert "def ledger_summary(" in accounting
    assert "def export_ledger_csv(" in accounting
    assert "def create_ledger_entry(" in accounting

    # Web-store customization + maintenance page, both without a heavy dependency.
    store_routes = (ROOT / "web_store/routes.py").read_text(encoding="utf-8")
    assert "from web_store import customize as wcustom" in store_routes
    store_server = (ROOT / "web_store/server.py").read_text(encoding="utf-8")
    assert "from web_store import maintenance_page" in store_server
    maint = (ROOT / "web_store/maintenance_page.py").read_text(encoding="utf-8")
    assert "from gear_svg import gear_path" in maint
    assert "def render(" in maint
    assert "def gear_path(" in (ROOT / "gear_svg.py").read_text(encoding="utf-8")
    custom = (ROOT / "web_store/customize.py").read_text(encoding="utf-8")
    assert "def safe_link(" in custom
    assert "def is_blocked_in_maintenance(" in custom
    assert "def build_custom_payload(" in custom
    assert "wcustom.build_custom_payload(" in store_routes
    assert "wcustom.is_blocked_in_maintenance(" in store_server

    # Web panel can notify users through the raw Bot API when it acts alone.
    assert "from admin_panel.telegram_notify import (" in server
    notify = (ROOT / "admin_panel/telegram_notify.py").read_text(encoding="utf-8")
    assert "async def copy_message(" in notify

    # Cleanup report: interval setting, one announcement per run, dry-run supported.
    cleanup = (ROOT / "cleanup_loop.py").read_text(encoding="utf-8")
    assert "def _cleanup_due(" in cleanup
    assert "def cleanup_once(" in cleanup
    assert "adm_cleanup_interval" in handlers_admin
    assert "adm_cleanup_report_toggle" in handlers_admin

    # Per-product start mode (purchase vs first connection).
    provision = (ROOT / "direct_panel_provision.py").read_text(encoding="utf-8")
    assert "def product_first_use(" in provision
    assert "start_on_first_use" in (ROOT / "db/_base.py").read_text(encoding="utf-8")
    assert "adm_prod_setstart" in handlers_admin

    # Ticket priority + group-topic ticket buttons are reachable from the bot.
    router = (ROOT / "report_router.py").read_text(encoding="utf-8")
    assert "def ticket_group_kb(" in router
    assert "def handle_group_ticket_callback(" in router
    assert "def notify_ticket_raw(" in router
    assert "def ticket_priority_buttons(" in keyboards
    assert "ticket_priority" in (ROOT / "db/tickets.py").read_text(encoding="utf-8")

def test_doctor_dns_and_source_offer_stay_wired():
    """Doctor DNS panel type and the license `/source` offer reach real code paths."""
    providers = (ROOT / "panel_providers/__init__.py").read_text(encoding="utf-8")
    assert "from .doctordns_provider import DoctorDNSProvider" in providers
    assert '"doctordns": DoctorDNSProvider' in providers
    assert '"doctordns": "doctordns"' in providers  # token-only, no template

    # The bot offers the panel type, and the panel type list matches the provider map.
    assert "adm_panel_type:doctordns" in (ROOT / "keyboards.py").read_text(encoding="utf-8")
    miniapp_js = (ROOT / "miniapp/static/app.js").read_text(encoding="utf-8")
    assert "doctordns" in miniapp_js
    admin_js = (ROOT / "admin_panel/static/app.js").read_text(encoding="utf-8")
    assert "'doctordns', 'Doctor DNS'" in admin_js

    # DNS addresses and WireGuard files are delivered through the dedicated-sub page
    # and through order delivery, not just declared in the provider.
    dedicated = (ROOT / "dedicated_sub.py").read_text(encoding="utf-8")
    assert "def dns_for_page(" in dedicated
    assert "DNS_DSUB_WARNING" in dedicated
    sub_server = (ROOT / "sub_server/server.py").read_text(encoding="utf-8")
    assert "async def _dns_bundle(" in sub_server
    assert "get_dns_bundle" in sub_server
    assert "get_dns_bundle" in (ROOT / "delivery_extras.py").read_text(encoding="utf-8")
    assert "dnssec" in (ROOT / "sub_server/sub_page.html").read_text(encoding="utf-8")

    # LICENSE section 6 source offer: bot command, mini app and web store routes.
    handlers_user = (ROOT / "handlers_user.py").read_text(encoding="utf-8")
    assert 'Command("source")' in handlers_user
    assert "source_offer.build_text" in handlers_user
    assert '"source"' in (ROOT / "bot_commands.py").read_text(encoding="utf-8")
    assert "/source" in (ROOT / "miniapp/server.py").read_text(encoding="utf-8")
    assert "/source" in (ROOT / "web_store/routes.py").read_text(encoding="utf-8")
    assert "SHOPVPN_SOURCE_URL" in (ROOT / "source_offer.py").read_text(encoding="utf-8")

    # The mini-app pinball game and the Glass Ops admin dashboard are real pages.
    assert (ROOT / "miniapp/static/pinball.js").stat().st_size > 10000
    assert "renderPinball" in miniapp_js
    assert "renderDashboardGlassOps" in admin_js

    # The new upstream tests live in tests/ so CI runs them.
    for name in ("test_doctordns_provider.py", "test_source_offer.py",
                 "test_reminder_renew_button.py", "test_dedicated_sub_multi.py"):
        assert (ROOT / "tests" / name).is_file(), f"{name} is missing from tests/"

    # The license this fork ships with is the source-available 1.0 one.
    assert "SOURCE-AVAILABLE" in (ROOT / "LICENSE").read_text(encoding="utf-8").upper()


def test_upstream_980_batch_is_wired_end_to_end():
    """Upstream 9.8.0 (fork 4.36.0): per-panel dedicated-sub switch, PayG minimum
    balance plus admin-defined delivery text/photo, accounting-priced service
    add-ons, report-topic backups, the Doctor DNS device limit and its one-time SSH
    bootstrap. Every edge is asserted so a later sync cannot leave it half-wired."""
    for relative in ("doctor_dns_ssh_setup.py", "tests/test_doctordns_ssh_setup.py",
                     "tests/test_accounting_service_addon.py"):
        path = ROOT / relative
        assert path.is_file(), f"{relative} is missing"
        assert path.stat().st_size > 0, f"{relative} is empty"

    admin_panel = (ROOT / "admin_panel/server.py").read_text(encoding="utf-8")
    admin_js = (ROOT / "admin_panel/static/app.js").read_text(encoding="utf-8")
    handlers_user = (ROOT / "handlers_user.py").read_text(encoding="utf-8")
    handlers_admin = (ROOT / "handlers_admin.py").read_text(encoding="utf-8")

    # Per-panel dedicated subscription: schema -> db -> gating -> panels UI.
    assert '("panel_servers", "dsub_enabled", "INTEGER DEFAULT 1")' in (ROOT / "db/_base.py").read_text(encoding="utf-8")
    assert '"dsub_enabled"' in (ROOT / "db/panels.py").read_text(encoding="utf-8")
    dedicated = (ROOT / "dedicated_sub.py").read_text(encoding="utf-8")
    for needle in ("def panel_enabled(", "def panels_dsub_off(",
                   "def panels_dsub_off_message(", "PANEL_DSUB_REQUIRED_TYPES"):
        assert needle in dedicated, f"dedicated_sub.py lost {needle}"
    assert "panel_enabled(db, panel_id)" in dedicated
    assert "panels_dsub_off_message" in (ROOT / "payg.py").read_text(encoding="utf-8")
    assert "panels_dsub_off_message" in (ROOT / "direct_panel_provision.py").read_text(encoding="utf-8")
    assert "panels_dsub_off_message" in (ROOT / "miniapp/server.py").read_text(encoding="utf-8")
    assert "panels_dsub_off_message" in admin_panel
    assert '"dsub_enabled"' in admin_panel
    assert "dsub_enabled: $('#pa-dsub', body).checked" in admin_js

    # PayG minimum balance and the admin-defined delivery message/photo.
    payg = (ROOT / "payg.py").read_text(encoding="utf-8")
    for needle in ("def get_min_balance(", "def get_usable_payg_panel_ids(",
                   "def render_delivery_text(", "async def send_delivery_message(",
                   "PAYG_MIN_BALANCE_KEY", "PAYG_DELIVERY_TEXT_KEY", "PAYG_DELIVERY_PHOTO_KEY"):
        assert needle in payg, f"payg.py lost {needle}"
    assert payg.count("send_delivery_message(call.message, db, default_text") >= 2
    for route in ('@app.post("/api/payg/delivery-photo")',
                  '@app.delete("/api/payg/delivery-photo")',
                  '@app.get("/api/payg/delivery-photo")'):
        assert route in admin_panel, f"admin panel lost {route}"
    assert "payg.get_min_balance(db)" in admin_panel
    assert 'id="payg-min-balance"' in admin_js and 'id="payg-delivery-text"' in admin_js
    assert "apiMultipart('/payg/delivery-photo'" in admin_js

    # Accounting-priced add-ons reach the bot's volume and user-count upgrade paths.
    assert "def suggest_service_addon(" in (ROOT / "accounting.py").read_text(encoding="utf-8")
    assert 'accounting.suggest_service_addon(db, item["custom"], amount, "gb")' in handlers_user
    assert 'accounting.suggest_service_addon(db, item["custom"], users - info["current"], "user")' in handlers_user
    assert "renew_accounting=accounting_enabled" in handlers_user

    # Backups go to the report topic first; private-chat sending is a real toggle.
    backup = (ROOT / "backup.py").read_text(encoding="utf-8")
    assert "report_router.send_to_group(" in backup
    assert "backup_skip_admin_dm" in backup
    assert '"adm_backup_dm_toggle"' in (ROOT / "keyboards.py").read_text(encoding="utf-8")
    assert 'F.data == "adm_backup_dm_toggle"' in handlers_admin
    assert "backup_skip_admin_dm" in (ROOT / "extra_settings_schema.py").read_text(encoding="utf-8")

    # Doctor DNS: device limit ("user count") and the one-time SSH bootstrap.
    provider = (ROOT / "panel_providers/doctordns_provider.py").read_text(encoding="utf-8")
    assert "supports_user_limit = True" in provider
    assert "async def _apply_devices(" in provider
    assert '@app.post("/api/panel-servers/doctordns/auto-setup")' in admin_panel
    assert "doctor_dns_ssh_setup.setup_existing_panel" in admin_panel
    assert "wireDoctorDNSAutoBox" in admin_js

    # Public service URLs are editable at runtime instead of only from .env.
    assert "def _runtime_api_base_url(" in admin_panel
    assert "def _runtime_miniapp_url(" in (ROOT / "miniapp/server.py").read_text(encoding="utf-8")
    assert "miniapp_public_url" in (ROOT / "keyboards.py").read_text(encoding="utf-8")
    assert '@app.put("/api/links-ssl")' in admin_panel
    assert "renderLinksSSL" in admin_js and "'links-ssl'" in admin_js

    # CI proves the new module imports on a lean install.
    workflow = (ROOT / ".github/workflows/deploy-smoke-test.yml").read_text(encoding="utf-8")
    assert '"doctor_dns_ssh_setup", "panel_providers.doctordns_provider"' in workflow


def test_upstream_982_batch_is_wired_end_to_end():
    """Upstream 9.8.2 (fork 4.38.0): per-tenant userbot/leak state, in-bot Telegram
    login, the Doctor DNS SSH bootstrap, quota-pool "start on first use", the
    accounting-priced service add-ons and full-reseller conversion.

    Every edge is asserted, so a later sync cannot leave one of them half-wired.
    """
    for relative in ("tenant_ctx.py", "userbot_login.py", "doctor_dns_ssh_setup.py",
                     "tests/test_doctordns_ssh_setup.py",
                     "tests/test_accounting_service_addon.py",
                     "tests/test_pool_first_use.py",
                     "tests/test_ssh_udpgw_install.py"):
        path = ROOT / relative
        assert path.is_file(), f"{relative} is missing"
        assert path.stat().st_size > 0, f"{relative} is empty"

    # tenant_ctx: one context per bot, wired into the userbot and the leak scanner.
    tenant = (ROOT / "tenant_ctx.py").read_text(encoding="utf-8")
    for needle in ("CURRENT = contextvars.ContextVar(", "def key_for(", "def use(",
                   "def current_key(", "def session_file(", "def middleware(",
                   "class PerTenant("):
        assert needle in tenant, f"tenant_ctx.py lost {needle}"
    for module in ("userbot.py", "leak_scanner.py", "leak_discovery.py", "leak_admin.py"):
        text = (ROOT / module).read_text(encoding="utf-8")
        assert "import tenant_ctx" in text, f"{module} no longer imports tenant_ctx"
    assert "tenant_ctx.use(db)" in (ROOT / "leak_scanner.py").read_text(encoding="utf-8")
    assert "tenant_ctx.middleware(db)" in (ROOT / "leak_admin.py").read_text(encoding="utf-8")

    # In-bot Telegram login: router registered for reseller bots in bot_manager.
    login = (ROOT / "userbot_login.py").read_text(encoding="utf-8")
    for needle in ("def create_login_router(", "class UbLogin(", "def login_buttons("):
        assert needle in login, f"userbot_login.py lost {needle}"
    manager = (ROOT / "bot_manager.py").read_text(encoding="utf-8")
    assert "from userbot_login import create_login_router" in manager
    assert "dp.include_router(create_login_router(db))" in manager
    assert "from userbot_login import login_buttons" in (ROOT / "userbot_admin.py").read_text(encoding="utf-8")
    assert "from userbot_login import login_buttons" in (ROOT / "leak_admin.py").read_text(encoding="utf-8")

    # Doctor DNS SSH bootstrap: module + the admin-panel route that triggers it.
    dns_setup = (ROOT / "doctor_dns_ssh_setup.py").read_text(encoding="utf-8")
    for needle in ("def _patch_panel_source(", "def _remote_script(",
                   "PANEL_TOO_OLD", "api_admin_devices"):
        assert needle in dns_setup, f"doctor_dns_ssh_setup.py lost {needle}"
    admin_panel = (ROOT / "admin_panel/server.py").read_text(encoding="utf-8")
    assert '@app.post("/api/panel-servers/doctordns/auto-setup")' in admin_panel

    # Quota pool "start on first use": db methods -> reconciler -> renewal -> catalog.
    usage = (ROOT / "db/usage.py").read_text(encoding="utf-8")
    for needle in ("def quota_pool_first_use_pending(", "def activate_quota_pool_first_use(",
                   "def add_quota_pool_first_use_days("):
        assert needle in usage, f"db/usage.py lost {needle}"
    assert "quota_pool_first_use_pending" in (ROOT / "quota_reconciler.py").read_text(encoding="utf-8")
    assert "activate_quota_pool_first_use" in (ROOT / "quota_reconciler.py").read_text(encoding="utf-8")
    assert "quota_pool_first_use_pending" in (ROOT / "renewal_engine.py").read_text(encoding="utf-8")
    assert "add_quota_pool_first_use_days" in (ROOT / "renewal_engine.py").read_text(encoding="utf-8")
    assert "first_use_pending" in (ROOT / "db/catalog.py").read_text(encoding="utf-8")
    dpp = (ROOT / "direct_panel_provision.py").read_text(encoding="utf-8")
    assert "def pool_first_use(" in dpp and "_first_use_pool_meta" in dpp

    # Accounting-priced service add-ons, reachable from the bot's volume/user flows.
    accounting = (ROOT / "accounting.py").read_text(encoding="utf-8")
    assert "def suggest_service_addon(" in accounting
    handlers_user = (ROOT / "handlers_user.py").read_text(encoding="utf-8")
    assert "accounting.suggest_service_addon" in handlers_user
    assert handlers_user.count("suggest_service_addon") >= 2

    # Full-reseller conversion: db helper -> admin callback -> keyboard -> state.
    users_db = (ROOT / "db/users.py").read_text(encoding="utf-8")
    assert "def is_unrestricted_full(" in users_db
    resellers = (ROOT / "db/resellers.py").read_text(encoding="utf-8")
    for needle in ("def get_reseller_membership_info(", "def convert_reseller_to_full(",
                   "reseller_discount_percent_prev"):
        assert needle in resellers, f"db/resellers.py lost {needle}"
    handlers_admin = (ROOT / "handlers_admin.py").read_text(encoding="utf-8")
    assert "adm_resbot_makefull:" in handlers_admin
    assert "adm_resbot_makefull_ok:" in handlers_admin
    keyboards = (ROOT / "keyboards.py").read_text(encoding="utf-8")
    assert "def resbot_makefull_confirm_kb(" in keyboards
    assert "adm_resbot_makefull:" in keyboards
    states = (ROOT / "states.py").read_text(encoding="utf-8")
    assert "class AdminResbotWebCreds(" in states

    # The UDP gateway fix on SSH nodes, pinned by its own test.
    agent = (ROOT / "deploy/install-shopvpn-ssh-agent.sh").read_text(encoding="utf-8")
    assert "badvpn-udpgw" in agent
    assert "127.0.0.1:7300" in agent
    assert "shopvpn-udpgw.service" in agent
    assert "udpgw" in (ROOT / "ssh_auto_install.py").read_text(encoding="utf-8")

    # The fork's lean installer must not have been replaced by upstream's.
    for protected in ("install.sh", "manage.sh", "update.sh", "preflight.sh",
                      "cleanup.sh", "setup_local_translation.sh", "check_upstream.sh"):
        assert (ROOT / protected).is_file(), f"{protected} disappeared"


def test_ssh_node_reachability_and_user_node_accounts_are_wired():
    """4.39.0 sync: the "client says connected but nothing pings" fix must stay
    reachable end to end, and node accounts must reach the buyer.

    A firewall helper on the agent does nothing unless the agent actually calls
    it at start-up and on a timer, the panel can ask the agent for a diagnosis,
    and the buyer can see the account in the bot and the mini app.
    """
    agent = (ROOT / "ssh_node_agent.py").read_text(encoding="utf-8")
    # Firewall/ICMP/IPv4 helpers exist and are idempotent.
    for needle in ("def _firewall_ranges", "def _firewall_open_ranges", "def _nft_input_accept",
                   "def _ensure_icmp_ping", "def _prefer_ipv4_resolution",
                   "def _ensure_network_access", "def diagnose", "def diagnose_http"):
        assert needle in agent, f"ssh_node_agent lost {needle}"
    # …and they are actually reached: at start-up, on the enforcement timer, and over HTTP.
    assert "await asyncio.to_thread(self._ensure_network_access)" in agent
    assert "tick % 10 == 0" in agent
    assert 'app.router.add_get("/v1/diagnose", self.diagnose_http)' in agent
    assert '"--diagnose"' in agent and '"--fix"' in agent
    # The default SSH port range is no longer skipped as "already open".
    assert "if low >= 20000 and high <= 39999" not in agent

    service = (ROOT / "ssh_service.py").read_text(encoding="utf-8")
    assert "async def probe_ssh_endpoint(" in service
    assert "async def diagnose_node(" in service
    assert 'provider._request("GET", "/v1/diagnose")' in service
    assert '"external_port_reachable"' in service
    assert '"reachable": reachable' in service
    assert "refresh: bool = False" in service

    # Admin panel: the diagnose route is registered and the UI can ask for a refresh.
    server = (ROOT / "admin_panel/server.py").read_text(encoding="utf-8")
    assert '"/api/ssh/nodes/{node_id}/diagnose"' in server
    assert "refresh=body.refresh" in server
    assert "refresh: bool = False" in server

    # Buyer-facing: the bot lists node accounts and offers the action callback.
    handlers_user = (ROOT / "handlers_user.py").read_text(encoding="utf-8")
    assert "db.list_ssh_accounts(user_tg_id)" in handlers_user
    assert 'F.data.startswith("mo_ssh_action:")' in handlers_user
    assert 'if kind == "ssh":' in handlers_user

    # Mini app: owner-only endpoints plus the client that renders them.
    miniapp = (ROOT / "miniapp/server.py").read_text(encoding="utf-8")
    assert '"/api/ssh-accounts"' in miniapp
    assert '"/api/ssh-accounts/{account_row_id}/action"' in miniapp
    assert "db.list_ssh_accounts(tg_id)" in miniapp
    miniapp_js = (ROOT / "miniapp/static/app.js").read_text(encoding="utf-8")
    assert "renderNodeAccountDetail" in miniapp_js
    assert "wireNodeAccountActions" in miniapp_js
    assert "/api/ssh-accounts/" in miniapp_js

    # PayG status text: the renderer, its keys, and the admin editor that feeds it.
    payg = (ROOT / "payg.py").read_text(encoding="utf-8")
    assert "def render_status_text(" in payg
    assert "PAYG_STATUS_TEXT_ACTIVE_KEY" in payg and "PAYG_STATUS_TEXT_INACTIVE_KEY" in payg
    assert "custom_text = render_status_text(db" in payg
    assert "status_text_active" in server
    assert "payg-status-active" in (ROOT / "admin_panel/static/app.js").read_text(encoding="utf-8")

    # The fa/en-only rule: no third language may ride along in the PayG catalog.
    import i18n
    assert i18n.SUPPORTED_LANGUAGES == ("fa", "en")
    assert set(i18n._PAYG_TRANSLATIONS) == {"en"}, "a third language came back into _PAYG_TRANSLATIONS"

    # Rejected upstream paths from this round must stay out.
    assert not (ROOT / "README.ru.md").exists(), "upstream's Russian README came back"
    assert not (ROOT / "README.zh.md").exists(), "upstream's Chinese README came back"
    assert not (ROOT / "update.json").exists(), "upstream's update.json came back"
    # web_store/server.py must stay the fork's lean storefront, not upstream's miniapp copy.
    ws = (ROOT / "web_store/server.py").read_text(encoding="utf-8")
    assert len(ws.splitlines()) < 1200, "web_store/server.py was replaced by upstream's miniapp copy"
    # ssh_auto_install must not reference deploy files the fork does not ship.
    installer = (ROOT / "ssh_auto_install.py").read_text(encoding="utf-8")
    for rel in ("deploy/shopvpn-ovpn-auth.py",):
        assert rel not in installer, f"{rel} is referenced but not shipped"


def test_central_sub_profiles_and_panel_links_are_wired():
    """4.41.0 sync (upstream 9.9.0): multi-domain dedicated-sub profiles and the
    per-panel sub links must stay reachable end to end.

    A profile row is useless unless the request path actually resolves a profile
    from the Host header, the link builder uses it, the sub server scopes a
    service to one panel, and the admin panel exposes the CRUD routes the UI
    calls. File existence alone would not catch a dropped wire.
    """
    ds = (ROOT / "dedicated_sub.py").read_text(encoding="utf-8")
    for needle in ("PROFILE_OWN_KEYS", "PROFILE_SETTING_KEYS", "def all_settings(db, profile",
                   "def get_profile", "def list_profiles", "def profile_for_host",
                   "def profile_for_panel", "def profile_for_config", "def sort_panel_ids",
                   "def is_scoped", "def panel_entries", "def scoped_config",
                   "def panel_page_links", "SCOPE_KEY"):
        assert needle in ds, f"dedicated_sub lost {needle}"
    # The profile-aware signatures must actually be called with a profile.
    assert "def base_url(db, profile" in ds
    assert "def is_enabled(db, profile" in ds
    assert "def link_for_token(db, token: str, profile" in ds
    assert "profile_for_config(db, config_id, cc)" in ds
    # A scoped (single-panel) view must not leak node/SSH accounts.
    assert "if is_scoped(cc):" in ds

    db_ds = (ROOT / "db/dedicated_sub.py").read_text(encoding="utf-8")
    for needle in ("def dsp_list", "def dsp_get", "def dsp_get_by_host", "def dsp_create",
                   "def dsp_update", "def dsp_set_settings", "def dsp_delete",
                   "def dsp_panel_ids", "def dsp_set_panels", "def dsp_for_panel"):
        assert needle in db_ds, f"db/dedicated_sub lost {needle}"
    # The table and the panel column are created by the schema, not assumed.
    base = (ROOT / "db/_base.py").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS dsub_profiles" in base
    assert '"panel_servers", "dsub_profile_id"' in base
    assert '"dsub_profile_id"' in (ROOT / "db/panels.py").read_text(encoding="utf-8")

    # Sub server: the Host header picks the profile and /p/{pid} scopes the service.
    server = (ROOT / "sub_server/server.py").read_text(encoding="utf-8")
    assert "async def _profile(request" in server
    assert "ds.profile_for_host" in server
    assert "async def _cc_for(request" in server
    assert "ds.scoped_config" in server
    assert "ds.all_settings, db, prof" in server
    assert "ds.is_enabled(db, prof)" in server
    assert "async def _page_panels(" in server
    assert "ds.panel_page_links" in server
    # Every per-panel route is registered, not just the plain one.
    for route in ('"/s/{token}/p/{pid:int}"', '"/s/{token}/p/{pid:int}/qr.png"',
                  '"/s/{token}/p/{pid:int}/ovpn/{n:int}"', '"/s/{token}/p/{pid:int}/wg/{n:int}"',
                  '"/s/{token}/p/{pid:int}/dns/login"', '"/s/{token}/p/{pid:int}/vpn/{n:int}/ca"',
                  '"/s/{token}/p/{pid:int}/reveal"'):
        assert route in server, f"sub_server lost the route {route}"
    # The W-UI/DNS caches are keyed per account, not per config, or two panels collide.
    assert "_wui_cache: Dict[tuple, tuple]" in server
    assert "_dns_cache: Dict[tuple, tuple]" in server
    assert 'key = (cid, str(cc["username"]))' in server

    # The page renders the per-panel section.
    page = (ROOT / "sub_server/sub_page.html").read_text(encoding="utf-8")
    assert 'id="pnsec"' in page and "D.show.panels" in page

    # Admin panel: the CRUD/SSL/settings routes the web UI calls.
    admin = (ROOT / "admin_panel/server.py").read_text(encoding="utf-8")
    for route in ('@app.get("/api/dsub-profiles")', '@app.post("/api/dsub-profiles")',
                  '@app.put("/api/dsub-profiles/{profile_id}")',
                  '@app.delete("/api/dsub-profiles/{profile_id}")',
                  '@app.put("/api/dsub-profiles/{profile_id}/panels")',
                  '@app.get("/api/dsub-profiles/{profile_id}/settings")',
                  '@app.put("/api/dsub-profiles/{profile_id}/settings")',
                  '@app.post("/api/dsub-profiles/{profile_id}/ssl")'):
        assert route in admin, f"admin_panel lost {route}"
    assert "def _dsp_clean_url(" in admin
    assert "def _dsp_guard(" in admin
    # The live preview can render a profile, not only the central settings.
    assert "def api_sub_page_preview(profile: Optional[int] = Query(None)" in admin
    assert "ds.all_settings(db, prof)" in admin

    # The web UI actually calls those routes.
    appjs = (ROOT / "admin_panel/static/app.js").read_text(encoding="utf-8")
    assert "function dsubProfilesCardHtml(" in appjs
    assert "async function bindDsubProfiles(" in appjs
    assert "/dsub-profiles" in appjs


def test_payg_miniapp_provisioning_is_wired():
    """4.41.0 sync: the mini app can read PayG state and create a service.

    The bot's rules must be the same ones the mini app applies, so the shared
    helpers are pinned, and both endpoints must reach them.
    """
    payg = (ROOT / "payg.py").read_text(encoding="utf-8")
    for needle in ("class PaygProvisionError", "def provision_blocker",
                   "async def provision_service_for_user", "def miniapp_overview",
                   "def _ensure_schema_once", "def _max_services_per_user",
                   "def _active_service_count"):
        assert needle in payg, f"payg lost {needle}"
    # The fork bills one per-GB rate; the tiered upstream helpers must stay out.
    assert "def get_rates(" not in payg, "tiered PayG rates were pulled back in"
    assert "get_rates(" not in payg
    # A missing PayG account must not KeyError on the usage field.
    assert "int(status.get('month_used_bytes') or 0)" in payg

    miniapp = (ROOT / "miniapp/server.py").read_text(encoding="utf-8")
    assert '@app.get("/api/payg/info")' in miniapp
    assert '@app.post("/api/payg/provision")' in miniapp
    assert "payg.miniapp_overview(db, tg_id)" in miniapp
    assert "await payg.provision_service_for_user(db, tg_id)" in miniapp
    assert "except payg.PaygProvisionError as e:" in miniapp
    # PayG stays a main-bot feature, never a reseller bot's.
    assert "def _payg_available(tenant)" in miniapp

    appjs = (ROOT / "miniapp/static/app.js").read_text(encoding="utf-8")
    assert "/payg/info" in appjs and "/payg/provision" in appjs


def test_account_hub_bulk_toggle_is_wired():
    """4.41.0 sync: the admin can switch every account-hub button at once, and
    the «configs» button honours its own toggle."""
    consts = (ROOT / "db/constants.py").read_text(encoding="utf-8")
    assert '"svc_show_links"' in consts
    assert "BULK_TOGGLE_KEYS = [k for k, _l, _d in ACCOUNT_TOGGLE_KEYS" in consts

    kb = (ROOT / "keyboards.py").read_text(encoding="utf-8")
    assert 'callback_data="adm_acct_all:0"' in kb
    assert 'callback_data="adm_acct_all:1"' in kb
    assert '("svc_links", "\U0001F4CB \u06a9\u0627\u0646\u0641\u06cc\u06af\u200c\u0647\u0627\u06cc \u062a\u06a9\u06cc", "svc_show_links", False)' in kb

    admin = (ROOT / "handlers_admin.py").read_text(encoding="utf-8")
    assert 'F.data.startswith("adm_acct_all:")' in admin
    assert "from db.constants import BULK_TOGGLE_KEYS" in admin

    user = (ROOT / "handlers_user.py").read_text(encoding="utf-8")
    assert 'db.get_setting, "svc_show_links", "1"' in user

    # Both copies of the button registry stay in step and expose the toggle.
    for rel in ("button_registry.py", "admin_panel/static/button_registry.py"):
        reg = (ROOT / rel).read_text(encoding="utf-8")
        assert 'toggle = kb._ACCOUNT_HUB_CALLBACKS[key][0]' in reg, rel
        assert '"togglable": True' in reg, rel


def test_node_only_subscriptions_are_wired_end_to_end():
    """4.42.0 sync: node-only products get a real dedicated-subscription page.

    A `node_subscriptions` row is useless unless provisioning creates it, the
    sub server can serve its token, the buyer can renew/rename it, and a failed
    provision rolls it back.
    """
    base = (ROOT / "db/_base.py").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS node_subscriptions" in base
    assert "node_subscription_id INTEGER" in base
    assert '"node_subscriptions"' in base or "idx_node_subscriptions_user" in base
    # SQLite ALTER for DBs created before this release.
    assert "ALTER TABLE ssh_accounts ADD COLUMN node_subscription_id" in base

    usage = (ROOT / "db/usage.py").read_text(encoding="utf-8")
    for needle in (
        "def create_node_subscription",
        "def link_ssh_account_to_node_subscription",
        "def rename_owned_node_subscription",
        "def ds_node_sub_get_or_create_token",
        "def ssh_accounts_for_node_subscription",
        "def node_subscription_quota_info",
    ):
        assert needle in usage, f"db/usage.py lost {needle}"

    orders = (ROOT / "db/orders.py").read_text(encoding="utf-8")
    assert "def list_node_subscription_renewals" in orders
    assert "renewal_target_kind='node'" in orders

    dsub = (ROOT / "dedicated_sub.py").read_text(encoding="utf-8")
    assert "def link_for_node_subscription" in dsub
    assert "is_node_subscription" in dsub
    assert "def ssh_uris_for_config" in dsub

    prov = (ROOT / "direct_panel_provision.py").read_text(encoding="utf-8")
    assert "db.create_node_subscription(" in prov
    assert "node_subscription_id=node_sub_id" in prov
    assert "dedicated_sub.link_for_node_subscription" in prov
    # A failed subscription link must not leave paid accounts behind.
    assert "DELETE FROM node_subscriptions WHERE id=?" in prov

    server = (ROOT / "sub_server/server.py").read_text(encoding="utf-8")
    assert 'cc.get("is_node_subscription")' in server
    assert "db.node_subscription_quota_info" in server

    renew = (ROOT / "renewal_engine.py").read_text(encoding="utf-8")
    assert 'if kind == "node":' in renew
    assert "UPDATE node_subscriptions SET volume_gb=?" in renew

    user = (ROOT / "handlers_user.py").read_text(encoding="utf-8")
    for needle in (
        "async def _ssh_service_kb(",
        'F.data.startswith("mo_ssh_refresh:")',
        'F.data.startswith("svc_node_history:")',
        'F.data.startswith("svc_node_rename:")',
        'F.data.startswith("svc_node_inquiry:")',
        'F.data.startswith("svc_node_disruption:")',
    ):
        assert needle in user, f"handlers_user.py lost {needle}"
    assert "waiting_node_display_name = State()" in (ROOT / "states.py").read_text(encoding="utf-8")
    # The buyer-facing node menu must be reachable from the item view itself.
    assert "markup = await _ssh_service_kb(account)" in user
    assert "markup = await _ssh_service_kb(current, account_row_id)" in user

    # The upstream node-only test ships with the suite.
    assert (ROOT / "tests/test_dedicated_sub_node.py").is_file()


def test_membership_gift_options_are_wired_end_to_end():
    """4.42.0 sync: the gift subscription offers admin-defined options."""
    base = (ROOT / "db/_base.py").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS welcome_gift_options" in base
    assert "CREATE TABLE IF NOT EXISTS welcome_gift_resends" in base
    assert '"welcome_gift_options", "welcome_gift_resends"' in base, "factory reset must clear gift tables"

    system = (ROOT / "db/system.py").read_text(encoding="utf-8")
    for needle in (
        "def get_welcome_gift_choices",
        "def add_welcome_gift_option",
        "def toggle_welcome_gift_option",
        "def defer_welcome_gift",
        "def welcome_gift_quota",
        "def reset_all_welcome_gifts",
        "def claim_due_welcome_gift_resends",
        "def retry_or_fail_welcome_gift_resend",
    ):
        assert needle in system, f"db/system.py lost {needle}"

    gift = (ROOT / "welcome_gift.py").read_text(encoding="utf-8")
    assert "async def welcome_gift_resend_once" in gift
    # The resend queue has to be polled, not just defined.
    assert "await welcome_gift_resend_once(bot, db)" in gift

    kb = (ROOT / "keyboards.py").read_text(encoding="utf-8")
    assert 'callback_data="acct:wgift"' in kb, "account hub must expose the gift button"
    user = (ROOT / "handlers_user.py").read_text(encoding="utf-8")
    assert 'F.data == "acct:wgift"' in user
    assert 'F.data == "wg_now"' in user and 'F.data == "wg_later"' in user
    assert 'F.data.startswith("wg_pick:")' in user

    admin_server = (ROOT / "admin_panel/server.py").read_text(encoding="utf-8")
    for route in (
        '@app.get("/api/welcome-gift")',
        '@app.post("/api/welcome-gift/options")',
        '@app.put("/api/welcome-gift/options/{option_id}")',
        '@app.delete("/api/welcome-gift/options/{option_id}")',
        '@app.post("/api/welcome-gift/reset-all")',
        '@app.post("/api/users/{tg_id}/welcome-gift/resend")',
    ):
        assert route in admin_server, f"admin panel lost {route}"
    appjs = (ROOT / "admin_panel/static/app.js").read_text(encoding="utf-8")
    assert "/welcome-gift/choices" in appjs
    assert "wgift-reset-all" in appjs
    assert (ROOT / "tests/test_welcome_gift_options.py").is_file()


def test_ticket_and_live_chat_topics_are_split():
    """4.42.0 sync: tickets and live chat report into separate group topics."""
    router = (ROOT / "report_router.py").read_text(encoding="utf-8")
    assert 'TopicSpec("live_chat"' in router
    assert 'TICKET_TOPIC = "support"' in router
    assert 'LIVE_CHAT_TOPIC = "live_chat"' in router
    assert "async def notify_live_chat(" in router
    assert "async def notify_live_chat_raw(" in router
    assert "def ticket_group_mode(" in router
    assert 'SUPPORT_PRIVATE_KEY = "support_to_admin_private"' in router
    assert "async def _handle_group_live_chat_reply" in router

    tickets = (ROOT / "db/tickets.py").read_text(encoding="utf-8")
    assert "def link_live_chat_group_message" in tickets
    assert "def get_live_chat_user_by_group_message" in tickets
    assert "def find_recent_duplicate_admin_reply" in tickets

    consts = (ROOT / "db/constants.py").read_text(encoding="utf-8")
    assert '"support_to_admin_private": "0"' in consts
    schema = (ROOT / "extra_settings_schema.py").read_text(encoding="utf-8")
    assert '_b("support_to_admin_private"' in schema

    user = (ROOT / "handlers_user.py").read_text(encoding="utf-8")
    assert "report_router.notify_live_chat(bot, db, user.id" in user
    miniapp = (ROOT / "miniapp/server.py").read_text(encoding="utf-8")
    assert "report_router.notify_live_chat_raw" in miniapp
    admin = (ROOT / "handlers_admin.py").read_text(encoding="utf-8")
    assert "report_router.ticket_group_mode(db)" in admin
    # A double-clicked reply must not reach the user twice (web panel, mini app).
    admin_server = (ROOT / "admin_panel/server.py").read_text(encoding="utf-8")
    assert "db.find_recent_duplicate_admin_reply, user_id, text" in admin_server
    assert "db.find_recent_duplicate_admin_reply(user_id, text)" in miniapp
    assert (ROOT / "tests/test_support_topics_split.py").is_file()


def test_broadcast_deeplinks_node_actions_and_payg_pool_repair_are_wired():
    """4.42.0 sync: deep-link buttons in broadcasts, honest node actions,
    PayG pool repair."""
    admin = (ROOT / "handlers_admin.py").read_text(encoding="utf-8")
    for needle in (
        'F.data == "adm_bc_dl_pick"',
        'F.data == "adm_bc_single_send"',
        'AdminBroadcast.waiting_deeplink_button_text',
        'AdminBroadcast.waiting_custom_param',
        "broadcast_deeplink_buttons",
    ):
        assert needle in admin, f"handlers_admin.py lost {needle}"
    kb = (ROOT / "keyboards.py").read_text(encoding="utf-8")
    assert 'callback_data="adm_bc_dl_pick"' in kb
    states = (ROOT / "states.py").read_text(encoding="utf-8")
    assert "waiting_deeplink_button_text = State()" in states

    ssh = (ROOT / "ssh_service.py").read_text(encoding="utf-8")
    assert "async def refresh_account(" in ssh
    # enable/disable/delete are only recorded when the node acknowledges them.
    assert "if changed is not True" in ssh
    assert "if deleted is not True" in ssh
    user = (ROOT / "handlers_user.py").read_text(encoding="utf-8")
    assert 'await ssh_service.account_action(db, account["account_id"], action, force=False)' in user

    payg = (ROOT / "payg.py").read_text(encoding="utf-8")
    assert "pool_restore = {" in payg
    assert "def _central_link(db, custom_config_id, upstream_url)" in payg
    assert "db.set_quota_pool_status(pool_id, \"active\")" in payg
    assert (ROOT / "tests/test_payg_multi_stale_pool.py").is_file()

    # The deploy script must keep the badvpn build working on new CMake.
    agent_installer = (ROOT / "deploy/install-shopvpn-ssh-agent.sh").read_text(encoding="utf-8")
    assert "CMAKE_POLICY_VERSION_MINIMUM=3.5" in agent_installer
    # Node sshd keeps the fork's hardening.
    sshd_unit = (ROOT / "deploy/shopvpn-sshd@.service").read_text(encoding="utf-8")
    assert "NoNewPrivileges=true" in sshd_unit
    assert "ProtectSystem=full" in sshd_unit


def test_card_auto_webhook_address_is_shown_and_copyable():
    """The bot's admin screen for the BankSmsForwarder app must show the server
    webhook address and give a one-tap copy button (CopyTextButton)."""
    admin = (ROOT / "handlers_admin.py").read_text(encoding="utf-8")
    assert "CopyTextButton" in admin
    assert 'tr("📋 کپی آدرس وب‌هوک سرور")' in admin
    assert "copy_text=CopyTextButton(text=webhook_url)" in admin
    assert 'f"{base_url}/api/webhooks/sms-forwarder"' in admin
    # Reseller bots must call their own tenant's webhook, not the main one.
    assert 'db.get_setting, "miniapp_tenant_id", ""' in admin
    assert 'webhook_url += f"?b={tenant_id}"' in admin
    import i18n_extra

    assert i18n_extra.EXTRA_PHRASES.get(
        "📋 کپی آدرس وب‌هوک سرور"
    ) == "📋 Copy server webhook address"
