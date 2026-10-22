"""Port of the PHP tests/Unit/CheckersTest.php, run with the sync and the async checker."""

import json
import pickle
from collections.abc import Callable
from datetime import UTC, date, datetime

import httpx
import pytest
from tests.httpx_integration.support import Check, page, raw

from benin_business_id import (
    CheckStatus,
    DirectoryError,
    Rccm,
    RccmCheckResult,
    RccmRegister,
    UnavailableReason,
)

BUSINESS_FIELDS = (
    "name",
    "trade_name",
    "creation_date",
    "municipality",
    "district",
    "phone",
    "email",
    "main_activity",
    "former_number",
    "register",
)


def assert_no_business_fields(result: RccmCheckResult) -> None:
    for field in BUSINESS_FIELDS:
        assert getattr(result, field) is None, field


def test_validates_before_checking_the_disabled_switch_without_making_requests(
    check: Check,
) -> None:
    for enabled in (False, True):
        result, fake = check("bad input", enabled=enabled)

        assert result.status is CheckStatus.INVALID_FORMAT
        assert result.rccm is None
        assert result.unavailable_reason is None
        assert result.failure is None
        assert result.input == "bad input"
        assert fake.requests == []

    result, fake = check(" rb/cot/18-B-22272 ", enabled=False)

    assert result.status is CheckStatus.UNAVAILABLE
    assert result.unavailable_reason is UnavailableReason.DISABLED
    assert result.failure is None
    assert result.input == " rb/cot/18-B-22272 "
    assert result.rccm is not None
    assert result.checked_at.tzinfo is UTC
    assert fake.requests == []


def test_maps_all_company_fields_from_the_first_exact_request(check: Check) -> None:
    identifier = Rccm("RB/COT/18 B 22272")
    before = datetime.now(UTC)
    result, fake = check(
        identifier,
        [
            page(
                [
                    {
                        "Numéro RC": "RB/COT/18 B 22272",
                        "Dénomination": "Example Company",
                        "Nom commercial": "Example Trade",
                        "Date création": "2018-08-27",
                        "Commune": {"key": "city", "value": "Example Municipality"},
                        "Quartier": {"key": "district", "value": "Example District"},
                        "Téléphone": "+229 01 00 00 00 00",
                        "Email": "company@example.test",
                        "Activité principale": "Ignored company activity",
                    }
                ]
            )
        ],
    )

    assert result.status is CheckStatus.FOUND
    assert result.unavailable_reason is None
    assert result.failure is None
    assert result.rccm is identifier
    assert result.input == identifier.value
    assert result.name == "Example Company"
    assert result.trade_name == "Example Trade"
    assert result.creation_date == date(2018, 8, 27)
    assert result.municipality == "Example Municipality"
    assert result.district == "Example District"
    assert result.phone == "+229 01 00 00 00 00"
    assert result.email == "company@example.test"
    assert result.main_activity is None
    assert result.former_number is None
    assert result.register is RccmRegister.COMPANIES
    assert result.checked_at.tzinfo is UTC
    assert before <= result.checked_at <= datetime.now(UTC)
    assert len(fake.requests) == 1


@pytest.mark.parametrize(
    ("annotation", "former"),
    [
        ("(Ancien n°: 02 B 1545)", "02 B 1545"),
        ("(Ancien n°: )", None),
        ("(Ancien numéro: 02 B 1545)", "02 B 1545"),
        ("(ANCIEN N° : 21.130 B)", "21.130 B"),
        ("(Ancien no: RB/PK/11 B 059)", "RB/PK/11 B 059"),
        ("(Ancien n°RCCM RB/PNO/05 B 146)", "RB/PNO/05 B 146"),
        ("(ANCIEN NUMÉRO 1234)", "1234"),
        (f"(Anc{chr(0x0130)}en n°: 1234)", None),
        (f"(anc{chr(0x0131)}en n°: 1234)", None),
    ],
)
def test_extracts_each_specified_former_number_after_the_contains_request(
    check: Check, annotation: str, former: str | None
) -> None:
    result, fake = check(
        "RB/COT/07 B 2058", [page(), page([{"Numéro RC": f"RB/COT/07 B 2058 {annotation}"}])]
    )

    assert result.status is CheckStatus.FOUND
    assert result.unavailable_reason is None
    assert result.failure is None
    assert result.former_number == former
    assert len(fake.requests) == 2


def test_compares_the_entire_identifier_rather_than_matching_a_prefix(check: Check) -> None:
    records: list[dict[str, object]] = [
        {"Numéro RC": f"RB/COT/18 B {number}"} for number in range(22270, 22280)
    ]
    records += [
        {"Numéro RC": "RB/ABC/18 B 2227"},
        {"Numéro RC": "RB/COT/17 B 2227"},
        {"Numéro RC": "RB/COT/18 C 2227"},
        {"Numéro RC": "invalid identifier"},
    ]
    result, fake = check("RB/COT/18 B 2227", [page(), page(records), page(), page()])

    assert result.status is CheckStatus.NOT_FOUND
    assert result.unavailable_reason is None
    assert result.failure is None
    assert len(fake.requests) == 4
    assert_no_business_fields(result)


@pytest.mark.parametrize(
    ("value", "stored"),
    [
        ("RB/ABC/12 B 180", "RB/ABC/2012 B 180"),
        ("RB/COT/2005 B 40", "RB/COT/2005 B 0040"),
        ("RB/COT/2005 B 0040", "RB/COT/05-B-40"),
        ("RB/COT/18 B 000000", "RB/COT/18 B 0"),
    ],
)
def test_compares_equivalent_year_forms_and_sequence_numbers(
    check: Check, value: str, stored: str
) -> None:
    result, _ = check(value, [page([{"Numéro RC": stored}])])

    assert result.status is CheckStatus.FOUND
    assert result.unavailable_reason is None
    assert result.failure is None
    assert result.rccm is not None
    assert result.rccm.value == value


def test_searches_establishments_first_for_category_a_and_never_exposes_personal_fields(
    check: Check,
) -> None:
    private = [
        "Private given name sentinel",
        "Private surname sentinel",
        "Private phone sentinel",
        "private@example.test",
    ]
    result, fake = check(
        "RB/PKO/23 A 18689",
        [
            page(
                [
                    {
                        "Numéro RC": "RB/PKO/23 A 18689",
                        "Nom commercial": "Example Establishment",
                        "Date de création": "2023-01-02",
                        "Commune": "Example Municipality",
                        "Quartier": "Example District",
                        "Activité principale": "Example Activity",
                        "Dénomination": "Untrusted establishment name",
                        "Prénom": private[0],
                        "Nom": private[1],
                        "Téléphone": private[2],
                        "Email": private[3],
                    }
                ]
            )
        ],
    )

    assert result.status is CheckStatus.FOUND
    assert result.unavailable_reason is None
    assert result.failure is None
    assert result.register is RccmRegister.ESTABLISHMENTS
    assert "gdb.monentreprise.bj" in str(fake.requests[0].url)
    assert result.trade_name == "Example Establishment"
    assert result.creation_date == date(2023, 1, 2)
    assert result.municipality == "Example Municipality"
    assert result.district == "Example District"
    assert result.main_activity == "Example Activity"
    assert result.name is None
    assert result.phone is None
    assert result.email is None

    for serialized in (repr(result), str(pickle.dumps(result))):
        for value in private:
            assert value not in serialized


@pytest.mark.parametrize("category", ["A", "B", "C", "D", "E"])
def test_falls_back_to_the_other_register_in_the_specified_order(
    check: Check, category: str
) -> None:
    number = f"RB/COT/18 {category} 1234"
    result, fake = check(
        number,
        [page(), page(), page([{"Numéro RC": number}])],
        companies_url="https://example.test/companies",
        establishments_url="https://example.test/establishments",
    )

    first = "/establishments" if category == "A" else "/companies"
    last = "/companies" if category == "A" else "/establishments"

    assert result.status is CheckStatus.FOUND
    assert result.unavailable_reason is None
    assert result.failure is None
    assert [request.url.path for request in fake.requests] == [first, first, last]


class FakeTransportError(httpx.TransportError):
    pass


TECHNICAL_FAILURES: list[
    tuple[str, Callable[[], httpx.Response | Exception], UnavailableReason]
] = [
    (
        "httpx exception",
        lambda: FakeTransportError("Fake transport failure."),
        UnavailableReason.TRANSPORT,
    ),
    (
        "unexpected runtime exception",
        lambda: RuntimeError("Fake runtime failure."),
        UnavailableReason.TRANSPORT,
    ),
    ("internal type error", lambda: TypeError("Fake type error."), UnavailableReason.TRANSPORT),
    (
        "server error",
        lambda: raw(500, "Private response body sentinel"),
        UnavailableReason.HTTP_STATUS,
    ),
    ("service unavailable", lambda: raw(503), UnavailableReason.HTTP_STATUS),
    (
        "redirect",
        lambda: httpx.Response(301, headers={"Location": "https://example.test/"}),
        UnavailableReason.HTTP_STATUS,
    ),
    ("invalid JSON", lambda: raw(200, "<html>Unavailable</html>"), UnavailableReason.INVALID_JSON),
    ("missing results", lambda: raw(200, '{"count":0}'), UnavailableReason.SCHEMA),
    ("missing count", lambda: raw(200, '{"results":[]}'), UnavailableReason.SCHEMA),
    ("string count", lambda: raw(200, '{"count":"0","results":[]}'), UnavailableReason.SCHEMA),
    ("boolean count", lambda: raw(200, '{"count":true,"results":[]}'), UnavailableReason.SCHEMA),
    ("object results", lambda: raw(200, '{"count":0,"results":{}}'), UnavailableReason.SCHEMA),
    (
        "non-list results",
        lambda: raw(200, '{"count":1,"results":{"1":{}}}'),
        UnavailableReason.SCHEMA,
    ),
    ("non-object row", lambda: raw(200, '{"count":1,"results":[[]]}'), UnavailableReason.SCHEMA),
    (
        "missing number",
        lambda: page([{"Other field": "Changed schema"}]),
        UnavailableReason.SCHEMA,
    ),
    ("top-level list", lambda: raw(200, "[]"), UnavailableReason.SCHEMA),
    ("null JSON", lambda: raw(200, "null"), UnavailableReason.SCHEMA),
    (
        "schema failure after matching record",
        lambda: page([{"Numéro RC": "RB/COT/18 B 22272"}, {"Other field": "Changed schema"}]),
        UnavailableReason.SCHEMA,
    ),
]


@pytest.mark.parametrize(
    ("make", "reason"),
    [case[1:] for case in TECHNICAL_FAILURES],
    ids=[case[0] for case in TECHNICAL_FAILURES],
)
def test_returns_unavailable_immediately_for_technical_and_schema_failures(
    check: Check, make: Callable[[], httpx.Response | Exception], reason: UnavailableReason
) -> None:
    response = make()
    result, fake = check("RB/COT/18 B 22272", [response])

    assert result.status is CheckStatus.UNAVAILABLE
    assert result.unavailable_reason is reason
    assert result.failure is not None

    if isinstance(response, Exception):
        assert result.failure is response
    elif reason is UnavailableReason.INVALID_JSON:
        assert isinstance(result.failure, json.JSONDecodeError)
    else:
        assert isinstance(result.failure, DirectoryError)
        assert result.failure.reason is reason
        assert str(result.failure) == (
            f"APIEx returned HTTP {response.status_code}."
            if reason is UnavailableReason.HTTP_STATUS
            else "APIEx returned an unexpected response schema."
        )
        assert result.failure.__cause__ is None
        assert "sentinel" not in str(result.failure)

    assert result.rccm is not None
    assert_no_business_fields(result)
    assert len(fake.requests) == 1


def test_never_follows_redirects_even_when_the_client_does(check: Check) -> None:
    result, fake = check(
        "RB/COT/18 B 22272",
        [
            httpx.Response(302, headers={"Location": "https://example.test/moved"}),
            page([{"Numéro RC": "RB/COT/18 B 22272"}]),
        ],
        client_options={"follow_redirects": True},
    )

    assert result.status is CheckStatus.UNAVAILABLE
    assert result.unavailable_reason is UnavailableReason.HTTP_STATUS
    assert len(fake.requests) == 1


@pytest.mark.parametrize(
    "date_value", [None, "", "27/08/2018", "2018-02-30", "2018-8-27", "2018-08-27T00:00:00Z", 123]
)
def test_maps_missing_empty_null_and_malformed_optional_fields_to_none(
    check: Check, date_value: object
) -> None:
    result, _ = check(
        "RB/COT/18 B 22272",
        [
            page(
                [
                    {
                        "Numéro RC": "RB/COT/18 B 22272",
                        "Dénomination": "   ",
                        "Nom commercial": None,
                        "Date création": date_value,
                        "Commune": {"key": "missing-value"},
                        "Quartier": False,
                    }
                ]
            )
        ],
    )

    assert result.status is CheckStatus.FOUND
    assert result.unavailable_reason is None
    assert result.failure is None
    assert result.name is None
    assert result.trade_name is None
    assert result.creation_date is None
    assert result.municipality is None
    assert result.district is None
    assert result.phone is None
    assert result.email is None


def test_selects_the_exact_record_after_several_near_misses(check: Check) -> None:
    result, fake = check(
        "RB/COT/18 B 22272",
        [
            page(
                [
                    {"Numéro RC": "RB/COT/18 B 22270", "Dénomination": "Wrong sequence"},
                    {"Numéro RC": "RB/ABC/18 B 22272", "Dénomination": "Wrong registry"},
                    {"Numéro RC": "RB/COT/17 B 22272", "Dénomination": "Wrong year"},
                    {"Numéro RC": "RB/COT/18 C 22272", "Dénomination": "Wrong category"},
                    {
                        "Numéro RC": "RB/COT/18 B 22272 (Ancien no: 02 B 1234)",
                        "Dénomination": "Matched Company",
                        "Nom commercial": "Matched Trade",
                        "Date création": "2018-08-27",
                        "Commune": "Matched Municipality",
                        "Quartier": "Matched District",
                        "Téléphone": "+229 01 00 00 00 00",
                        "Email": "matched@example.test",
                    },
                ]
            )
        ],
    )

    assert result.status is CheckStatus.FOUND
    assert result.unavailable_reason is None
    assert result.failure is None
    assert result.register is RccmRegister.COMPANIES
    assert result.name == "Matched Company"
    assert result.trade_name == "Matched Trade"
    assert result.creation_date == date(2018, 8, 27)
    assert result.municipality == "Matched Municipality"
    assert result.district == "Matched District"
    assert result.phone == "+229 01 00 00 00 00"
    assert result.email == "matched@example.test"
    assert result.former_number == "02 B 1234"
    assert len(fake.requests) == 1


@pytest.mark.parametrize(
    ("stored", "expected"),
    [("RB/COT/18 B 22273", CheckStatus.UNAVAILABLE), ("RB/COT/18 B 22272", CheckStatus.FOUND)],
)
def test_treats_incomplete_results_as_schema_unavailable_unless_a_row_matches(
    check: Check, stored: str, expected: CheckStatus
) -> None:
    body = json.dumps({"count": 51, "results": [{"Numéro RC": stored}]})
    result, fake = check("RB/COT/18 B 22272", [raw(200, body)])

    assert result.status is expected

    if expected is CheckStatus.UNAVAILABLE:
        assert result.unavailable_reason is UnavailableReason.SCHEMA
        assert isinstance(result.failure, DirectoryError)
        assert str(result.failure) == (
            "APIEx returned an incomplete results page without a matching record."
        )
    else:
        assert result.unavailable_reason is None
        assert result.failure is None

    assert len(fake.requests) == 1


def test_returns_schema_unavailable_for_a_nonempty_count_with_no_received_rows(
    check: Check,
) -> None:
    result, fake = check("RB/COT/18 B 22272", [raw(200, '{"count":1,"results":[]}')])

    assert result.status is CheckStatus.UNAVAILABLE
    assert result.unavailable_reason is UnavailableReason.SCHEMA
    assert isinstance(result.failure, DirectoryError)
    assert str(result.failure) == (
        "APIEx returned an incomplete results page without a matching record."
    )
    assert len(fake.requests) == 1


def test_returns_transport_unavailable_when_httpx_rejects_the_url(check: Check) -> None:
    result, fake = check("RB/COT/18 B 22272", companies_url="https://example.test:abc/")

    assert result.status is CheckStatus.UNAVAILABLE
    assert result.unavailable_reason is UnavailableReason.TRANSPORT
    assert isinstance(result.failure, httpx.InvalidURL)
    assert fake.requests == []


def test_returns_schema_unavailable_for_unexpected_errors_after_receiving_a_200_response(
    check: Check, monkeypatch: pytest.MonkeyPatch
) -> None:
    failure = TypeError("Fake response processing failure.")

    def broken_decoder(body: bytes) -> object:
        raise failure

    monkeypatch.setattr("benin_business_id._php.json_decode", broken_decoder)
    result, _ = check("RB/COT/18 B 22272", [page()])

    assert result.status is CheckStatus.UNAVAILABLE
    assert result.unavailable_reason is UnavailableReason.SCHEMA
    assert result.failure is failure


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        (42, "42"),
        (0, "0"),
        (12.5, "12.5"),
        (1e20, "1.0E+20"),
        ("  Example  ", "Example"),
        (" \t\n ", None),
        (f"{chr(0x00A0)}Example", f"{chr(0x00A0)}Example"),
        ("\0Example\0", "Example"),
        (False, None),
        ([], None),
    ],
)
def test_normalizes_numeric_and_trimmed_text_fields_including_catalog_values(
    check: Check, raw_value: object, expected: str | None
) -> None:
    result, _ = check(
        "RB/COT/18 B 22272",
        [
            page(
                [
                    {
                        "Numéro RC": "RB/COT/18 B 22272",
                        "Dénomination": raw_value,
                        "Commune": {"value": raw_value},
                    }
                ]
            )
        ],
    )

    assert result.status is CheckStatus.FOUND
    assert result.unavailable_reason is None
    assert result.failure is None
    assert result.name == expected
    assert result.municipality == expected
