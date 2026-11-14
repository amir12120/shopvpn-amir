# Sync this fork with upstream (Shopvpn)

This file is the authoritative, reusable procedure for pulling new upstream work
into this fork **without breaking anything we changed ourselves**.

- fork: `https://github.com/amir12120/shopvpn-amir` (branch `main`)
- upstream: `https://github.com/mehdirafatpanah/Shopvpn`

## How to use this file

Give your coding agent (Freebuff, Codex, Cursor, Claude Code, ...) this one line:

> Read `SYNC_UPSTREAM.md` in the repo root and execute every step in it exactly.
> Start with Step 1 and show me the classification report; wait for my approval
> before merging anything.

Persian equivalent, if you prefer:

> فایل `SYNC_UPSTREAM.md` در ریشه‌ی ریپو را کامل بخوان و دقیقاً طبق همان اجرا کن؛
> اول گزارش مرحله‌ی ۱ را بده و قبل از merge منتظر تأیید من بمان.

The agent must read the whole file before touching anything. Everything below is
binding: if a step cannot be completed safely, the agent reports it instead of
guessing.

---

## 0. Environment and hard rules

- Repo root on this machine: `E:\Z\new shop\Shopvpn`, branch `main`.
- Helper Python: `PY="/e/Z/new shop/TEMp/shopvpn-venv/Scripts/python.exe"`.
  Prefix every Python/test command with `PYTHONUTF8=1`, otherwise Persian output
  crashes with a cp1252 error.
- Shell is Git Bash on Windows: bash syntax everywhere, never cmd.exe.
- `core.autocrlf=true`: the working tree is CRLF, repo blobs are LF. Never
  "fix" line endings and never include a line-ending-only diff.
- **Never execute `install.sh`, `manage.sh`, `update.sh`, `cleanup.sh`,
  `preflight.sh`, `setup_local_translation.sh`, or anything that touches
  systemd, apt, pip installs, or a live server.** Verify statically and with the
  test suite only.
- If `git status` is not clean at the start, stop and report. Never discard,
  stash, or overwrite changes you did not make.
- This is a released, user-installed product (v4.17.0+) running on Ubuntu 22.04
  with systemd, Argos offline translation and SQLite. A broken merge ships real
  damage to real servers. Be conservative and evidence-driven.
- The repository is **standalone** now (not a GitHub fork). There is no automatic
  upstream merge and no "behind" badge; compare content, not the fork counter.

## 1. Investigate BEFORE changing anything

0. Make sure the upstream remote exists. `bash check_upstream.sh` adds or
   updates it, fetches the source, and prints a read-only comparison; use the
   commands below when you need the raw diff.
1. `git fetch upstream main` (or `bash check_upstream.sh`)
2. `git log --oneline HEAD..upstream/main`
3. `git diff --stat HEAD...upstream/main`
4. Read the real upstream diffs for Python changes: `git diff HEAD...upstream/main -- '*.py'`
5. Write a short report classifying each upstream commit as one of:
   - `NEW PYTHON FEATURE`
   - `PYTHON BUGFIX`
   - `INSTALL / SCRIPT CHANGE` (reject)
   - `DOCS` (reject unless it documents a feature we take)
   - `CI` (reject)
6. State, before merging, which category you take and which you reject.
   Do not start the merge before presenting this plan.
7. If anything is ambiguous or destructive, ask. Do not improvise.

## 2. Protected files — the fork side ALWAYS wins

Upstream re-uploads its own older shell files on every merge. These never change:

- `install.sh`, `manage.sh`, `update.sh`, `preflight.sh`, `cleanup.sh`,
  `setup_local_translation.sh`, `check_upstream.sh`
  → **the install/update flow is never modified**
- everything under `.github/`
- everything under `tests/`
- `VERSION`
- `README.md`, `README.fa.md`, `INSTALL.md`, `INSTALL.fa.md`
  (ru/zh readmes are deliberately absent; this project is fa/en only)
- `i18n_extra.py`, and `i18n.py` where it declares
  `SUPPORTED_LANGUAGES = ("fa", "en")` — never add a third language

Also: do not import upstream's donation / crypto-wallet lines.

## 3. Merge procedure

- `git merge --no-commit --no-ff upstream/main`
- Resolve conflicts deterministically in favour of the fork:
  `git checkout --ours install.sh manage.sh update.sh preflight.sh cleanup.sh setup_local_translation.sh check_upstream.sh VERSION README.md README.fa.md INSTALL.md INSTALL.fa.md i18n_extra.py`
  and restore `.github/` and `tests/` wholesale to the fork side.
- Accept upstream only for new/modified Python code (features, bug fixes).
- If upstream **deleted** a file the fork needs, do not delete it. Keep it and
  report the deletion.
- A new third-party dependency from upstream: add it to `requirements.txt`
  keeping the lean flags (`--no-cache-dir`, CPU torch index when relevant), and
  add an import assertion for it to the CI job's
  "Runtime project-module import (merged upstream features)" step. If the local
  venv cannot import it (for example `aiohttp` is missing locally), say so and
  let CI prove it instead of claiming success.
- No cosmetic reformatting, no import reordering, no "while I was here" edits.
  Keep every diff minimal and reviewable.

## 4. Pin new features in the integrity test

- Update `tests/test_merge_integrity.py`: append every newly added upstream
  module to `UPSTREAM_FEATURE_MODULES` and add **real wiring** assertions — the
  module must be imported and actually reachable from a handler / menu / DB
  path. File existence alone is not enough.
- If a new module is wired through a dispatcher or registry, find that edge and
  assert it too.

## 5. Fork improvements that MUST survive every merge

Verify each of these still holds after merging. They are already pinned in the
test suite; if one fails, fix the merge — never the test.

- `force_join.py`, `config_delivery.py`, `handlers_admin.py`: line 1 is
  `# -*- coding: utf-8 -*-`, with `from i18n import tr` **below** the docstring.
- `handlers_admin.py` contains `call.bot.send_message(uid, notification)`.
- `handlers_user.py` contains at least two `call.bot, db,` occurrences.
- `keyboards.py` contains exactly one `def blupal_settings_kb(`.
- `admin_panel/server.py` imports `is_language_enabled`.
- The `language_selected` migration exists.
- `setup_local_translation.sh` installs Argos models **as the service account**:
  `SERVICE_USER` resolved via `systemctl show -p User --value "$SERVICE_NAME"`
  plus `getent passwd`; `as_service_user` sets `HOME=$SERVICE_HOME` and unsets
  `XDG_DATA_HOME` / `XDG_CACHE_HOME` / `XDG_CONFIG_HOME`; the LibreTranslate
  unit sets `Environment=HOME=$SERVICE_HOME`. This is the fix that stopped
  `/root` from filling up with a duplicate copy of every model.
- `cleanup.sh` sweeps pip + Argos download caches for **all** relevant homes
  (caller, service account, `/root`) using `while IFS= read -r h` — a plain
  `for h in $LIST` breaks on paths containing spaces; it also removes stale
  `/tmp/{restore_,restore_full_,xui_restore_,qr_bg_,image_,media_}*` dirs and
  vacuums the journal with `journalctl --vacuum-size=` (`SHOPVPN_JOURNAL_MAX`,
  default 200M).
- `manage.sh` has `wait_for_service_ready()` / `restart_service_and_wait()`
  (three consecutive `systemctl is-active` polls, 30 s budget, prints journal
  lines on failure) and `update_bot()` runs in this order:
  fetch → pip → translation → cleanup.sh → restart-and-wait. A failed
  translation step is a warning (`warned=1`), never `failed=1`; "Bot did not
  start" is printed only when the unit is actually inactive.
- `setup_local_translation.sh` must keep `set -uo pipefail` (not `-e`) and read
  `SHOPVPN_TRANSLATION_LANGS` with `sed ... || true`, then write the key before
  any download. This is the fix for the silent `✗ translation` failure.
- `install.sh` writes the journald drop-in
  (`/etc/systemd/journald.conf.d/shopvpn-disk.conf`, `SystemMaxUse`,
  `SystemKeepFree=1G`, opt out with `SHOPVPN_SKIP_JOURNAL_LIMIT=1`) and has the
  `BOT_READY` readiness loop.

## 6. Quality gates — ALL must pass, never work around one

- `PYTHONUTF8=1 "$PY" -m pytest tests -q` (baseline: 140+ passed)
- `PYTHONUTF8=1 "$PY" -m ruff check --select F821,F811,E9 .`
  (ruff ships in the helper venv; a bare `ruff` may be "command not found")
- `bash -n` on every `*.sh`, plus a scan for the shell-glue bug class:
  `grep -nE '^(fi|done|esac|else)[A-Za-z_"]' *.sh` must return nothing.
- `"$PY" -m compileall -q .`
- `"$PY" check_i18n_coverage.py` must **exit 0**. Every new uncovered Persian
  string needs an English entry in `i18n_extra.EXTRA_PHRASES` (write ZWNJ as
  `\u200c`). Never "fix" this by weakening the checker.
- The workflow YAML must still parse.
- Known traps to re-check after every merge: a doubled backslash, or a size
  regex that requires a trailing `B`, makes the journal-size parse print `-`.
- Never delete, skip, or weaken a test to get green. If a gate cannot run in
  this environment, report it as NOT RUN instead of claiming success.

## 7. Release

1. Bump `VERSION` (e.g. 4.9.1 → 4.10.0). The file is CRLF in the working copy —
   preserve that.
2. Commit message in English that explains **why** (which upstream commits and
   which features), not a restatement of the diff.
3. `git tag -a v<VERSION> -m "..."` and `git push origin main --tags`.
   Pushes sometimes do not land on the first attempt: retry with
   `timeout 200 git -c http.version=HTTP/1.1 push origin main`, then **prove** it
   landed via `git fetch origin main -q` and comparing `git rev-parse HEAD` with
   `git rev-parse origin/main`.
4. Create the GitHub release for that tag via the REST API. Use the workspace
   token source described in `AGENTS.md`; never paste a token into the repo or
   a release body.
5. Wait for CI: `Deploy Smoke Test` and `Cleanup Caches` must be green. Poll in
   short calls; a long poll can exceed the command timeout. If red, fix the
   cause, never suppress it.
6. Final check: `git status` clean, `VERSION` correct, and a fresh
   `git diff --stat HEAD upstream/main` contains only the documented exclusions
   (install/scripts, ru/zh docs, root upload duplicates, and upstream's
   zero-width watermark lines). Because this is a standalone repo,
   `HEAD..upstream/main == 0` is **not** the goal and must not be used as a
   success test.

## 8. Final report (short, factual)

- Which upstream commits/features came in, and what each one does.
- Which upstream changes were REJECTED and why.
- What was added to the tests and CI.
- Result of each quality gate, plus the CI run number/URL.
- Tag, release link, and the list of upstream changes still excluded.
- Anything you could NOT do, stated plainly. Never invent success, never hide a
  failing check.

## 9. Sync log

| Date | Fork version | Ported | Rejected and why |
|---|---|---|---|
| 2026-10-30 | 4.19.0 | Storefront network map (`web_store/static/assets/network-map.*`) and its server-side `/api/web/world-map` cache. It is a static, clearly-labelled illustrative map with no CDN call and no new Python dependency. | The 41 new upstream uploads are mostly zero-width watermark noise; upstream also removed the reseller-section switch, web-store branding fields, the SSH node install package and node creation, and regressed the SSH username digit guard. Root `catalog.py`/`users.py`/`system.py`/`orders.py` are unimported upload duplicates with package-relative imports. Russian/Chinese READMEs violate the fa/en-only policy. None of those were copied. |
| 2026-10-31 | 4.21.0 | Multi-target extra panels/nodes (`multi_target`, `db/multi_target`), SSH hosts/URI/service, SSH admin wiring, quota/renewal/dedicated-sub/provider deltas, web-store/miniapp/admin panel Python+JS. Restored fork SSH install-package + web-store preview URL + renderSSHInstall. | Upstream VERSION 7.5.0; deploy SSH/OVPN/WG agent scripts and systemd units; root `test_*.py`; install.sh family; donation; ru/zh. |
| 2026-11-04 | 4.22.0 | Product targets per product (`product_targets`, db/orders/catalog/admin+direct provisioning), one source of panel capabilities (`panel_capabilities` + startup repair so old products match real panel support), config healing on subscription fetch (`panel_resync` + `quota_reconciler` stale_grace), per-product full-renewal rules (`renewal_rules` in bot/web/miniapp), extra-settings editor inside the bot (`admin_extra_settings`) and desktop QR-background upload, release link in the update message, plus `check_settings_sync.py` with its baseline/tests. Two upstream bugs fixed instead of suppressed: undefined `logger` in `miniapp/server.py`, duplicate local imports in `admin_panel/server.py`. | Upstream VERSION 7.9.0; `release.sh` (re-added upstream with `git push -f`); `deploy/` SSH-agent and OVPN auth scripts (fork keeps its lean install flow); ru/zh READMEs and the re-added `README.ru.md`/`README.zh.md` (fa/en only); `test_multi_target.py` (deleted in the fork on purpose); empty commit 10dca66; donation/crypto-wallet lines. |
| 2026-11-05 | 4.23.0 | W-UI panel type (`panel_providers/wui_provider.py`, registered in PROVIDERS/TEMPLATE_BASED/TOKEN_ONLY with its secret and template prompts); cross-panel user migration (`panel_migration.py`, `db/panel_migration.py`, `admin_panel_migration.py`, wired in `handlers_admin.py` and `db/__init__.py`); several manual card-to-card cards with weighted shares (`payment_cards` and `payment_card_assignments` schema, `db/payments.py`, receipt matching in `db/orders.py`, bot editor in `states.py`/`keyboards.py`/`handlers_admin.py`, card API in the mini app); W-UI dedicated-sub files and OpenConnect/L2TP/PPTP/IKEv2 logins (`dedicated_sub.py`, `sub_server/server.py`, `sub_server/sub_page.html`, CSP connect-src narrowed to 'self'); web settings navigation groups/sub-tabs/search (`admin_panel/static/*`); Aban Gateway availability diagnostics. Bugfixes: auto-provision products are no longer tied to config-bank stock (bot + mini app), referral level 2/3 commission is now actually paid (`db/system.py`, `db/users.py`), an empty welcome text no longer crashes /start, and receipts match the new card numbers. | Upstream VERSION 8.8.0; all four READMEs (fa/en only, ru/zh stay deleted); upstream's Persian AUDIT_AND_SALES_SETUP note; the re-added 9k-line root `app.js` upload duplicate (deleted here too); root `test_dedicated_sub.py` (moved to `tests/` so CI runs it); the zero-width watermark comment line injected into `panel_providers/__init__.py`. |
| 2026-11-05 | 4.23.1 | CI fix only: the smoke job now installs `python-dotenv`, `aiohttp` and `cryptography`, because `tests/test_dedicated_sub.py` imports `config` and `panel_providers`. No product code changed; the 4.23.0 sync-log rows were added in this same commit. | Nothing new; the 4.23.0 exclusions still apply. |
| 2026-11-07 | 4.24.0 | Per-panel account naming (`account_naming.py`); smart buy guide (`buy_guide.py`); card-to-card UI (`card_payment_ui.py`); admin links menu (`admin_links.py`); unlimited forced-join channels (`force_join_channels.py`); related db/admin-panel/miniapp/web-store wiring and dedicated-sub HTML/client-reply hardening. Copied `admin_panel/static/settings_schema.py` onto root `settings_schema.py` for parity. | Upstream VERSION 8.8.6/8.9.2; deletion of AUDIT_AND_SALES_SETUP.fa.md (file was already absent on the fork); install.sh family; ru/zh; donation. |
| 2026-11-10 | 4.25.0 | Hourly system cron (`cron_checks.py`, wired in `bot_manager.py` and exposed as `/api/cron/status` + `/api/cron/run`); signup config gift (`welcome_gift.py`, `welcome_gift_queue` table with its DB methods, admin editor and the user `welcome_gift_claim` button); configurable emojis (`emoji_prefs.py` + admin emoji menu + per-category/product/test-plan emoji); Stealth VLESS panel type (`panel_providers/stealth_provider.py`, registered in PROVIDERS/TOKEN_ONLY/NO_SETUP with its secret prompt) with its standalone node installer and agent (`deploy/install-shopvpn-stealth.py`, `deploy/shopvpn-stealth-agent.py`); the web DB manager (tables, schema, WAL backup, SELECT-only console, masked columns, row edit/delete with pre-change backup, `_shopvpn_db_audit`, CSV/JSON export, JSON import, VACUUM, owner-only) plus `docs/database-manager.md`; sectioned admin hub with settings search (`ADMIN_HUB_SECTIONS`, `resolve_admin_category`, `admin_hub_text`, `admin_search_results`, `adm_hub:` / `adm_search`); broadcast section (single user, forward-all, targeting by service state, channel post, status/cancel, `/pin` + `/unpin`); per-config management (search, add/reduce volume and days, delete, dedicated-sub token); per-user test cap (`test_max_per_user`, `get_effective_test_limit`, override); product list layout/order toggles; test plans now provision through `direct_panel_provision` (`plan_to_product`). Bugfixes taken: `ai_support.py` honours the per-user test cap, `_migrate_test_config_plans` column migration, gift/test configs excluded from real-service counts. Wrote the missing `stealth_auto_install.py` (upstream calls it from six places but never shipped it). Restored the fork's `# -*- coding: utf-8 -*-` line 1 and the single `blupal_settings_kb`. Added 94 literal + 27 template English translations so `check_i18n_coverage.py` exits 0. Pinned all new modules in `UPSTREAM_FEATURE_MODULES` with real wiring assertions. | Upstream VERSION 9.0.0; `README.ru.md` / `README.zh.md` (fa/en only); the zero-width watermark lines upstream injects into `handlers_admin.py`, `force_join.py`, `config_delivery.py` and `panel_providers/__init__.py`; the duplicate `blupal_settings_kb` definition; the `deploy/` OVPN/WG units and auth scripts (the fork keeps its lean install flow); `test_stealth_node.py` and root `test_*.py` upload duplicates; upstream's `Create Test` / `Delete docs/Test` noise commits. No donation/crypto-wallet lines were present in this batch. |
| 2026-11-11 | 4.26.0 | Phone-prefix verification (`phone_gate.py`, bot callback middleware, miniapp `/api/phone/*`, confirm-contact handler); saved user groups (`db/user_groups.py`, `/api/user-groups*` CRUD + member/action endpoints); subscriptions page (`db/subscriptions.py`, `/api/subscriptions`, SSH account action); auto banners (`DEFAULT_AUTO_BANNERS` + panel UI); stealth node settings endpoints with upstream's stealth auto-install/agent updates (fork `renderSSHInstall` kept); report-topic flood/sync fallback and order-approval group sync. | Upstream VERSION 9.1.0; install.sh family and deploy SSH/OVPN/WG scripts; ru/zh docs; `stealth_auto_install.py` merged to upstream's validated version. |
| 2026-11-12 | 4.27.0 | Upstream 9.3.0: PayG billing (`payg.py` with five tables, `/payg` and `adm_payg`), Telegram widgets (`widgets.py`, `widgets_pro.py`, `widget_html.py`, `widget_html_pro.py`), bot profile description/short-description (`bot_profile.py`), category description media (`category_media.py`), delivery extras (per-product delivery text/sticker, VPN files and panel accounts on delivery), `telegram_media.py` album copying, scheduled broadcast with media and audience targeting, smart subscription, payment-card photo/description, admin-panel built assets with `_built_manifest`, web-store 3D scene modes, per-thread read-only SQLite connections in `db/_base.py`, the stealth-agent `adu` port/parse fix, plus the matching English i18n entries and integrity assertions. | Upstream VERSION 9.3.0; `README.ru.md`/`README.zh.md` (fa/en only); install/update scripts (unchanged); `admin_panel/build_assets.sh` and `fetch_fonts.py` (dev-only tooling; the built output itself is kept); the dead `miniapp_button_style` settings field; donation/crypto-wallet lines. |
| 2026-11-14 | 4.28.0 | Upstream 9.4.0: custom glass-menu buttons (`custom_menu_buttons.py`, `db/custom_menu.py` with its table and menu-order keys), pricing formulas / accounting mode (`accounting.py` plus `/api/accounting/panel-costs`), ticket and live-chat upgrade (priority, service reference, search, reopen, per-department counts in `db/tickets.py`, bot handlers and mini-app routes), web-admin TOTP 2FA with idle session refresh (`admin_panel/security.py`, `web_admins.totp_*`), the web-panel assistant (`web_assistant.py` with `ai_admin` tool injection), PayG multi-target/multi-node billing and panel-cost quotes, mini-app home tiles and home icons (`home_tiles.py`, `/api/home/config`, icon upload), category photos stored as Telegram `file_id`, ticket/support sort settings, the five new upstream tests moved into `tests/`, English i18n entries for every new Persian string, and the matching integrity/CI wiring assertions. | Upstream VERSION 9.4.0; `update.sh` / `update_runner.sh` / `admin_panel/build_assets.sh` (the fork keeps its own install/update flow); upstream `i18n_extra.py` (translated here instead); donation/crypto-wallet lines. |
