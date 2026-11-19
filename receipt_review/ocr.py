from collections import defaultdict
import csv
from dataclasses import dataclass
from io import BytesIO, StringIO
import os
import subprocess

from PIL import Image, ImageOps


@dataclass(frozen=True)
class Line:
    text: str
    confidence: float
    box: tuple[int, int, int, int] | None = None


def read_tsv(tsv, scale_x=1, scale_y=1):
    groups = defaultdict(list)
    for word in csv.DictReader(StringIO(tsv), delimiter="\t"):
        if word["level"] == "5" and word["text"].strip() and float(word["conf"]) >= 0:
            key = tuple(word[name] for name in ("page_num", "block_num", "par_num", "line_num"))
            groups[key].append(word)
    lines = []
    for words in groups.values():
        x, y, w, h = ([int(word[name]) for word in words] for name in ("left", "top", "width", "height"))
        box = (
            round(min(x) / scale_x),
            round(min(y) / scale_y),
            round(max(a + b for a, b in zip(x, w)) / scale_x),
            round(max(a + b for a, b in zip(y, h)) / scale_y),
        )
        text = " ".join(word["text"].strip() for word in words)
        confidence = min(float(word["conf"]) for word in words) / 100
        lines.append(Line(text, confidence, box))
    return sorted(lines, key=lambda line: (line.box[1], line.box[0]))


def read_image(path):
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source).convert("L")
    width, height = image.size
    scale = min(1400 / max(width, height), max(1.0, 800 / width))
    image = image.resize((max(1, round(width * scale)), max(1, round(height * scale))), Image.Resampling.LANCZOS)
    image = ImageOps.autocontrast(image, cutoff=1)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    environment = dict(os.environ)
    environment.setdefault("OMP_THREAD_LIMIT", "1")
    try:
        result = subprocess.run(
            ["tesseract", "stdin", "stdout", "-l", "eng", "--psm", "6", "tsv"],
            input=buffer.getvalue(), capture_output=True, timeout=45, check=True, env=environment,
        )
    except FileNotFoundError as error:
        raise RuntimeError("Install Tesseract and its English model") from error
    except subprocess.CalledProcessError as error:
        raise RuntimeError(error.stderr.decode(errors="replace").strip()) from error
    return read_tsv(result.stdout.decode(errors="replace"), image.width / width, image.height / height)
