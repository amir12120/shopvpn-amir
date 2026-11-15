# -*- coding: utf-8 -*-
"""جایگزین سبک aiogram برای محیط تست محلی (CI خودِ aiogram را ندارد).

تست‌هایی که ماژول‌های وابسته به aiogram را import می‌کنند (report_router,
keyboards, bot_commands, ...) بدون نصب aiogram هم باید جمع‌آوری (collect) شوند.
اگر aiogram نصب باشد هیچ کاری نمی‌کند، پس در محیط واقعی همان کلاس‌های اصلی
مورد استفاده قرار می‌گیرند.
"""
import sys
import types

_Sub = None


class _StubBase(Exception):
    """هم کلاس داده (کیبورد/دکمه) هم قابل استفاده در except (خطاهای تلگرام)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args)
        for key, value in kwargs.items():
            setattr(self, key, value)
        self._args = args

    def __repr__(self):
        return "<%s %s>" % (type(self).__name__, vars(self))


class _StubModule(types.ModuleType):
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        cls = type(name, (_StubBase,), {})
        setattr(self, name, cls)
        return cls


def install() -> bool:
    """True اگر stub نصب شد (یعنی aiogram واقعی در دسترس نبود)."""
    global _Sub
    if _Sub is not None:
        return True
    try:
        import aiogram  # noqa: F401
        import aiogram.types  # noqa: F401
        return False
    except ImportError:
        pass

    root = _StubModule("aiogram")
    sys.modules["aiogram"] = root
    for dotted in (
        "aiogram.types", "aiogram.enums", "aiogram.exceptions", "aiogram.methods",
        "aiogram.fsm", "aiogram.fsm.state", "aiogram.fsm.context", "aiogram.fsm.storage",
        "aiogram.fsm.storage.memory", "aiogram.filters", "aiogram.client",
        "aiogram.client.session", "aiogram.client.session.aiohttp", "aiogram.utils",
        "aiogram.utils.keyboard", "aiogram.utils.exceptions", "aiogram.dispatcher",
    ):
        parent, _, leaf = dotted.rpartition(".")
        module = _StubModule(dotted)
        sys.modules[dotted] = module
        parent_module = sys.modules.get(parent)
        if parent_module is not None:
            setattr(parent_module, leaf, module)
    _Sub = root
    return True
