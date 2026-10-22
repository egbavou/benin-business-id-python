import math

import pytest

from benin_business_id import (
    DEFAULT_COMPANIES_URL,
    DEFAULT_ESTABLISHMENTS_URL,
    DEFAULT_TIMEOUT,
    ApiexSettings,
)

ENABLED = "BENIN_RCCM_APIEX_ENABLED"
TIMEOUT = "BENIN_RCCM_APIEX_TIMEOUT"
COMPANIES = "BENIN_RCCM_APIEX_COMPANIES_URL"
ESTABLISHMENTS = "BENIN_RCCM_APIEX_ESTABLISHMENTS_URL"


def test_disables_verification_by_default() -> None:
    settings = ApiexSettings()

    assert settings == ApiexSettings.from_env({})
    assert settings.enabled is False
    assert settings.timeout == DEFAULT_TIMEOUT == 10.0
    assert settings.companies_url == DEFAULT_COMPANIES_URL
    assert settings.establishments_url == DEFAULT_ESTABLISHMENTS_URL
    assert DEFAULT_COMPANIES_URL == "https://gdb.guichet.investbenin.bj/data-view/pm/latest/5"
    assert DEFAULT_ESTABLISHMENTS_URL == (
        "https://gdb.monentreprise.bj/data-view/registre%20pp/latest/310"
    )


def test_reads_os_environ_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENABLED, "true")
    monkeypatch.setenv(TIMEOUT, "3.5")

    settings = ApiexSettings.from_env()

    assert settings.enabled is True
    assert settings.timeout == 3.5


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("true", True),
        ("(true)", True),
        ("TRUE", True),
        ("1", True),
        ("yes", True),
        ("on", True),
        (" on ", True),
        ("'yes'", True),
        ("false", False),
        ("0", False),
        ("no", False),
        ("maybe", False),
        ("", False),
        ("null", False),
        ("empty", False),
    ],
)
def test_reads_the_switch(value: str, expected: bool) -> None:
    assert ApiexSettings.from_env({ENABLED: value}).enabled is expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("5", 5.0),
        (" 2.5 ", 2.5),
        ("1e309", math.inf),
        ("'7'", 7.0),
        ("0", 10.0),
        ("-1", 10.0),
        ("abc", 10.0),
        ("true", 10.0),
        ("", 10.0),
        ("null", 10.0),
        ("0x1A", 10.0),
    ],
)
def test_reads_the_timeout_with_a_fallback(value: str, expected: float) -> None:
    assert ApiexSettings.from_env({TIMEOUT: value}).timeout == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://example.test/companies", "https://example.test/companies"),
        ("'https://example.test/quoted'", "https://example.test/quoted"),
        ("", DEFAULT_COMPANIES_URL),
        ("empty", DEFAULT_COMPANIES_URL),
        ("null", DEFAULT_COMPANIES_URL),
        ("true", DEFAULT_COMPANIES_URL),
    ],
)
def test_reads_the_urls_with_a_fallback(value: str, expected: str) -> None:
    settings = ApiexSettings.from_env({COMPANIES: value, ESTABLISHMENTS: value})

    assert settings.companies_url == expected
    assert settings.establishments_url == expected.replace(
        DEFAULT_COMPANIES_URL, DEFAULT_ESTABLISHMENTS_URL
    )
