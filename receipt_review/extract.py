from collections import defaultdict
from dataclasses import dataclass, asdict
from datetime import date
from decimal import Decimal
import re

FIELDS = ("company", "date", "total", "subtotal", "tax", "discount", "service")
DEFAULT_THRESHOLDS = {"company": 0.65, "date": 0.65, "total": 0.72}
MONEY = re.compile(r"(?<![\w.,+\-])[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}(?![\d.,])")
DATE = re.compile(r"\b(?:\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}[-/.]\d{1,2}[-/.]\d{2}(?:\d{2})?)\b")
LABELS = (
    ("subtotal", r"\bsub[\s-]*total\b", 0.96),
    ("discount", r"\b(?:total\s+)?discounts?\b", 0.96),
    ("tax", r"\b(?:total\s+tax|tax\s+(?:amount|total)|tax|gst|vat|sst)\b", 0.89),
    ("service", r"\bservice\s+(?:fee|charge)\b", 0.94),
    ("total", r"\b(?:grand\s+total|nett?\s+total|total\s+payable|amount\s+due|balance\s+due)\b", 0.99),
    ("total", r"\btotal\b", 0.86),
)
EXCLUDED = re.compile(r"\b(?:change|cash|tendered|rounding|qty|items?|you saved|savings|before tax|taxable|inclusive|relief|exempt)\b", re.I)
ADJUSTMENT = re.compile(r"\b(?:rounding|inclusive|incl\.?\s+tax|tax included|deposit|delivery|shipping|refund|adjustment|tip|gratuity)\b", re.I)
AMOUNT_FIELDS = ("subtotal", "tax", "discount", "service", "total")


@dataclass(frozen=True)
class Candidate:
    value: str
    score: float
    source: str
    bbox: tuple | None


def display_date(raw, day_first=True):
    a, b, c = re.split(r"[-/.]", raw)
    if len(a) == 4:
        year, month, day = map(int, (a, b, c))
    else:
        day, month, year = map(int, (a, b, c) if day_first else (b, a, c))
        if len(c) == 2:
            year += 2000
    return date(year, month, day).isoformat()


def candidates(lines, day_first):
    found = defaultdict(list)
    for i, line in enumerate(lines):
        if i < 6 and re.search(r"[a-zA-Z]{2}", line.text) and not re.search(
            r"receipt|invoice|^welcome|^tel|^date|^tax|^cash|\bNO\.|\bJALAN\b|^\d+\s", line.text, re.I
        ):
            found["company"].append(Candidate(line.text, 0.72 * line.confidence + 0.28 - i * 0.06, line.text, line.box))
        for raw in DATE.findall(line.text):
            try:
                result = display_date(raw, day_first)
            except ValueError:
                continue
            found["date"].append(Candidate(result, (0.99 if re.search(r"\bdate\b", line.text, re.I) else 0.89) * line.confidence, line.text, line.box))
        if EXCLUDED.search(line.text):
            continue
        for name, label, weight in LABELS:
            match = re.search(label, line.text, re.I)
            if not match:
                continue
            post = line.text[match.end():]
            amounts = MONEY.findall(post)
            if amounts:
                raw = amounts[-1].replace(",", "")
                value = format(Decimal(raw), ".2f")
                found[name].append(Candidate(value, weight * line.confidence, line.text, line.box))
            break
    return found


def reconcile(fields, lines):
    total, subtotal = (fields[name]["value"] for name in ("total", "subtotal"))
    if total is None or subtotal is None:
        return {"status": "unavailable", "reason": "Both a labeled subtotal and total are required."}
    if any(ADJUSTMENT.search(line.text) for line in lines):
        return {"status": "unavailable", "reason": "An adjustment or tax-inclusion marker needs manual interpretation."}
    if any(fields[name]["reasons"] for name in AMOUNT_FIELDS):
        return {"status": "unavailable", "reason": "Confirm the uncertain amounts before reconciling."}
    get = lambda name: Decimal(fields[name]["value"] or "0")
    expected = get("subtotal") + get("tax") + get("service") - abs(get("discount"))
    difference = get("total") - expected
    return {
        "status": "matches" if difference == 0 else "mismatch",
        "expected": str(expected),
        "printed": total,
        "difference": str(difference),
        "assumption": "Unprinted components are treated as zero. The check uses only labeled receipt totals.",
    }


def extract(lines, thresholds=None, day_first=True, with_lines=False):
    cutoffs = DEFAULT_THRESHOLDS if thresholds is None else thresholds
    found = candidates(lines, day_first)
    fields = {}
    questions = []
    for name in FIELDS:
        ranked = sorted(found[name], key=lambda item: -item.score)
        best = ranked[0] if ranked else None
        reasons = []
        if not best and name in DEFAULT_THRESHOLDS:
            reasons.append("missing")
        if not best and name in ("tax", "discount", "service"):
            label = next(pattern for field, pattern, _ in LABELS if field == name)
            if any(re.search(label, line.text, re.I) and not EXCLUDED.search(line.text) for line in lines):
                reasons.append("label_without_amount")
        if best:
            if best.score < cutoffs.get(name, 0.68):
                reasons.append("low_score")
            competing = any(item.value != best.value and best.score - item.score <= 0.07 for item in ranked[1:])
            if competing and name != "company":
                reasons.append("competing_values")
        fields[name] = {
            "value": best.value if best else None,
            "score": round(best.score, 4) if best else None,
            "evidence": {"line": best.source, "bbox": best.bbox} if best else None,
            "reasons": reasons,
        }
        if reasons:
            questions.append(f"Confirm {name.replace('_', ' ')} ({', '.join(reasons)}).")
    arithmetic = reconcile(fields, lines)
    if arithmetic["status"] == "mismatch":
        questions.append("Check the subtotal, adjustments and printed total. The labeled amounts do not reconcile.")
    output = {"fields": fields, "arithmetic": arithmetic, "questions": questions}
    if with_lines:
        output["ocr_lines"] = [asdict(line) for line in lines]
    return output
