"""Fetch a small reproducible SROIE subset without bundling original images."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import time
from urllib.parse import urlencode
from urllib.request import urlopen


DATASET = "jsdnrs/ICDAR2019-SROIE"
ENDPOINT = "https://datasets-server.huggingface.co/rows?"


def fetch(url):
    for attempt in range(3):
        try:
            with urlopen(url, timeout=25) as response:
                return response.read()
        except OSError:
            if attempt == 2:
                raise
            time.sleep(attempt + 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--count", type=int, default=48, choices=range(1, 101), metavar="1..100")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    for split in ("train", "test"):
        query = urlencode({"dataset": DATASET, "config": "default", "split": split, "offset": 0, "length": args.count})
        rows = json.loads(fetch(ENDPOINT + query))["rows"]

        def download(item):
            row = item["row"]
            label = str(row["key"])
            image = f"{split}-{item['row_idx']:04}.jpg"
            path = args.output / image
            if not path.exists():
                path.write_bytes(fetch(row["image"]["src"]))
            return {"id": label, "image": image, "truth": row["entities"]}

        with ThreadPoolExecutor(max_workers=8) as pool:
            records = list(pool.map(download, rows))
        if len(records) != args.count:
            raise RuntimeError(f"Expected {args.count} records in {split}, got {len(records)}")
        (args.output / f"{split}.json").write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
        print(f"{split}: {len(records)} receipt images", flush=True)


if __name__ == "__main__":
    main()
