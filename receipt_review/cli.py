import argparse
import json
from pathlib import Path
import subprocess

from .demo import make_demo
from .evaluate import choose_thresholds, collect, measure
from .extract import DEFAULT_THRESHOLDS, extract
from .ocr import read_image


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read receipt evidence and surface extraction uncertainty")
    commands = parser.add_subparsers(dest="command", required=True)
    scan = commands.add_parser("scan")
    scan.add_argument("image", type=Path)
    scan.add_argument("--profile", type=Path)
    scan.add_argument("--include-ocr", action="store_true")
    fit = commands.add_parser("fit-review")
    fit.add_argument("manifest", type=Path)
    fit.add_argument("--target", type=float, default=0.85)
    assess = commands.add_parser("evaluate")
    assess.add_argument("manifest", type=Path)
    assess.add_argument("--profile", type=Path)
    demo = commands.add_parser("make-demo")
    demo.add_argument("directory", type=Path)
    for command in (scan, fit, assess):
        command.add_argument("--output", type=Path)
        command.add_argument("--month-first", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "make-demo":
            print(json.dumps(make_demo(args.directory), indent=2))
            return
        day_first = not args.month_first
        profile = json.loads(args.profile.read_text(encoding="utf-8")) if getattr(args, "profile", None) else None
        cutoffs = profile["thresholds"] if profile else DEFAULT_THRESHOLDS
        if profile and profile["day_first"] != day_first:
            parser.error("The profile was fitted with a different date convention")
        if args.command == "scan":
            result = extract(read_image(args.image), cutoffs, day_first, args.include_ocr)
        else:
            records = collect(args.manifest)
            ids = {row["id"] for row, _ in records}
            if args.command == "fit-review":
                if not 0 < args.target <= 1:
                    parser.error("Target precision must lie between 0 (exclusive) and 1")
                cutoffs = choose_thresholds(records, args.target, day_first=day_first)
                result = {"thresholds": cutoffs, "day_first": day_first, "fitted_ids": sorted(ids),
                          "target_precision": args.target, "training": measure(records, cutoffs, day_first)}
            else:
                if profile and ids.intersection(profile["fitted_ids"]):
                    parser.error("Evaluation records overlap with the fitting manifest")
                result = {"default": measure(records, DEFAULT_THRESHOLDS, day_first)}
                if profile:
                    result["fitted"] = measure(records, cutoffs, day_first)
        payload = json.dumps(result, indent=2) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(payload, encoding="utf-8")
        else:
            print(payload, end="")
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        parser.exit(2, f"receipt-review: {error}\n")


if __name__ == "__main__":
    main()
