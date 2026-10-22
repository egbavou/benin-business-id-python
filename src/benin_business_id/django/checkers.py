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
normalized like the PHP service provider. The shared checker is rebuilt when the setting
changes, for example under override_settings().
"""

import threading
from collections.abc import Mapping
from typing import Any, Final

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.signals import setting_changed

from benin_business_id import ApiexSettings, IfuChecker, RccmChecker
from benin_business_id._settings import normalize

SETTING: Final = "BENIN_BUSINESS_ID"

_lock = threading.Lock()
_ifu_checker: Final = IfuChecker()
_rccm_checker: RccmChecker | None = None
_owns_rccm_checker = False


def get_ifu_checker() -> IfuChecker:
    return _ifu_checker


def get_rccm_checker() -> RccmChecker:
    global _rccm_checker, _owns_rccm_checker

    with _lock:
        if _rccm_checker is None:
            _rccm_checker, _owns_rccm_checker = _build_rccm_checker()

        return _rccm_checker


def reset_checkers() -> None:
    """Forget the shared RCCM checker, closing it when the integration created it."""
    global _rccm_checker, _owns_rccm_checker

    with _lock:
        if _rccm_checker is not None and _owns_rccm_checker:
            _rccm_checker.close()

        _rccm_checker = None
        _owns_rccm_checker = False


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
