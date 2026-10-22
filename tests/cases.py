"""Test vectors ported from the PHP package's tests/Support/IdentifierCases.php.

Special characters are built with chr() so that the source stays plain ASCII.
"""

from benin_business_id import FailureReason, TaxpayerType
from benin_business_id._clock import current_year

NBSP = chr(0x00A0)
NARROW_NBSP = chr(0x202F)
EM_SPACE = chr(0x2003)
# A lone surrogate is the Python counterpart of the PHP vectors' invalid UTF-8 byte "\xFF".
INVALID_UTF8 = chr(0xDCFF)


def fullwidth(digits: str) -> str:
    return "".join(chr(0xFF10 + int(digit)) for digit in digits)


def valid_ifu() -> list[tuple[str, str, TaxpayerType, int]]:
    return [
        ("3202444139959", "3202444139959", TaxpayerType.COMPANY, 2024),
        ("3.201.200.247.219", "3201200247219", TaxpayerType.COMPANY, 2012),
        ("32009008191 13", "3200900819113", TaxpayerType.COMPANY, 2009),
        (f"{NBSP}32024{NARROW_NBSP}44139959\t\n", "3202444139959", TaxpayerType.COMPANY, 2024),
        ("4201710116446", "4201710116446", TaxpayerType.PUBLIC_ENTITY, 2017),
        ("5201000673108", "5201000673108", TaxpayerType.INTERNATIONAL_ORGANIZATION, 2010),
        ("6201001214905", "6201001214905", TaxpayerType.NGO, 2010),
        # Synthetic individual identifiers; an accidental real-world assignment cannot be
        # ruled out.
        ("1201500000000", "1201500000000", TaxpayerType.INDIVIDUAL, 2015),
        ("0201500000000", "0201500000000", TaxpayerType.INDIVIDUAL, 2015),
        ("2201500000000", "2201500000000", TaxpayerType.INDIVIDUAL, 2015),
    ]


def invalid_ifu() -> list[tuple[str, FailureReason]]:
    return [
        ("", FailureReason.INVALID_LENGTH),
        ("   ", FailureReason.INVALID_LENGTH),
        ("320244413995", FailureReason.INVALID_LENGTH),
        ("32024441399590", FailureReason.INVALID_LENGTH),
        ("3202444139A59", FailureReason.INVALID_CHARACTERS),
        ("IFU : 3202444139959", FailureReason.INVALID_CHARACTERS),
        ("BJ-IFU-3200901353510", FailureReason.INVALID_CHARACTERS),
        ("7202400000000", FailureReason.UNKNOWN_TAXPAYER_TYPE),
        ("9999900000001", FailureReason.UNKNOWN_TAXPAYER_TYPE),
        ("5200081145006", FailureReason.INVALID_YEAR),
        ("2977421186134", FailureReason.INVALID_YEAR),
        (f"3{current_year() + 1}00000000", FailureReason.INVALID_YEAR),
        ("3200500000000", FailureReason.INVALID_YEAR),
        ("3202444139959:", FailureReason.INVALID_CHARACTERS),
        (f"3202444139959{INVALID_UTF8}", FailureReason.INVALID_CHARACTERS),
        (fullwidth("3202444139959"), FailureReason.INVALID_CHARACTERS),
        ("A", FailureReason.INVALID_CHARACTERS),
        ("9999", FailureReason.INVALID_LENGTH),
    ]


def valid_rccm() -> list[tuple[str, str, int]]:
    return [
        ("RB/COT/18 B 22272", "RB/COT/18 B 22272", 2018),
        ("RB/COT/07-B-1432", "RB/COT/07 B 1432", 2007),
        ("RB/COT/07/B 1351", "RB/COT/07 B 1351", 2007),
        ("RB KDI 22 B 137", "RB/KDI/22 B 137", 2022),
        ("RB/Cot/13B9933", "RB/COT/13 B 9933", 2013),
        ("RBCOT24B38169", "RB/COT/24 B 38169", 2024),
        ("RB/COT/2005 B 0040", "RB/COT/2005 B 0040", 2005),
        ("RB/LKS/2008-B-180", "RB/LKS/2008 B 180", 2008),
        ("RB/PN/11 B 303", "RB/PN/11 B 303", 2011),
        ("RB/ABY/94 A 1215", "RB/ABY/94 A 1215", 1994),
        ("RB/PNO/23 C 28", "RB/PNO/23 C 28", 2023),
        ("RB/COT/23 D 232", "RB/COT/23 D 232", 2023),
        ("RB/COT/20 E 2841", "RB/COT/20 E 2841", 2020),
        ("RB/ABC/26 B 11379", "RB/ABC/26 B 11379", 2026),
        (f"{EM_SPACE}RB/PKO/18{NBSP}A{NARROW_NBSP}00001", "RB/PKO/18 A 00001", 2018),
    ]


def invalid_rccm() -> list[tuple[str, FailureReason]]:
    return [
        ("RCCM : RB/COT/24 B 39072", FailureReason.INVALID_CHARACTERS),
        ("RB/COT/07 B 2058 (Ancien n\N{DEGREE SIGN}: 02 B 1545)", FailureReason.INVALID_CHARACTERS),
        ("RCCM RB/COT/25 B 41160", FailureReason.INVALID_STRUCTURE),
        ("RB/PKO 18 B 277 du 13/06/2018", FailureReason.INVALID_STRUCTURE),
        ("BJ/COT/18 B 22272", FailureReason.INVALID_COUNTRY),
        ("RB/CO/18 B 22272", FailureReason.UNKNOWN_REGISTRY),
        ("RB/OUI/22 B 12", FailureReason.UNKNOWN_REGISTRY),
        ("RB/ODH/23 B 12", FailureReason.UNKNOWN_REGISTRY),
        ("RB/COT/018 B 22272", FailureReason.INVALID_STRUCTURE),
        ("RB/COT/18 22272", FailureReason.INVALID_STRUCTURE),
        ("RB/COT/18 B", FailureReason.INVALID_STRUCTURE),
        ("RB/COT/18 B 1234567", FailureReason.INVALID_LENGTH),
        ("RB/COT/24 M 12", FailureReason.UNKNOWN_CATEGORY),
        ("RB/COT/2021 B 12", FailureReason.INVALID_YEAR),
        ("RB/COT/85 B 12", FailureReason.INVALID_YEAR),
        ("RB COTONOU 2005 M 2323", FailureReason.INVALID_STRUCTURE),
        ("CM-YDE-01-2015-B23-00010", FailureReason.INVALID_STRUCTURE),
        ("3200700019113", FailureReason.INVALID_STRUCTURE),
        ("24905-B", FailureReason.INVALID_STRUCTURE),
        ("", FailureReason.INVALID_LENGTH),
        (" .- ", FailureReason.INVALID_LENGTH),
        (f"RB/COT/18 B 12{INVALID_UTF8}", FailureReason.INVALID_CHARACTERS),
        ("BJ/ZZZ/1985 M 1234567", FailureReason.INVALID_LENGTH),
        ("BJ/ZZZ/1985 M 12", FailureReason.INVALID_COUNTRY),
        ("RB/ZZZ/1985 M 12", FailureReason.UNKNOWN_REGISTRY),
        ("RB/ODH/2021 M 12", FailureReason.UNKNOWN_CATEGORY),
        ("RB/ODH/2021 B 12", FailureReason.INVALID_YEAR),
    ]
