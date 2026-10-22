"""Port of the PHP tests/Unit/RequestsTest.php, plus the exact request sent on the wire."""

import json
from typing import cast
from urllib.parse import parse_qs, quote

from tests.httpx_integration.support import Check, FakeApiex, page

from benin_business_id import Rccm, RccmRegister
from benin_business_id._apiex import request_url

# Written out rather than read from the package (decision P1 of the design).
USER_AGENT = (
    "egbavou/benin-business-id-python (+https://github.com/egbavou/benin-business-id-python)"
)


def query(fake: FakeApiex, index: int) -> dict[str, list[str]]:
    return parse_qs(fake.requests[index].url.query.decode(), keep_blank_values=True)


def decoded_filters(fake: FakeApiex, index: int) -> list[dict[str, object]]:
    raw = query(fake, index)["filters"][0]

    return cast(list[dict[str, object]], json.loads(raw))


def test_sends_the_exact_expected_equality_and_delimited_contains_filters(check: Check) -> None:
    _, fake = check("RB/COT/2005 B 40", [page() for _ in range(4)])

    assert len(fake.requests) == 4

    for index, request in enumerate(fake.requests):
        assert request.method == "GET"
        assert request.headers["User-Agent"] == USER_AGENT
        assert request.headers["Accept"] == "application/json"
        parameters = query(fake, index)
        assert parameters["page"] == ["1"]
        assert parameters["page_size"] == ["50"]
        assert "\\/" not in parameters["filters"][0]

        exact = index % 2 == 0
        expected: list[dict[str, object]] = []

        for year in ("2005", "05"):
            for sequence in ("40", "040", "0040", "00040") if exact else ("40",):
                for form in (f"RB/COT/{year} B {sequence}", f"RB/COT/{year}-B-{sequence}"):
                    for suffix in ("",) if exact else (" ", "("):
                        expected.append(
                            {
                                "gate": "&&" if not expected else "||",
                                "type": "string",
                                "field_id": 307 if index < 2 else 141,
                                "logic": "==" if exact else "icontains",
                                "value": form + suffix,
                            }
                        )

        assert decoded_filters(fake, index) == expected


def test_uses_only_base_sequences_in_contains_filters_and_preserves_leading_zeros(
    check: Check,
) -> None:
    _, fake = check("RB/COT/05 B 0040", [page() for _ in range(4)])
    values = [item["value"] for item in decoded_filters(fake, 1)]

    assert len(values) == 16
    assert "RB/COT/05 B 0040(" in values
    assert "RB/COT/2005-B-40 " in values
    assert "RB/COT/05 B 00040(" not in values


def test_does_not_generate_unsupported_four_digit_years_for_recent_registrations(
    check: Check,
) -> None:
    _, fake = check("RB/COT/24 B 12345", [page() for _ in range(4)])

    assert len(decoded_filters(fake, 0)) == 2
    assert "2024" not in query(fake, 0)["filters"][0]


def test_appends_request_parameters_to_a_configured_url_with_an_existing_query(
    check: Check,
) -> None:
    _, fake = check(
        "RB/COT/18 B 22272",
        [page() for _ in range(4)],
        companies_url="https://example.test/companies?token=example",
        establishments_url="https://example.test/establishments?token=example",
    )

    assert len(fake.requests) == 4

    for index, request in enumerate(fake.requests):
        assert request.url.query.decode().startswith("token=example&page=1&")
        parameters = query(fake, index)
        assert parameters["token"] == ["example"]
        assert parameters["page_size"] == ["50"]
        assert "filters" in parameters


def test_sends_exactly_the_computed_url_encoded_like_rawurlencode(check: Check) -> None:
    rccm = Rccm("RB/COT/24 B 39072")
    _, fake = check(rccm, [page() for _ in range(4)])

    filters = (
        '[{"gate":"&&","type":"string","field_id":307,"logic":"==","value":"RB/COT/24 B 39072"},'
        '{"gate":"||","type":"string","field_id":307,"logic":"==","value":"RB/COT/24-B-39072"}]'
    )
    expected = (
        "https://gdb.guichet.investbenin.bj/data-view/pm/latest/5?page=1&page_size=50&filters="
        + quote(filters, safe="")
    )

    assert str(fake.requests[0].url) == expected
    assert (
        request_url(
            "https://gdb.guichet.investbenin.bj/data-view/pm/latest/5",
            RccmRegister.COMPANIES,
            rccm,
            exact=True,
        )
        == expected
    )
    assert "%2F" in expected
    assert "%20" in expected
    assert str(fake.requests[2].url).startswith(
        "https://gdb.monentreprise.bj/data-view/registre%20pp/latest/310?page=1&"
    )


def test_sends_only_host_user_agent_and_accept_whatever_the_client_defaults(check: Check) -> None:
    _, fake = check(
        "RB/COT/18 B 22272",
        [page() for _ in range(4)],
        client_options={
            "headers": {"X-Client-Default": "1"},
            "params": {"client": "param"},
            "cookies": {"session": "cookie"},
        },
    )

    for request in fake.requests:
        assert sorted(request.headers.keys()) == ["accept", "host", "user-agent"]
        assert "client=param" not in str(request.url)
        assert str(request.url).count("page=1") == 1


def test_applies_the_client_timeout_to_the_request(check: Check) -> None:
    _, fake = check("RB/COT/18 B 22272", [page() for _ in range(4)], client_options={"timeout": 7})

    assert fake.requests[0].extensions["timeout"] == {
        "connect": 7,
        "read": 7,
        "write": 7,
        "pool": 7,
    }
