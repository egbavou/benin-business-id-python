"""Shared checkers for the existence validators, the counterpart of the PHP service provider.

The RCCM checker is configured by the optional BENIN_BUSINESS_ID setting:

    BENIN_BUSINESS_ID = {
        "RCCM_APIEX": {
            "ENABLED": True,
            "TIMEOUT": 10,
            "COMPANIES_URL": "...",
            "ESTABLISHMENTS_URL": "...",
        },
        "RCCM_CHECKER": checker,  # optional RccmChecker instance, used as is
    }

A missing or None key falls back to the BENIN_RCCM_APIEX_* environment variables. Values are
normalized like the PHP service provider. The shared checker is replaced when the setting
changes, for example under override_settings(). A replaced checker that the integration
created is closed once the checks still using it are over.
"""

import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Final

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.signals import setting_changed

from benin_business_id import ApiexSettings, IfuChecker, RccmChecker
from benin_business_id._settings import normalize

SETTING: Final = "BENIN_BUSINESS_ID"


@dataclass
class _Shared:
    checker: RccmChecker
    owned: bool
    users: int = 0
    retired: bool = False

    def closable(self) -> bool:
        return self.owned and self.retired and self.users == 0


_lock = threading.Lock()
_ifu_checker: Final = IfuChecker()
_rccm: _Shared | None = None


def get_ifu_checker() -> IfuChecker:
    return _ifu_checker


def get_rccm_checker() -> RccmChecker:
    """The shared RCCM checker.

    It may be closed when the setting changes; the existence validators use
    borrowed_rccm_checker() instead, which keeps it open while they use it.
    """
    with _lock:
        return _current().checker


@contextmanager
def borrowed_rccm_checker() -> Iterator[RccmChecker]:
    """The shared RCCM checker, kept open until the block ends even if the setting changes."""
    with _lock:
        shared = _current()
        shared.users += 1

    try:
        yield shared.checker
    finally:
        with _lock:
            shared.users -= 1
            closable = shared.closable()

        if closable:
            shared.checker.close()


def reset_checkers() -> None:
    """Retire the shared RCCM checker; it is closed now or when its last check ends."""
    global _rccm

    with _lock:
        shared, _rccm = _rccm, None

        if shared is None:
            return

        shared.retired = True
        closable = shared.closable()

    if closable:
        shared.checker.close()


def _current() -> _Shared:
    """Return the shared checker, building it if needed. The caller holds the lock."""
    global _rccm

    if _rccm is None:
        checker, owned = _build_rccm_checker()
        _rccm = _Shared(checker, owned)

    return _rccm


def _build_rccm_checker() -> tuple[RccmChecker, bool]:
    config = _mapping(getattr(settings, SETTING, None), SETTING)
    checker = config.get("RCCM_CHECKER")

    if checker is not None:
        if not isinstance(checker, RccmChecker):
            raise ImproperlyConfigured(f"{SETTING}['RCCM_CHECKER'] must be an RccmChecker.")

        return checker, False

    apiex = _mapping(config.get("RCCM_APIEX"), f"{SETTING}['RCCM_APIEX']")
    environment = ApiexSettings.from_env()

    def pick(key: str, fallback: object) -> object:
        value = apiex.get(key)
        return fallback if value is None else value

    apiex_settings = normalize(
        enabled=pick("ENABLED", environment.enabled),
        timeout=pick("TIMEOUT", environment.timeout),
        companies_url=pick("COMPANIES_URL", environment.companies_url),
        establishments_url=pick("ESTABLISHMENTS_URL", environment.establishments_url),
    )

    return RccmChecker.from_settings(apiex_settings), True


def _mapping(value: object, name: str) -> Mapping[str, object]:
    if value is None:
        return {}

    if not isinstance(value, Mapping):
        raise ImproperlyConfigured(f"{name} must be a dict.")

    return value


def _on_setting_changed(*, setting: str, **kwargs: Any) -> None:
    if setting == SETTING:
        reset_checkers()


setting_changed.connect(_on_setting_changed, dispatch_uid="benin_business_id.django.checkers")
