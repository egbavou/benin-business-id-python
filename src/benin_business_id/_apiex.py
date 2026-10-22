"""The APIEx public directory: request building and response reading, shared by sync and async.

APIEx publishes no API documentation: the views, field identifiers and field names below were
read from its public web client, and can change without notice.
"""

import json
import re
from datetime import date
from typing import TYPE_CHECKING, Final, TypedDict
from urllib.parse import quote

from benin_business_id import _php
from benin_business_id._cleanup import PCRE_SPACE
from benin_business_id._enums import RccmRegister, UnavailableReason
from benin_business_id._errors import DirectoryError
from benin_business_id._rccm import Rccm

if TYPE_CHECKING:
    import httpx

USER_AGENT: Final = (
    "egbavou/benin-business-id-python (+https://github.com/egbavou/benin-business-id-python)"
)
COMPANIES_FIELD_ID: Final = 307
ESTABLISHMENTS_FIELD_ID: Final = 141
RC_NUMBER_FIELD: Final = "Numéro RC"
PAGE_SIZE: Final = 50
INCOMPLETE_PAGE_MESSAGE: Final = (
    "APIEx returned an incomplete results page without a matching record."
)

_SPACE: Final = f"[{PCRE_SPACE}]"
# The PHP pattern /\(\s*ancien\s*n(?:um[ée]ro|\s*[°o])?\s*(?:rccm)?\s*:?\s*(.+?)\s*\)/iu, spelled
# without re.IGNORECASE: Python would then also match U+0130 and U+0131 for 'i', and PCRE does not.
_FORMER_NUMBER: Final = re.compile(
    rf"\({_SPACE}*[aA][nN][cC][iI][eE][nN]{_SPACE}*[nN]"
    rf"(?:[uU][mM][éÉeE][rR][oO]|{_SPACE}*[°oO])?{_SPACE}*(?:[rR][cC][cC][mM])?"
    rf"{_SPACE}*:?{_SPACE}*(.+?){_SPACE}*\)"
)
_DATE: Final = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})")

Record = dict[str, object]


class Details(TypedDict):
    name: str | None
    trade_name: str | None
    creation_date: date | None
    municipality: str | None
    district: str | None
    phone: str | None
    email: str | None
    main_activity: str | None
    former_number: str | None
    register: RccmRegister


def register_order(rccm: Rccm) -> tuple[RccmRegister, RccmRegister]:
    """Category A numbers are searched among establishments first, others among companies."""
    if rccm.category == "A":
        return (RccmRegister.ESTABLISHMENTS, RccmRegister.COMPANIES)

    return (RccmRegister.COMPANIES, RccmRegister.ESTABLISHMENTS)


def search_values(rccm: Rccm, exact: bool) -> list[str]:
    """The spellings of the number searched with '==' (exact) or 'icontains'."""
    year_input = rccm.value.split("/")[2].split(" ", 1)[0]
    years = [year_input]

    if rccm.year <= 2020:
        years.append(str(rccm.year) if len(year_input) == 2 else year_input[-2:])

    numbers = [rccm.sequence_number, sequence_key(rccm)]

    if exact and rccm.sequence_number[0] != "0" and len(rccm.sequence_number) < 5:
        numbers.extend(rccm.sequence_number.zfill(length) for length in (3, 4, 5))

    suffixes = [""] if exact else [" ", "("]
    values: list[str] = []

    for year in years:
        for number in dict.fromkeys(numbers):
            for form in (
                f"RB/{rccm.registry_code}/{year} {rccm.category} {number}",
                f"RB/{rccm.registry_code}/{year}-{rccm.category}-{number}",
            ):
                values.extend(form + suffix for suffix in suffixes)

    return values


def filters(register: RccmRegister, rccm: Rccm, exact: bool) -> list[dict[str, object]]:
    """The 'filters' parameter: one filter per spelling, combined with OR."""
    field_id = COMPANIES_FIELD_ID if register is RccmRegister.COMPANIES else ESTABLISHMENTS_FIELD_ID

    return [
        {
            "gate": "&&" if index == 0 else "||",
            "type": "string",
            "field_id": field_id,
            "logic": "==" if exact else "icontains",
            "value": value,
        }
        for index, value in enumerate(search_values(rccm, exact))
    ]


def request_url(base_url: str, register: RccmRegister, rccm: Rccm, exact: bool) -> str:
    """The request URL, encoded like http_build_query(..., PHP_QUERY_RFC3986)."""
    encoded = json.dumps(filters(register, rccm, exact), separators=(",", ":"), ensure_ascii=True)
    query = f"page=1&page_size={PAGE_SIZE}&filters={quote(encoded, safe='')}"

    return base_url + ("&" if "?" in base_url else "?") + query


def build_request(
    base_url: str, register: RccmRegister, rccm: Rccm, exact: bool, timeout: "httpx.Timeout"
) -> "httpx.Request":
    """A bare request: the client adds Host only, so the wire matches Guzzle with cURL.

    The timeout is set on the request itself: httpx 0.27 does not apply the client's timeout
    to a request it did not build.
    """
    import httpx

    return httpx.Request(
        "GET",
        request_url(base_url, register, rccm, exact),
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        extensions={"timeout": timeout.as_dict()},
    )


def read_page(status: int, body: bytes, rccm: Rccm) -> Record | None:
    """Return the record matching rccm in a results page, or None.

    Raises DirectoryError when the page cannot be trusted. Every row is checked, even after a
    match, so that a schema change is noticed.
    """
    if status != 200:
        raise DirectoryError(UnavailableReason.HTTP_STATUS, f"APIEx returned HTTP {status}.")

    try:
        payload = _php.json_decode(body)
    except (ValueError, RecursionError) as error:
        raise DirectoryError(UnavailableReason.INVALID_JSON) from error

    if not isinstance(payload, dict):
        raise DirectoryError(UnavailableReason.SCHEMA)

    count = payload.get("count")
    results = payload.get("results")

    if not isinstance(count, int) or isinstance(count, bool) or not isinstance(results, list):
        raise DirectoryError(UnavailableReason.SCHEMA)

    match: Record | None = None

    for record in results:
        if not isinstance(record, dict) or RC_NUMBER_FIELD not in record:
            raise DirectoryError(UnavailableReason.SCHEMA)

        if match is None and _matches(record, rccm):
            match = record

    if match is None and count > len(results):
        raise DirectoryError(UnavailableReason.SCHEMA, INCOMPLETE_PAGE_MESSAGE)

    return match


def details(record: Record, register: RccmRegister) -> Details:
    """The public business fields of a found record (D14, D19, D27).

    Owner names are never read. Phone and email are only read from the companies register.
    """
    company = register is RccmRegister.COMPANIES

    return Details(
        name=text(record, "Dénomination") if company else None,
        trade_name=text(record, "Nom commercial"),
        creation_date=creation_date(record, "Date création" if company else "Date de création"),
        municipality=text(record, "Commune"),
        district=text(record, "Quartier"),
        phone=text(record, "Téléphone") if company else None,
        email=text(record, "Email") if company else None,
        main_activity=None if company else text(record, "Activité principale"),
        former_number=former_number(record),
        register=register,
    )


def sequence_key(rccm: Rccm) -> str:
    """The sequence number without leading zeros; '0' when it only has zeros."""
    return rccm.sequence_number.lstrip("0") or "0"


def text(record: Record, field: str) -> str | None:
    """A field as trimmed text. Catalog fields hold their text under 'value'."""
    value = record.get(field)

    if isinstance(value, dict):
        value = value.get("value")

    if isinstance(value, bool):
        return None

    if isinstance(value, str):
        result = value
    elif isinstance(value, int):
        result = str(value)
    elif isinstance(value, float):
        result = _php.float_to_string(value)
    else:
        return None

    result = _php.trim(result)

    return result or None


def creation_date(record: Record, field: str) -> date | None:
    value = text(record, field)
    parts = _DATE.fullmatch(value) if value is not None else None

    if parts is None:
        return None

    try:
        return date(int(parts[1]), int(parts[2]), int(parts[3]))
    except ValueError:
        return None


def former_number(record: Record) -> str | None:
    """The former number from an annotation such as '(Ancien n°: 02 B 1545)'."""
    raw = text(record, RC_NUMBER_FIELD)
    parts = _FORMER_NUMBER.search(raw) if raw is not None else None

    if parts is None:
        return None

    return _php.trim(parts[1]) or None


def _matches(record: Record, rccm: Rccm) -> bool:
    raw = text(record, RC_NUMBER_FIELD)
    candidate = Rccm.try_parse(raw.split("(", 1)[0]) if raw is not None else None

    return (
        candidate is not None
        and candidate.registry_code == rccm.registry_code
        and candidate.year == rccm.year
        and candidate.category == rccm.category
        and sequence_key(candidate) == sequence_key(rccm)
    )
