"""Differential test: the PHP package is the executable reference (design, section 13.2).

Excluded by default and from CI. Run it with `pytest -m parity`; it needs `php` and the PHP
package installed with its development dependencies, in ../benin-business-id or in
BENIN_BUSINESS_ID_PHP_DIR.
"""

import asyncio
import base64
import json
import math
import os
import shutil
import subprocess
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from tests.httpx_integration.support import FakeApiex, NoQueuedResponseError, route_owned_clients
from tests.parity import generate

from benin_business_id import (
    AsyncRccmChecker,
    DirectoryError,
    Ifu,
    InvalidIdentifierError,
    Rccm,
    RccmChecker,
    RccmCheckResult,
    UnavailableReason,
)
from benin_business_id._clock import current_year
from benin_business_id._settings import ApiexSettings, normalize

pytestmark = pytest.mark.parity

PHP_DIRECTORY = Path(
    os.environ.get(
        "BENIN_BUSINESS_ID_PHP_DIR", Path(__file__).resolve().parents[3] / "benin-business-id"
    )
)
ORACLE = Path(__file__).with_name("oracle.php")
# Written out rather than read from the packages: the only intended request difference (P1).
PHP_USER_AGENT = "egbavou/benin-business-id (+https://github.com/egbavou/benin-business-id)"
PYTHON_USER_AGENT = (
    "egbavou/benin-business-id-python (+https://github.com/egbavou/benin-business-id-python)"
)
ENV_VARIABLES = (
    "BENIN_RCCM_APIEX_ENABLED",
    "BENIN_RCCM_APIEX_TIMEOUT",
    "BENIN_RCCM_APIEX_COMPANIES_URL",
    "BENIN_RCCM_APIEX_ESTABLISHMENTS_URL",
)
SEED = 20261022


class InjectedTransportError(Exception):
    pass


def run_oracle(cases: list[dict[str, object]]) -> list[dict[str, object]]:
    php = shutil.which("php")

    if php is None or not (PHP_DIRECTORY / "vendor/autoload.php").is_file():
        pytest.skip("php and the PHP package with its dev dependencies are required")

    # The oracle must not inherit the developer's own APIEx configuration.
    environment = {key: value for key, value in os.environ.items() if key not in ENV_VARIABLES}
    completed = subprocess.run(
        [php, str(ORACLE)],
        input=json.dumps(cases),
        capture_output=True,
        text=True,
        check=True,
        env={**environment, "BENIN_BUSINESS_ID_PHP_DIR": str(PHP_DIRECTORY)},
    )
    results: list[dict[str, object]] = json.loads(completed.stdout)

    return results


def compare(
    cases: Iterable[dict[str, object]], expected: list[dict[str, object]], actual: list[object]
) -> None:
    mismatches = [
        (case, php, python)
        for case, php, python in zip(cases, expected, actual, strict=True)
        if php != python
    ]

    assert not mismatches, (
        "\n\n".join(
            f"case: {case!r}\nphp:    {php!r}\npython: {python!r}"
            for case, php, python in mismatches[:5]
        )
        + f"\n\n{len(mismatches)} mismatches"
    )


def identifier(operation: str, raw: str) -> dict[str, object]:
    try:
        parsed = Ifu(raw) if operation == "ifu" else Rccm(raw)
    except InvalidIdentifierError as error:
        return {"ok": False, "reason": error.reason.value}

    if isinstance(parsed, Ifu):
        return {
            "ok": True,
            "value": parsed.value,
            "taxpayer_type": parsed.taxpayer_type.value.title().replace("_", ""),
            "registration_year": parsed.registration_year,
        }

    return {
        "ok": True,
        "value": parsed.value,
        "registry_code": parsed.registry_code,
        "year": parsed.year,
        "category": parsed.category,
        "sequence_number": parsed.sequence_number,
    }


def failure(error: Exception | None) -> str | None:
    """Classify the exception itself, the way the oracle classifies the PHP one."""
    if error is None:
        return None

    if isinstance(error, DirectoryError):
        return f"directory:{error}"

    if isinstance(error, InjectedTransportError):
        return "injected"

    if isinstance(error, NoQueuedResponseError):
        return "exhausted"

    # json.JSONDecodeError, UnicodeDecodeError and the package's own decoding errors.
    if isinstance(error, ValueError | RecursionError):
        return "json"

    return "other"


def user_agent(request: httpx.Request) -> str:
    value = request.headers["User-Agent"]

    return PHP_USER_AGENT if value == PYTHON_USER_AGENT else value


def responses(case: dict[str, object]) -> Iterator[httpx.Response | BaseException]:
    for spec in case["responses"]:  # type: ignore[attr-defined]
        if spec.get("throw"):
            yield InjectedTransportError("Injected transport failure.")
        else:
            yield httpx.Response(
                spec["status"],
                headers=spec.get("headers", {}),
                content=base64.b64decode(spec["body"]),
            )


def run_check(case: dict[str, object], mode: str) -> RccmCheckResult:
    enabled = bool(case["enabled"])
    companies_url = str(case["companies_url"])
    establishments_url = str(case["establishments_url"])
    value = str(case["input"])

    if mode == "sync":
        with RccmChecker(
            enabled=enabled, companies_url=companies_url, establishments_url=establishments_url
        ) as checker:
            return checker.check(value)

    async def run() -> RccmCheckResult:
        async with AsyncRccmChecker(
            enabled=enabled, companies_url=companies_url, establishments_url=establishments_url
        ) as checker:
            return await checker.check(value)

    return asyncio.run(run())


def check(case: dict[str, object], mode: str, monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """Run a case on the client the checker creates itself, routed to a fake directory."""
    fake = FakeApiex(list(responses(case)))
    route_owned_clients(monkeypatch, fake)

    before = datetime.now(UTC)
    result = run_check(case, mode)
    after = datetime.now(UTC)

    return {
        "status": result.status.value,
        "input": result.input,
        "rccm": result.rccm.value if result.rccm else None,
        "name": result.name,
        "trade_name": result.trade_name,
        "creation_date": result.creation_date.isoformat() if result.creation_date else None,
        "municipality": result.municipality,
        "district": result.district,
        "phone": result.phone,
        "email": result.email,
        "main_activity": result.main_activity,
        "former_number": result.former_number,
        "register": result.register.value if result.register else None,
        "unavailable_reason": result.unavailable_reason.value
        if result.unavailable_reason
        else None,
        "failure": failure(result.failure),
        "checked_at_ok": result.checked_at.tzinfo is UTC and before <= result.checked_at <= after,
        "requests": [
            {
                "method": request.method,
                "url": str(request.url),
                "user_agent": user_agent(request),
                "accept": request.headers["Accept"],
            }
            for request in fake.requests
        ],
    }


def settings_projection(settings: ApiexSettings) -> dict[str, object]:
    return {
        "enabled": settings.enabled,
        "timeout": "INF" if math.isinf(settings.timeout) else settings.timeout,
        "companies_url": settings.companies_url,
        "establishments_url": settings.establishments_url,
    }


@pytest.fixture(autouse=True)
def stable_year() -> Iterator[None]:
    year = current_year()
    yield
    if current_year() != year:
        pytest.skip("the year changed while the PHP and Python results were computed")


def test_identifiers_match_the_php_package() -> None:
    inputs = generate.identifier_inputs(SEED)
    cases: list[dict[str, object]] = [{"op": operation, "input": raw} for operation, raw in inputs]

    expected = run_oracle(cases)

    assert len(cases) > 7000
    compare(cases, expected, [identifier(operation, raw) for operation, raw in inputs])


@pytest.mark.parametrize("mode", ["sync", "async"])
def test_checks_match_the_php_package(mode: str, monkeypatch: pytest.MonkeyPatch) -> None:
    cases = generate.check_cases(SEED)

    expected = run_oracle(cases)
    actual = [check(case, mode, monkeypatch) for case in cases]

    statuses = {str(result["status"]) for result in expected}
    reasons = {str(result["unavailable_reason"]) for result in expected}
    assert statuses == {"found", "not_found", "invalid_format", "unavailable"}
    assert reasons >= {value.value for value in UnavailableReason} - {"no_source"}
    assert all(result["checked_at_ok"] is True for result in expected)
    compare(cases, expected, list(actual))


def test_environment_settings_match_the_php_service_provider() -> None:
    cases = generate.environment_cases(SEED)

    expected = run_oracle(cases)
    actual = [
        settings_projection(ApiexSettings.from_env(case["environ"]))  # type: ignore[arg-type]
        for case in cases
    ]

    compare(cases, expected, list(actual))


def test_typed_setting_values_match_the_php_service_provider() -> None:
    cases = generate.value_cases(SEED)

    expected = run_oracle(cases)
    actual = [
        settings_projection(
            normalize(
                enabled=case["enabled"],
                timeout=case["timeout"],
                companies_url=case["companies_url"],
                establishments_url=case["establishments_url"],
            )
        )
        for case in cases
    ]

    compare(cases, expected, list(actual))
