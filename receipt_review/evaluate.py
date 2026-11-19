from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re

from .extract import DEFAULT_THRESHOLDS, display_date, extract
from .ocr import read_image


def normalize(field, value, day_first=True):
    if not value:
        return None
    if field == "company":
        return re.sub(r"[^a-z0-9]", "", value.casefold()) or None
    if field == "date":
        try:
            return display_date(value.strip(), day_first)
        except ValueError:
            return None
    try:
        cleaned = re.sub(r"^(?:RM|MYR)\s*", "", value.strip(), flags=re.I)
        amount = Decimal(cleaned.replace(",", "").replace("$", ""))
        return amount if amount.is_finite() else None
    except InvalidOperation:
        return None


def collect(manifest, jobs=4):
    path = Path(manifest)
    records = json.loads(path.read_text(encoding="utf-8"))
    if not records:
        raise ValueError("Manifest contains no receipts")
    if len({row["id"] for row in records}) != len(records):
        raise ValueError("Receipt IDs must be unique")

    def process(row):
        lines = read_image(path.parent / row["image"])
        return row, lines

    with ThreadPoolExecutor(max_workers=jobs) as pool:
        return list(pool.map(process, records))


def measure(records, thresholds, day_first=True):
    predictions = [(row, extract(lines, thresholds, day_first)) for row, lines in records]
    report = {}
    for name in DEFAULT_THRESHOLDS:
        labeled = correct = accepted = accepted_correct = 0
        for row, result in predictions:
            truth = normalize(name, row["truth"].get(name), day_first)
            if truth is None:
                continue
            labeled += 1
            field = result["fields"][name]
            match = normalize(name, field["value"], day_first) == truth
            correct += match
            if not field["reasons"]:
                accepted += 1
                accepted_correct += match
        report[name] = {
            "labeled": labeled, "correct": correct, "accepted": accepted,
            "accepted_correct": accepted_correct,
            "exact_match": correct / labeled if labeled else None,
            "coverage": accepted / labeled if labeled else None,
            "accepted_precision": accepted_correct / accepted if accepted else None,
        }
    return {
        "receipts": len(records),
        "fields": report,
        "receipts_with_questions": sum(bool(result["questions"]) for _, result in predictions),
        "arithmetic_status_counts": {
            state: sum(result["arithmetic"]["status"] == state for _, result in predictions)
            for state in ("matches", "mismatch", "unavailable")
        },
    }


def choose_thresholds(records, precision=0.85, minimum=6, day_first=True):
    grid = [i / 100 for i in range(40, 101, 2)]
    cutoffs = {}
    for cutoff in grid:
        metrics = measure(records, dict.fromkeys(DEFAULT_THRESHOLDS, cutoff), day_first)["fields"]
        for name, stats in metrics.items():
            if name not in cutoffs and stats["accepted"] >= minimum and stats["accepted_precision"] >= precision:
                cutoffs[name] = cutoff
    return {name: cutoffs.get(name, 1.01) for name in DEFAULT_THRESHOLDS}
