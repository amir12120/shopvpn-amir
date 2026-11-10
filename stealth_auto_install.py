# -*- coding: utf-8 -*-
"""نصب خودکار نود «Stealth VLESS» روی سرور تازه (Debian/Ubuntu، root).

upstream روت‌های `/api/stealth/nodes/auto-install` و
`/api/stealth/nodes/install-jobs/{job_id}` را در `admin_panel/server.py` صدا می‌زند
اما ماژول `stealth_auto_install` را در مخزن جا انداخته است. این فایل همان قرارداد
را با همان الگوی `ssh_auto_install.py` پیاده می‌کند:

- `InstallError`، `start_install(db, ...) -> job_id`، `get_job(job_id)`
- آپلود `deploy/install-shopvpn-stealth.py` و `deploy/shopvpn-stealth-agent.py`
  روی سرور و اجرای نصاب با آرگومان‌های امن (بدون shell injection)
- خواندن آدرس API و توکن از `/etc/shopvpn-stealth/node.json` روی سرور
- ثبت پنل با `panel_type="stealth"` و تست اتصال

رمز root و کلید خصوصی فقط داخل closure تسک می‌مانند و هیچ‌جا لاگ نمی‌شوند.
"""
import asyncio
import json
import logging
import os
import re
import secrets

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
_FILES = (
    "deploy/install-shopvpn-stealth.py",
    "deploy/shopvpn-stealth-agent.py",
)
REMOTE_DIR = "/tmp/shopvpn-stealth-install"
NODE_JSON = "/etc/shopvpn-stealth/node.json"
ALLOWED_TRANSPORTS = ("ws", "httpupgrade", "grpc", "xhttp")
ALLOWED_DECOYS = ("movie", "proxy")
ALLOWED_CERTS = ("letsencrypt", "file", "self")

_MAX_JOBS = 30
_JOBS = {}


class InstallError(Exception):
    """خطای قابل‌نمایش برای ادمین؛ پیامش مستقیم به HTTPException می‌رود."""


def _new_job() -> dict:
    job = {
        "id": secrets.token_hex(8),
        "status": "running",
        "log": [],
        "panel_id": None,
        "warning": None,
        "error": None,
    }
    _JOBS[job["id"]] = job
    while len(_JOBS) > _MAX_JOBS:
        _JOBS.pop(next(iter(_JOBS)))
    return job


def get_job(job_id: str):
    job = _JOBS.get(job_id)
    if not job:
        return None
    return {k: job[k] for k in ("id", "status", "log", "panel_id", "warning", "error")}


def _log(job, text: str):
    job["log"].append(str(text)[:400])


def _clean_domain(value: str) -> str:
    domain = (value or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9]([a-z0-9.-]{0,251}[a-z0-9])?", domain) or "." not in domain:
        raise InstallError("دامنه نامعتبر است (مثلاً cdn.example.com).")
    return domain


def start_install(db, *, name, host, ssh_port=22, password=None, private_key=None, domain,
                  decoy="movie", proxy_url=None, cert="letsencrypt", email="",
                  transports=None, port=443, title="Stealth", site_name="CineVault") -> str:
    """یک جاب پس‌زمینه می‌سازد و شناسه‌اش را برمی‌گرداند."""
    name = (name or "").strip()
    host = (host or "").strip()
    if not name:
        raise InstallError("نام نود الزامی است.")
    if not host:
        raise InstallError("آدرس سرور (IP یا هاست) الزامی است.")
    if not (password or private_key):
        raise InstallError("رمز root یا کلید خصوصی را وارد کنید.")
    domain = _clean_domain(domain)

    wanted = [t for t in ALLOWED_TRANSPORTS if t in (transports or ["ws", "httpupgrade", "grpc"])]
    if not wanted:
        raise InstallError("حداقل یک ترنسپورت (ws، httpupgrade، grpc یا xhttp) انتخاب کنید.")
    if str(decoy) not in ALLOWED_DECOYS:
        raise InstallError("نوع سایت جعلی باید movie یا proxy باشد.")
    if str(cert) not in ALLOWED_CERTS:
        raise InstallError("نوع گواهی باید letsencrypt، file یا self باشد.")
    if str(decoy) == "proxy":
        if not proxy_url or not re.match(r"^https?://[^/\s]+", proxy_url):
            raise InstallError("برای سایت جعلی proxy، آدرس معتبر (https://...) لازم است.")
    try:
        ssh_port = int(ssh_port)
        port = int(port)
    except (TypeError, ValueError) as exc:
        raise InstallError("پورت نامعتبر است.") from exc
    if not 1 <= ssh_port <= 65535 or not 1 <= port <= 65535:
        raise InstallError("پورت نامعتبر است.")

    job = _new_job()

    async def _runner():
        try:
            await _install(db, job, name=name, host=host, ssh_port=ssh_port, password=password,
                           private_key=private_key, domain=domain, decoy=str(decoy),
                           proxy_url=(proxy_url or "").strip() or None, cert=str(cert),
                           email=(email or "").strip(), transports=wanted, port=port,
                           title=(title or "Stealth").strip(), site_name=(site_name or "CineVault").strip())
            job["status"] = "done"
        except InstallError as exc:
            job["status"] = "error"
            job["error"] = str(exc)
        except Exception as exc:  # هرگز رمز یا کلید را لو نده
            logger.exception("Stealth node auto-install failed")
            job["status"] = "error"
            job["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"

    task = asyncio.get_running_loop().create_task(_runner())
    job["_task"] = task  # مرجع نگه داشته شود تا جمع‌آوری نشود
    return job["id"]


async def _install(db, job, *, name, host, ssh_port, password, private_key, domain, decoy,
                   proxy_url, cert, email, transports, port, title, site_name):
    try:
        import asyncssh
    except ImportError as exc:
        raise InstallError("کتابخانه asyncssh نصب نیست (pip install asyncssh).") from exc
    from panel_providers import get_provider

    kwargs = dict(host=host, port=ssh_port, username="root", known_hosts=None, connect_timeout=20)
    if private_key:
        try:
            kwargs["client_keys"] = [asyncssh.import_private_key(private_key)]
        except Exception as exc:
            raise InstallError("کلید خصوصی نامعتبر است.") from exc
    else:
        kwargs["password"] = password
        kwargs["client_keys"] = None

    _log(job, f"اتصال به {host}:{ssh_port} ...")
    try:
        conn = await asyncssh.connect(**kwargs)
    except asyncssh.PermissionDenied as exc:
        raise InstallError("احراز هویت SSH ناموفق بود (رمز یا کلید اشتباه است).") from exc
    except (OSError, asyncssh.Error, asyncio.TimeoutError) as exc:
        raise InstallError(f"اتصال SSH برقرار نشد: {type(exc).__name__}") from exc

    async with conn:
        async def run(cmd, timeout=1800, check=True):
            try:
                res = await asyncio.wait_for(conn.run(cmd, check=False), timeout)
            except asyncio.TimeoutError as exc:
                raise InstallError("زمان اجرای دستور روی سرور تمام شد.") from exc
            if check and res.exit_status != 0:
                tail = ((res.stderr or "") + (res.stdout or "")).strip()[-400:]
                raise InstallError(f"دستور روی سرور شکست خورد: {tail}")
            return (res.stdout or "").strip()

        osr = (await run("cat /etc/os-release", check=False)).lower()
        if "debian" not in osr and "ubuntu" not in osr:
            raise InstallError("فقط Debian/Ubuntu پشتیبانی می‌شود.")

        _log(job, "آپلود نصاب و ایجنت...")
        await run(f"rm -rf {REMOTE_DIR} && mkdir -p {REMOTE_DIR}/deploy")
        async with conn.start_sftp_client() as sftp:
            for rel in _FILES:
                local = os.path.join(_PROJECT_ROOT, rel)
                if not os.path.isfile(local):
                    raise InstallError(f"فایل نصب روی پنل پیدا نشد: {rel}")
                await sftp.put(local, f"{REMOTE_DIR}/{rel}")

        # آرگومان‌ها با shlex.quote امن می‌شوند؛ هیچ ورودی کاربر خام اجرا نمی‌شود.
        import shlex
        argv = [
            "python3", f"{REMOTE_DIR}/deploy/install-shopvpn-stealth.py",
            "--domain", domain,
            "--port", str(port),
            "--transports", ",".join(transports),
            "--decoy", decoy,
            "--cert", cert,
            "--title", title,
            "--site-name", site_name,
        ]
        if proxy_url:
            argv += ["--proxy-url", proxy_url]
        if email:
            argv += ["--email", email]
        cmd = " ".join(shlex.quote(a) for a in argv)

        _log(job, f"اجرای نصاب (دامنه {domain}، ترنسپورت {', '.join(transports)}) — چند دقیقه طول می‌کشد...")
        await run(cmd, timeout=2400)

        _log(job, "خواندن آدرس API و توکن از سرور...")
        raw = await run(f"cat {NODE_JSON}", check=False)
        try:
            node = json.loads(raw)
        except ValueError as exc:
            raise InstallError(f"فایل {NODE_JSON} روی سرور خوانده نشد.") from exc
        api_path = str(node.get("api_path") or "").strip()
        api_token = str(node.get("api_token") or "").strip()
        if not api_path or not api_token:
            raise InstallError("آدرس API یا توکن در node.json پیدا نشد.")

        api_url = f"https://{domain}" + ("" if port == 443 else f":{port}") + f"/{api_path}"
        _log(job, "ثبت پنل Stealth در دیتابیس...")
        panel_id = db.add_panel_server(name, "stealth", api_url, "stealth", api_token, None)

        _log(job, "تست اتصال به ایجنت...")
        ok = False
        err = ""
        for _ in range(5):
            try:
                ok, err = await get_provider(db.get_panel_server(panel_id)).check_connection()
                if ok:
                    break
            except Exception as exc:
                err = f"{type(exc).__name__}: {str(exc)[:160]}"
            await asyncio.sleep(2)
        if not ok:
            job["panel_id"] = panel_id
            raise InstallError(
                "نود نصب شد ولی تست اتصال ناموفق بود. پنل با شناسه "
                f"{panel_id} ثبت شد؛ فایروال/کلادفلر پورت {port} را بررسی کنید."
                + (f" ({err})" if err else "")
            )

    job["panel_id"] = panel_id
    _log(job, "نود Stealth آماده است ✅")
