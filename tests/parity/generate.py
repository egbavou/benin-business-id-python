"""Seeded generators of identifiers, APIEx responses and configurations for the parity test."""

import base64
import json
import random
from dataclasses import dataclass
from decimal import Decimal

from tests import cases

from benin_business_id import Rccm
from benin_business_id._cleanup import SEPARATOR_CODE_POINTS
from benin_business_id._clock import current_year

ACTIVE = ["COT", "ABC", "PNO", "PKO", "ABY", "LKS", "NAT", "DGO", "KDI", "APL", "SVL"]
FORMER = ["PN", "PK", "ODH", "POB", "ALD"]
SPACES = [chr(code_point) for code_point in SEPARATOR_CODE_POINTS]
# Characters that look like separators but are not removed, in PHP or in Python.
NEAR_SPACES = [
    chr(code_point) for code_point in (0x1C, 0x1F, 0x180E, 0x200B, 0xFEFF, 0x2010, 0x00AD)
]
OTHER = ["/", ":", "(", ")", "°", "é", "A", "b", "\0", chr(0xFF13), chr(0x0131), chr(0x017F)]


def has_surrogate(value: str) -> bool:
    return any(0xD800 <= ord(character) <= 0xDFFF for character in value)


def mutate(rng: random.Random, value: str) -> str:
    """Insert separators and look-alikes, and change the case of letters."""
    characters = list(value)

    for _ in range(rng.randint(0, 3)):
        position = rng.randint(0, len(characters))
        pool = rng.choice([SPACES, SPACES, [".", "-"], NEAR_SPACES, OTHER])
        characters.insert(position, rng.choice(pool))

    if rng.random() < 0.3:
        characters = [c.lower() if rng.random() < 0.5 else c for c in characters]

    return "".join(characters)


def random_ifu(rng: random.Random) -> str:
    year = rng.choice([rng.randint(1995, current_year() + 2), rng.randint(2006, current_year())])
    digits = f"{rng.randint(0, 9)}{year}{rng.randint(0, 10**8 - 1):08d}"

    if rng.random() < 0.2:
        digits = digits[: rng.randint(0, 15)] + "".join(
            str(rng.randint(0, 9)) for _ in range(rng.randint(0, 2))
        )

    return mutate(rng, digits) if rng.random() < 0.6 else digits


def random_rccm(rng: random.Random) -> str:
    country = rng.choice(["RB", "RB", "RB", "BJ", "rb", "Rb"])
    registry = rng.choice([*ACTIVE, *ACTIVE, *FORMER, "OUI", "CO", "COTT", "Cot", "ZZZ"])
    year = rng.choice(
        [
            f"{rng.randint(0, 99):02d}",
            f"{rng.randint(0, 99):02d}",
            str(rng.randint(1985, current_year() + 1)),
            f"{rng.randint(0, 999):03d}",
        ]
    )
    category = rng.choice(["A", "B", "B", "C", "D", "E", "M", "Z", "b"])
    sequence = "".join(str(rng.randint(0, 9)) for _ in range(rng.choice([0, 1, 2, 3, 4, 5, 6, 7])))

    if sequence and rng.random() < 0.2:
        sequence = "0" * rng.randint(1, 3) + sequence

    first, second, third, fourth = (
        rng.choice(["/", " ", "-", "", ".", "/ ", " - "]) for _ in range(4)
    )
    value = f"{country}{first}{registry}{second}{year}{third}{category}{fourth}{sequence}"

    if rng.random() < 0.1:
        value = (
            rng.choice(["RCCM ", "N° ", "RCCM : ", ""])
            + value
            + rng.choice(["", " du 13/06/2018", " (Ancien n°: 02 B 1545)"])
        )

    return mutate(rng, value) if rng.random() < 0.4 else value


def identifier_inputs(seed: int) -> list[tuple[str, str]]:
    rng = random.Random(seed)
    inputs = [("ifu", raw) for raw, *_ in cases.valid_ifu()]
    inputs += [("ifu", raw) for raw, _ in cases.invalid_ifu()]
    inputs += [("rccm", raw) for raw, *_ in cases.valid_rccm()]
    inputs += [("rccm", raw) for raw, _ in cases.invalid_rccm()]
    inputs += [("ifu", random_ifu(rng)) for _ in range(3000)]
    inputs += [("rccm", random_rccm(rng)) for _ in range(4000)]
    inputs += [
        ("ifu", "".join(rng.choice("0123456789 .-/x") for _ in range(rng.randint(0, 16))))
        for _ in range(500)
    ]

    # Lone surrogates cannot cross JSON to PHP; invalid UTF-8 has no Python string anyway.
    return [(operation, raw) for operation, raw in inputs if not has_surrogate(raw)]


@dataclass
class Raw:
    """JSON text inserted verbatim, for tokens a Python object cannot express."""

    text: str


@dataclass
class Pairs:
    """A JSON object written with its pairs as given, duplicate keys included."""

    items: list[tuple[str, object]]


def dump(value: object, rng: random.Random) -> str:
    """JSON text; strings are written with or without \\u escapes at random."""
    if isinstance(value, Raw):
        return value.text

    if isinstance(value, Pairs):
        pairs = (
            f"{json.dumps(key, ensure_ascii=rng.random() < 0.5)}:{dump(item, rng)}"
            for key, item in value.items
        )
        return "{" + ",".join(pairs) + "}"

    if isinstance(value, dict):
        return dump(Pairs(list(value.items())), rng)

    if isinstance(value, list):
        return "[" + ",".join(dump(item, rng) for item in value) + "]"

    return json.dumps(value, ensure_ascii=rng.random() < 0.5)


def safe_float(value: float) -> bool:
    """False for exact or near ties at the 15th significant digit (see design section 12.2)."""
    digits = Decimal(value).as_tuple().digits

    return len(digits) <= 14 or "".join(map(str, digits[14:16])) not in ("49", "50")


def random_float(rng: random.Random) -> float:
    while True:
        value: float = rng.choice(
            [
                rng.choice([12.5, 1.0, 0.1, 0.30000000000000004, 1e20, 1e-7, 100000.0, -3.75]),
                rng.uniform(-1e6, 1e6),
                rng.uniform(-1, 1) * 10 ** rng.randint(-30, 30),
            ]
        )

        if safe_float(value):
            return value


def text_value(rng: random.Random) -> object:
    return rng.choice(
        [
            "Example",
            "  Padded  ",
            " \t\n ",
            "",
            f"{chr(0x00A0)}Nbsp{chr(0x00A0)}",
            "\0Nul\0",
            "Café Étoile",
            rng.randint(-1000, 10**12),
            Raw(str(rng.choice([2**63 - 1, 2**63, -(2**63), -(2**63) - 1, 10**30]))),
            random_float(rng),
            True,
            False,
            None,
            [],
            {"value": "Catalog"},
            {"key": "k", "value": rng.choice(["  Catalog  ", 42, None, {"value": "nested"}])},
            {"key": "missing"},
        ]
    )


def date_value(rng: random.Random) -> object:
    year = rng.choice([rng.randint(1000, 2999), 2018, 2020])

    return rng.choice(
        [
            f"{year}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}",
            f"{year}-02-{rng.randint(28, 31):02d}",
            f"{year}-{rng.randint(0, 13):02d}-{rng.randint(0, 32):02d}",
            f" {year}-01-02 ",
            "27/08/2018",
            "2018-8-27",
            "2018-08-27T00:00:00Z",
            None,
            20180827,
        ]
    )


def number_variants(rng: random.Random, rccm: Rccm) -> list[str]:
    year_input = rccm.value.split("/")[2].split(" ", 1)[0]
    years = [year_input, str(rccm.year), str(rccm.year)[-2:]]
    sequences = [rccm.sequence_number, rccm.sequence_number.lstrip("0") or "0"]
    sequences.append(sequences[1].zfill(rng.randint(1, 6)))
    sequences.append(str(int(sequences[1]) + rng.choice([-1, 1, 10])))
    variants = []

    for _ in range(4):
        year = rng.choice(years)
        sequence = rng.choice(sequences)
        separator = rng.choice([" ", "-", "/"])
        category = rccm.category if rng.random() < 0.9 else rng.choice("ABCDE")
        registry = rccm.registry_code if rng.random() < 0.9 else rng.choice(ACTIVE)
        variants.append(
            f"RB/{registry}/{year}{separator}{category}{separator}{sequence}"
            + rng.choice(["", " ", "(", " (Ancien n°: 02 B 1545)"])
        )

    return variants


ANNOTATIONS = [
    "(Ancien n°: 02 B 1545)",
    "(Ancien n°: )",
    "(ANCIEN NUMÉRO 1234)",
    "(Ancien no: RB/PK/11 B 059)",
    "(Ancien n°RCCM RB/PNO/05 B 146)",
    "( ancien  n ° rccm : X )",
    f"(Anc{chr(0x0130)}en n°: 1)",
    f"(ancien n°:{chr(0x00A0)}5{chr(0x180E)})",
    "(Ancien n°: a\nb)",
    "(Ancien n°: a\rb)",
    "(Nouveau n°: 1)",
]


def record(rng: random.Random, rccm: Rccm | None) -> object:
    if rng.random() < 0.03:
        return rng.choice([[], "row", 1, None, {"Other field": "Changed schema"}])

    if rccm is not None and rng.random() < 0.7:
        number: object = rng.choice(number_variants(rng, rccm))

        if rng.random() < 0.3:
            number = f"{number} {rng.choice(ANNOTATIONS)}"
    else:
        number = rng.choice(
            [
                random_rccm(rng),
                "invalid identifier",
                None,
                3200700019113,
                {"value": "RB/COT/18 B 1"},
            ]
        )

    if rng.random() < 0.1:
        number = {"key": "rc", "value": number}

    fields: list[tuple[str, object]] = [("Numéro RC", number)]

    for name in (
        "Dénomination",
        "Nom commercial",
        "Commune",
        "Quartier",
        "Téléphone",
        "Email",
        "Activité principale",
        "Prénom",
        "Nom",
    ):
        if rng.random() < 0.8:
            fields.append((name, text_value(rng)))

    for name in ("Date création", "Date de création"):
        if rng.random() < 0.8:
            fields.append((name, date_value(rng)))

    if rng.random() < 0.05:
        fields.append(("Dénomination", text_value(rng)))

    rng.shuffle(fields)

    return Pairs(fields)


def nested(depth: int) -> str:
    return "[" * depth + "1" + "]" * depth


def junk_body(rng: random.Random) -> bytes:
    valid = '{"count":0,"results":[]}'

    return rng.choice(
        [
            b"",
            b"null",
            b"[]",
            b"1",
            b"<html>Unavailable</html>",
            valid[: rng.randint(1, len(valid) - 1)].encode(),
            b"\xef\xbb\xbf" + valid.encode(),
            valid.encode("utf-16"),
            valid.encode().replace(b"[]", b'["\xff"]'),
            b'{"count":NaN,"results":[]}',
            b'{"count":0,"results":[],"x":Infinity}',
            (
                '{"count":0,"results":[],"deep":' + nested(rng.choice([509, 510, 511, 600])) + "}"
            ).encode(),
            b'{"count":0,"results":[],"x":"\\ud800"}',
            b'{"count":0,"results":[],"x":"\\ud800","x":"ok"}',
            b'{"count":0,"results":[],"\\u0000x":1}',
            b'{"count":0,"results":[],"x\\u0000":1}',
            b'{"count":0,"results":[],"x":"\\ud83d\\ude00"}',
            b'{"count":' + b"1" * rng.randint(18, 30) + b',"results":[]}',
            b'{"count":1e400,"results":[]}',
            b'{"count":0,"results":[]} trailing',
            b'{"count":0,"results":[],}',
        ]
    )


def body(rng: random.Random, rccm: Rccm | None) -> bytes:
    if rng.random() < 0.15:
        return junk_body(rng)

    records = [record(rng, rccm) for _ in range(rng.choice([0, 0, 1, 1, 2, 3, 6]))]
    count: object = len(records)

    if rng.random() < 0.1:
        count = rng.choice([len(records) + rng.randint(1, 3), "0", True, None, -1, 1.0, Raw("51")])

    results: object = records

    if rng.random() < 0.03:
        results = rng.choice([{}, Pairs([("1", {})]), None, "x"])

    payload: list[tuple[str, object]] = []

    if rng.random() > 0.02:
        payload.append(("count", count))

    if rng.random() > 0.02:
        payload.append(("results", results))

    if rng.random() < 0.1:
        payload.append(("next", None))

    rng.shuffle(payload)

    return dump(Pairs(payload), rng).encode()


def response(rng: random.Random, rccm: Rccm | None) -> dict[str, object]:
    if rng.random() < 0.03:
        return {"throw": True}

    status = 200 if rng.random() < 0.9 else rng.choice([201, 204, 301, 302, 307, 400, 404, 503])
    headers = {}

    if status in (301, 302, 307) and rng.random() < 0.8:
        headers["Location"] = rng.choice(
            ["https://example.test/moved", "/relative", "http://example.com:bad/", ""]
        )

    return {
        "status": status,
        "headers": headers,
        "body": base64.b64encode(body(rng, rccm)).decode(),
    }


def clean_page(rng: random.Random, rccm: Rccm | None) -> dict[str, object]:
    """A well-formed page whose rows are near misses of the searched number."""
    rows: list[object] = []

    if rccm is not None:
        for _ in range(rng.randint(0, 3)):
            sequence = str(int(rccm.sequence_number) + rng.randint(1, 9))
            rows.append(
                {"Numéro RC": f"RB/{rccm.registry_code}/{rccm.year} {rccm.category} {sequence}"}
            )

    payload = {"count": len(rows), "results": rows}

    return {"status": 200, "body": base64.b64encode(dump(payload, rng).encode()).decode()}


def check_cases(seed: int) -> list[dict[str, object]]:
    rng = random.Random(seed)
    generated = []

    for _ in range(4000):
        raw = random_rccm(rng)

        # About one input in ten stays invalid; the others are drawn until they are valid.
        if rng.random() < 0.9:
            while not Rccm.is_valid(raw):
                raw = random_rccm(rng)

        rccm = Rccm.try_parse(raw)
        companies, establishments = rng.choice(
            [
                (
                    "https://gdb.guichet.investbenin.bj/data-view/pm/latest/5",
                    "https://gdb.monentreprise.bj/data-view/registre%20pp/latest/310",
                ),
                ("https://example.test/companies", "https://example.test/establishments"),
                ("https://example.test/companies?token=a", "https://example.test/est?token=b"),
            ]
        )
        generated.append(
            {
                "op": "check",
                "input": raw,
                "enabled": rng.random() < 0.95,
                "companies_url": companies,
                "establishments_url": establishments,
                "responses": [
                    # Some checks only receive clean pages, so that NOT_FOUND is reached.
                    response(rng, rccm) if rng.random() < 0.85 else clean_page(rng, rccm)
                    for _ in range(4)
                ],
            }
        )

    return [case for case in generated if not has_surrogate(str(case["input"]))]


ENV_VALUES = [
    "true", "TRUE", "(true)", "false", "(False)", "1", "0", "yes", "no", "on", "off", " on ",
    "\x0btrue\x0b", "\x0ctrue", "\ttrue\n", "maybe", "", "null", "(null)", "empty", "(Empty)",
    "'yes'", '"1"', "'a\nb'", "'mismatched\"", "5", "5.5", " 5 ", "\x0b2.5\x0c", "1e3", "1e309",
    "-1", "abc", "0x1A", "1_0", ".5", "5.", "+3", "inf", "https://example.test/x",
    "'https://example.test/quoted'",
]  # fmt: skip


def environment_cases(seed: int) -> list[dict[str, object]]:
    rng = random.Random(seed)
    names = [
        "BENIN_RCCM_APIEX_ENABLED",
        "BENIN_RCCM_APIEX_TIMEOUT",
        "BENIN_RCCM_APIEX_COMPANIES_URL",
        "BENIN_RCCM_APIEX_ESTABLISHMENTS_URL",
    ]

    return [
        {
            "op": "environment",
            "environ": {name: rng.choice(ENV_VALUES) for name in names if rng.random() < 0.7},
        }
        for _ in range(1500)
    ]


TYPED_VALUES: list[object] = [
    True, False, 0, 1, 2, -1, 1.0, 1.5, 0.0, 2.5, 1e308, "yes", "no", "x", "3", " 4 ", "abc",
    "", None, [], {}, "https://example.test/x",
]  # fmt: skip


def value_cases(seed: int) -> list[dict[str, object]]:
    rng = random.Random(seed)

    return [
        {
            "op": "values",
            "enabled": rng.choice(TYPED_VALUES),
            "timeout": rng.choice(TYPED_VALUES),
            "companies_url": rng.choice(TYPED_VALUES),
            "establishments_url": rng.choice(TYPED_VALUES),
        }
        for _ in range(1000)
    ]
