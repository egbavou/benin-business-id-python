# benin-business-id

Offline validation of Beninese business identifiers (IFU and RCCM) for Python 3.11+, with optional RCCM existence checks against the public APIEx directory, and optional Django and Pydantic integrations. It is the Python port of the PHP package `egbavou/benin-business-id` and gives the same results: same accepted input, same checks in the same order, same failure reasons, same requests to APIEx and same check outcomes.

```bash
pip install benin-business-id
pip install "benin-business-id[httpx]"     # RCCM existence checks (sync and async)
pip install "benin-business-id[django]"    # Django validators and form fields
pip install "benin-business-id[pydantic]"  # Pydantic v2 types
```

The core has no dependencies.

## Validate a format

```python
from benin_business_id import FailureReason, Ifu, InvalidIdentifierError, Rccm, TaxpayerType

Ifu.is_valid("3202444139959")  # True
Ifu.try_parse("invalid")  # None

ifu = Ifu("3.201.200.247.219")
ifu.value  # '3201200247219'
ifu.taxpayer_type  # TaxpayerType.COMPANY
ifu.registration_year  # 2012

rccm = Rccm("RB/COT/07-B-1432")
rccm.value  # 'RB/COT/07 B 1432'
rccm.format()  # 'RB/COT/07 B 1432'
rccm.registry_code  # 'COT'
rccm.year  # 2007
rccm.category  # 'B'
rccm.sequence_number  # '1432'

try:
    Rccm("RB/OUI/22 B 12")
except InvalidIdentifierError as error:  # a ValueError
    error.reason  # FailureReason.UNKNOWN_REGISTRY
    error.reason.value  # 'unknown_registry'
    str(error)  # 'Invalid RCCM: unknown_registry.'
```

The constructor validates and normalizes its input, and raises `InvalidIdentifierError` when it is invalid. `try_parse()` returns `None` instead, and `is_valid()` returns a boolean. Instances are immutable, hashable and compare by normalized value. A value that is not a `str` raises `TypeError`: nothing is converted. Format validation never makes network requests and does not establish existence.

`FailureReason` values are stable snake_case codes: `invalid_characters`, `invalid_length`, `invalid_checksum` (never produced for Benin), `unknown_taxpayer_type`, `invalid_year`, `invalid_country`, `unknown_registry`, `unknown_category` and `invalid_structure`.

### IFU rules

The rule declared by the State, checked in this order:

1. Spaces, dots and hyphens are removed. The space set is exactly what PHP's `\s` matches with the `u` modifier: U+0009 to U+000D, U+0020, U+0085, U+00A0, U+1680, U+180E, U+2000 to U+200A, U+2028, U+2029, U+202F, U+205F and U+3000. Unlike `str.isspace()`, it excludes U+001C to U+001F. Prefixes such as `IFU :` or `BJ-IFU-` are not removed.
2. Only ASCII digits remain (`invalid_characters`), 13 of them (`invalid_length`).
3. The first digit is the taxpayer type, 0 to 6 (`unknown_taxpayer_type`): `INDIVIDUAL` (0, 1 or 2), `COMPANY` (3), `PUBLIC_ENTITY` (4), `INTERNATIONAL_ORGANIZATION` (5) and `NGO` (6).
4. Digits 2 to 5 are the registration year, from 2006 through the current UTC year (`invalid_year`).

The last digit is a check digit whose algorithm has never been published: it is not verified.

### RCCM rules

The strict rule drawn from the official register:

1. Spaces (same set as above), dots and hyphens are removed and ASCII letters are uppercased; `/` is kept. Anything other than `A-Z`, `0-9` and `/` fails (`invalid_characters`); prefixes such as `RCCM :` and annotations such as `(Ancien n° …)` are therefore rejected.
2. The structure is country, registry, year, category letter and sequence number (`invalid_structure`), with at most 6 sequence digits (`invalid_length`).
3. The country is `RB` (`invalid_country`).
4. The registry is one of `COT`, `ABC`, `PNO`, `PKO`, `ABY`, `LKS`, `NAT`, `DGO`, `KDI`, `APL` and `SVL`, or one of the former codes `PN`, `PK`, `ODH`, `POB` and `ALD` for numbers through 2020 (`unknown_registry`).
5. The category is `A` to `E` (`unknown_category`).
6. The year has 2 digits, or 4 digits through 2020, and lies between 1990 and the current year (`invalid_year`).

The normalized value is the register's own form, `RB/COT/18 B 22272`; the year spelling and the leading zeros of the sequence number are kept.

## Check existence

```python
import httpx
from benin_business_id import AsyncRccmChecker, IfuChecker, RccmChecker

with RccmChecker(enabled=True) as checker:  # creates its own client (10 s timeout)
    result = checker.check("RB/COT/18 B 22272")

result.status  # CheckStatus.FOUND, NOT_FOUND, INVALID_FORMAT or UNAVAILABLE
result.input  # the string received (or the value of an Rccm received)
result.rccm  # the parsed Rccm; None for INVALID_FORMAT
result.checked_at  # timezone-aware datetime, in UTC
result.unavailable_reason  # UnavailableReason; None unless UNAVAILABLE
result.failure  # the exception behind a technical failure; None otherwise

with httpx.Client(timeout=5) as client:  # or inject your own client
    RccmChecker(client, enabled=True).check("RB/COT/18 B 22272")

async with AsyncRccmChecker(enabled=True) as checker:  # same behaviour, on httpx.AsyncClient
    await checker.check("RB/COT/18 B 22272")

IfuChecker().check("3202444139959").unavailable_reason  # UnavailableReason.NO_SOURCE
```

RCCM verification is **disabled by default**: without `enabled=True` a valid number is `UNAVAILABLE` with the `DISABLED` reason, and no client is created. `checker.enabled` reports the switch. A check never raises: technical failures return `UNAVAILABLE`. Only a value that is neither a `str` nor an `Rccm` raises `TypeError`, and `KeyboardInterrupt` or `asyncio.CancelledError` propagate.

A `FOUND` result exposes `name`, `trade_name`, `creation_date` (a `datetime.date`), `municipality`, `district`, `phone`, `email`, `main_activity`, `former_number` and `register` (`RccmRegister.COMPANIES` or `ESTABLISHMENTS`). These fields are `None` for every other status. Results from the establishments register never carry the owner's name, phone or email. Results from the companies register are returned as APIEx publishes them, including for category A or E numbers.

APIEx is an **undocumented source**: its endpoints, schema and coverage can change. `NOT_FOUND` means absent from this directory and **is not proof of non-existence**. A stored number with leading zeros and a parenthetical annotation is only found when the input also includes those zeros. Obtain written authorisation from APIEx before production use.

IFU existence returns `UNAVAILABLE` with `NO_SOURCE` until an authorised DGI source exists; invalid input returns `INVALID_FORMAT`. CAPTCHA-protected services are never queried. `AsyncIfuChecker` is its asynchronous counterpart.

### Unavailable reasons

`unavailable_reason` is set exactly when the status is `UNAVAILABLE`:

| Enum member | Value | Meaning |
| --- | --- | --- |
| `NO_SOURCE` | `no_source` | IFU only: no authorised IFU source exists yet. |
| `DISABLED` | `disabled` | Online verification is switched off. |
| `TRANSPORT` | `transport` | Failure before a complete response is received, including request construction and a body cut off by the network. |
| `HTTP_STATUS` | `http_status` | The server returned a status other than 200. Redirects are never followed. |
| `INVALID_JSON` | `invalid_json` | The body is not JSON that PHP's `json_decode()` would accept. |
| `SCHEMA` | `schema` | Unexpected JSON shape, incomplete results with no match, or any other error while processing a 200 response. |

`failure` holds the original exception for `TRANSPORT` (for example `httpx.ConnectError`), `INVALID_JSON` and processing errors classified as `SCHEMA`. For `HTTP_STATUS` and schema rejections without an original exception, it holds a `DirectoryError` with a clear message, for example `APIEx returned HTTP 503.`. Messages generated by the package never include response bodies or personal data. `failure` is `None` for `FOUND`, `NOT_FOUND`, `INVALID_FORMAT` and `DISABLED`.

### HTTP client and timeouts

A check makes up to **4 sequential GET requests**. The request carries only `Host`, `User-Agent` and `Accept`; the client's default headers, parameters and cookies are not applied, while its timeout, authentication, proxy, TLS settings, transport and event hooks are. The checker never closes an injected client; `close()` / `aclose()` (or the context manager) release a client it created.

httpx timeouts apply to each operation (connect, each read, write, pool), not to the whole request: a server that keeps sending data slowly can make a request last longer than the timeout. Enforce an overall deadline yourself if you need one. Passing `timeout` together with a client raises `ValueError`: an injected client keeps its own.

### Configuration

```python
from benin_business_id import ApiexSettings, RccmChecker

settings = ApiexSettings.from_env()  # reads os.environ, or the mapping you pass
checker = RccmChecker.from_settings(settings)
```

| Environment variable | Default |
| --- | --- |
| `BENIN_RCCM_APIEX_ENABLED` | `false` |
| `BENIN_RCCM_APIEX_TIMEOUT` | `10` seconds |
| `BENIN_RCCM_APIEX_COMPANIES_URL` | `https://gdb.guichet.investbenin.bj/data-view/pm/latest/5` |
| `BENIN_RCCM_APIEX_ESTABLISHMENTS_URL` | `https://gdb.monentreprise.bj/data-view/registre%20pp/latest/310` |

Values are read like the PHP package's Laravel configuration: `true`, `1`, `on` and `yes` enable verification, any other value disables it; a timeout that is not a positive number and an empty URL fall back to their defaults. Nothing is read at import time.

## Django

Django 5.2 or later. Add the app to get the French messages (without it, messages are in English):

```python
INSTALLED_APPS = [
    # ...
    "benin_business_id.django",
]
```

Form fields clean values into `Ifu` / `Rccm` objects (or `None` when empty):

```python
from django import forms
from benin_business_id.django.forms import IfuField, RccmField


class CompanyForm(forms.Form):
    ifu = IfuField()
    rccm = RccmField()


form = CompanyForm(data={"ifu": "3.201.200.247.219", "rccm": "RB/COT/07-B-1432"})
form.is_valid()  # True
form.cleaned_data["rccm"]  # Rccm(value='RB/COT/07 B 1432')
```

Validators work on model fields and are serializable in migrations:

```python
from django.db import models
from benin_business_id.django.validators import IfuValidator, RccmExistsValidator, RccmValidator


class Company(models.Model):
    ifu = models.CharField(max_length=13, validators=[IfuValidator()])
    rccm = models.CharField(
        max_length=30,
        validators=[RccmValidator(), RccmExistsValidator(fail_when_unavailable=True)],
    )
```

Each error carries its reason as its `code`. A value that is not a string fails with the `invalid_characters` message.

`IfuExistsValidator` and `RccmExistsValidator` reject invalid formats and `NOT_FOUND`. `UNAVAILABLE` passes by default; `fail_when_unavailable=True` makes it fail, with a dedicated `verification_disabled` message when RCCM verification is switched off. With the current IFU checker, a valid IFU passes the default existence validator and fails its strict version. They use a shared checker configured by the optional `BENIN_BUSINESS_ID` setting; a missing or `None` key falls back to the environment variables above:

```python
BENIN_BUSINESS_ID = {
    "RCCM_APIEX": {"ENABLED": True, "TIMEOUT": 10},
    # "RCCM_CHECKER": RccmChecker(fake_client, enabled=True),  # e.g. in tests
}
```

The shared checker is rebuilt when the setting changes, for example under `override_settings()`. An enabled RCCM checker needs the `httpx` extra.

Like the Laravel rules of the PHP package, the form fields leave a value that is blank after PHP's `trim()` (only `" \t\n\r\0\x0b"` are stripped) to `required`. A model `CharField` converts its value to a string before running validators, and a plain `forms.CharField` strips surrounding whitespace with `str.strip()`: use the package's form fields, or call the validators yourself, where the original value matters. Override messages with `error_messages={"unknown_registry": "..."}` on a form field, or with your own catalogue in `LOCALE_PATHS`.

## Pydantic

Pydantic 2.0.1 or later:

```python
from pydantic import BaseModel
from benin_business_id.pydantic import PydanticIfu, PydanticRccm


class Company(BaseModel):
    ifu: PydanticIfu
    rccm: PydanticRccm


company = Company.model_validate({"ifu": "3.201.200.247.219", "rccm": "RB/COT/07-B-1432"})
company.rccm  # Rccm(value='RB/COT/07 B 1432')
company.model_dump()  # {'ifu': '3201200247219', 'rccm': 'RB/COT/07 B 1432'}
```

Validation errors have one type per reason (`ifu_invalid_year`, `rccm_unknown_registry`…) and carry `ctx={"reason": ...}`. An existing object of the matching type is returned as is; any other value that is not a string fails with `*_invalid_characters`. Strict mode behaves the same. `PydanticIfu` and `PydanticRccm` are `Annotated` aliases, not classes: use `Ifu` and `Rccm` for `isinstance()` checks. Existence is never checked during model validation.

## Differences from the PHP package

- The `User-Agent` sent to APIEx names this package: `egbavou/benin-business-id-python (+https://github.com/egbavou/benin-business-id-python)`.
- `creation_date` is a `datetime.date` rather than a `DateTimeImmutable` at midnight UTC; a year-0000 date, which `datetime.date` cannot hold, is `None`.
- `TaxpayerType` members have string values, and failures are reported through Python exceptions in `failure`.
- Timeouts apply per operation (see above); a body cut off by the network is `TRANSPORT`, as with Guzzle.
- A float found in an APIEx text field is converted like PHP's `(string)` with the default precision of 14, except for rare exact ties at the 15th significant digit.

## Development

```bash
uv sync --all-extras
uv run ruff check && uv run ruff format --check
uv run mypy
uv run pytest
```

The default tests use a fake httpx transport and never reach the network. Two groups are excluded by default:

```bash
uv run pytest -m parity                            # compares results with the PHP package
BENIN_BUSINESS_ID_LIVE=1 uv run pytest -m live     # queries the real APIEx directory
```

The parity tests run thousands of generated identifiers, APIEx responses and configurations through both packages and compare every result. They need `php` and the PHP package installed with its development dependencies in `../benin-business-id`, or in `BENIN_BUSINESS_ID_PHP_DIR`. Live tests are skipped unless `BENIN_BUSINESS_ID_LIVE=1`, even when selected; they never run in CI.

## Licence

MIT. See [LICENSE](LICENSE).
