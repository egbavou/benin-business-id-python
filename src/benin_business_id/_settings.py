import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, final

from benin_business_id import _php

DEFAULT_COMPANIES_URL: Final = "https://gdb.guichet.investbenin.bj/data-view/pm/latest/5"
DEFAULT_ESTABLISHMENTS_URL: Final = (
    "https://gdb.monentreprise.bj/data-view/registre%20pp/latest/310"
)
DEFAULT_TIMEOUT: Final = 10.0

ENABLED_VARIABLE: Final = "BENIN_RCCM_APIEX_ENABLED"
TIMEOUT_VARIABLE: Final = "BENIN_RCCM_APIEX_TIMEOUT"
COMPANIES_URL_VARIABLE: Final = "BENIN_RCCM_APIEX_COMPANIES_URL"
ESTABLISHMENTS_URL_VARIABLE: Final = "BENIN_RCCM_APIEX_ESTABLISHMENTS_URL"


@final
@dataclass(frozen=True, slots=True, kw_only=True)
class ApiexSettings:
    """Configuration of the APIEx directory check. Verification is disabled by default."""

    enabled: bool = False
    timeout: float = DEFAULT_TIMEOUT
    companies_url: str = DEFAULT_COMPANIES_URL
    establishments_url: str = DEFAULT_ESTABLISHMENTS_URL

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "ApiexSettings":
        """Read the BENIN_RCCM_APIEX_* variables, as the PHP package's Laravel config does.

        environ defaults to os.environ. Values are read like Laravel's env() helper, then
        normalized like the PHP service provider: an unknown switch value means disabled,
        and an invalid timeout or an empty URL falls back to its default.
        """
        variables = os.environ if environ is None else environ

        return normalize(
            enabled=_php.env_value(variables, ENABLED_VARIABLE, False),
            timeout=_php.env_value(variables, TIMEOUT_VARIABLE, 10),
            companies_url=_php.env_value(variables, COMPANIES_URL_VARIABLE, DEFAULT_COMPANIES_URL),
            establishments_url=_php.env_value(
                variables, ESTABLISHMENTS_URL_VARIABLE, DEFAULT_ESTABLISHMENTS_URL
            ),
        )


def normalize(
    *, enabled: object, timeout: object, companies_url: object, establishments_url: object
) -> ApiexSettings:
    """Build settings from loosely typed values, normalized like the PHP service provider."""
    return ApiexSettings(
        enabled=_php.filter_bool(enabled),
        timeout=_timeout(timeout),
        companies_url=_url(companies_url, DEFAULT_COMPANIES_URL),
        establishments_url=_url(establishments_url, DEFAULT_ESTABLISHMENTS_URL),
    )


def _timeout(value: object) -> float:
    number = _php.numeric_value(value)

    # A NaN fails the comparison and falls back, like `(float) $timeout > 0` in PHP.
    return number if number is not None and number > 0 else DEFAULT_TIMEOUT


def _url(value: object, default: str) -> str:
    return value if isinstance(value, str) and value != "" else default
