from __future__ import annotations

import re


LEVERAGED_PATTERNS = [r"2X", r"레버리지", r"선물레버리지", r"블룸버그레버리지"]
INVERSE_PATTERNS = [r"인버스", r"선물인버스", r"\b-1X\b", r"\b-2X\b"]
SYNTHETIC_PATTERNS = [r"합성", r"\(H\)", r"TRS"]
FOREIGN_PATTERNS = [
    r"미국",
    r"글로벌",
    r"나스닥",
    r"S&P",
    r"다우",
    r"일본",
    r"중국",
    r"차이나",
    r"인도",
    r"베트남",
    r"유럽",
]


def _matches_any(name: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, name, flags=re.IGNORECASE) for pattern in patterns)


def classify_etf_name(name: str) -> dict[str, bool]:
    normalized = name or ""
    return {
        "is_leveraged": _matches_any(normalized, LEVERAGED_PATTERNS),
        "is_inverse": _matches_any(normalized, INVERSE_PATTERNS),
        "is_synthetic": _matches_any(normalized, SYNTHETIC_PATTERNS),
        "is_foreign_underlying": _matches_any(normalized, FOREIGN_PATTERNS),
    }
