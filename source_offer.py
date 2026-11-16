# -*- coding: utf-8 -*-
"""Source-code offer required by the ShopVPN license (LICENSE, section 6).

If you modify ShopVPN and let people use your version through the bot, the mini app, the web
panel or the web store, you must offer them the source code of the version you run.
Set SHOPVPN_SOURCE_URL (in .env) to the public repository of YOUR version.
When it is empty the offer points at the repository of the code being run (this fork).
"""
import html
import os

OFFICIAL_REPO = "https://github.com/mehdirafatpanah/Shopvpn"
# The code running here is this fork, so an unset SHOPVPN_SOURCE_URL must not send
# admins to the upstream project: LICENSE section 6 asks for the source of the
# version actually served, which is this fork's repository.
FORK_REPO = "https://github.com/amir12120/shopvpn-amir"
LICENSE_NAME = "ShopVPN Source-Available Network Copyleft License 1.0"


def source_url() -> str:
    url = (os.getenv("SHOPVPN_SOURCE_URL") or "").strip()
    if not url.lower().startswith(("https://", "http://")):
        url = FORK_REPO
    return url


def license_url() -> str:
    base = source_url().rstrip("/")
    return f"{base}/blob/main/LICENSE" if "github.com" in base else base


def build_text(lang: str = "fa") -> str:
    """The /source answer: the repository address alone, with no extra wording.

    The text is sent with parse_mode=HTML, so the URL is escaped for HTML (it still
    renders as the plain address). ``lang`` is kept for the existing callers.
    """
    return html.escape(source_url(), quote=False)
