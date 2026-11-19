# 05 · Receipt Reader That Knows When to Ask

Read a single English receipt image on your CPU. The reader extracts the merchant, date and printed total, and looks for labeled subtotal, tax, service charge and discount. Each proposed value includes the OCR line and its bounding box. Missing, weak or conflicting values yield a confirmation question.

## Install

Use Python 3.10 or newer and Tesseract 5 with its `eng` language data. Check `tesseract --list-langs` before running the CLI. On Debian or Ubuntu the system packages are `tesseract-ocr` and `tesseract-ocr-eng`. Run the Python commands from this folder.

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
receipt-review --help
```

On Windows PowerShell, activate the environment with `.venv\Scripts\Activate.ps1` and put Tesseract on PATH. Inference runs locally after setup.

## Scan a receipt

```sh
receipt-review scan path/to/receipt.jpg --output outputs/receipt.json
```

Add `--include-ocr` to see all recognized lines. Add `--month-first` for receipts that use month/day/year. The default is day/month/year, and ISO dates keep their year/month/day order. Evidence boxes are pixel coordinates `[left, top, right, bottom]` in the EXIF-oriented image.

The reader uses grayscale, resizing and contrast preprocessing, then pretrained Tesseract English OCR. It combines OCR word scores and label strength to propose field values. Review scores are heuristic scores. Pass `--profile reports/review-profile.json` to apply the fitted SROIE thresholds with the day-first convention.

Arithmetic uses decimal cents and checks `subtotal + tax + service − discount = printed total`. A match means the parsed labels satisfy this equation under the assumption that unprinted components are zero. A mismatch preserves the printed value and asks the user to check both sides. Unknown adjustments, tax inclusion and uncertain parsed amounts can make the check unavailable.

## Synthetic smoke test

```sh
receipt-review make-demo outputs/demo
receipt-review scan outputs/demo/matching.png
receipt-review scan outputs/demo/mismatch.png
python -m unittest discover -s tests -v
```

The generated receipts are synthetic images. Tesseract read an expected total of 23.50 in both examples. The matching case printed 23.50, and the mismatch case printed 26.50 and triggered a question for the 3.00 difference. The reports include the actual CLI outputs from both images.

## Reproduce the real-image evaluation

The source is the [SROIE dataset extension](https://huggingface.co/datasets/jsdnrs/ICDAR2019-SROIE), which contains annotated English-language Malaysian receipts. The download script takes the first 48 rows from each official split through the Hugging Face dataset viewer API. The underlying release and data card describe access and attribution. The project archive contains aggregate metrics and synthetic examples. Keep any downloaded receipt images and manifests local.

```sh
python scripts/fetch_sroie.py --output data/sroie --count 48
receipt-review fit-review data/sroie/train.json --target 0.85 --output outputs/profile.json
receipt-review evaluate data/sroie/test.json --profile outputs/profile.json --output outputs/test.json
```

Fitting selects the lowest per-field threshold on a fixed grid with at least six accepted labeled training examples and at least 85% empirical accepted precision. If no threshold qualifies, the profile sends all proposals of that field to review. Tesseract weights are reused as shipped. Evaluation checks receipt IDs for overlap with fitting and reports raw normalized exact match, automatic coverage and accepted precision. Company evaluation ignores punctuation, spaces and case. Date evaluation compares normalized ISO dates and total evaluation compares decimal values. Labels that fail to normalize are excluded from the corresponding field denominator and missing predictions count as errors. This subset is small and selected by dataset row order.

The recorded run used Python 3.12.14, Pillow 13.0.0 and Tesseract 5.5.0 with English trained data (SHA-256 `7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2`). See [measured test results](reports/sroie-test.json) and the [fitted profile](reports/review-profile.json).

### Held-out results

| Field | Raw exact match | Default precision on accepted fields | Fitted precision on accepted fields | Fitted coverage |
| --- | ---: | ---: | ---: | ---: |
| Merchant | 16/48 | 16/37 | Undefined | 0/48 |
| Date | 29/41 | 12/14 | 20/24 | 24/41 |
| Printed total | 25/48 | 10/10 | 11/11 | 11/48 |

Seven date labels failed date normalization. The fitted profile asked at least one question on all 48 receipts. Its accepted dates reached 83.3% observed precision, below the 85% training target. The arithmetic check reported unavailable on all 48 real receipts under the supported rules. The 10 unit tests and the two separately generated OCR smoke tests passed.

## Limitations

- The merchant rule uses the header. Logos, long addresses or the wrong reading order can cause incorrect accepted values.
- Blurry photographs, non-English text, handwritten receipts, decimal commas, multiple currencies and complex tax or promotion rules are outside the validated scope.
- SROIE supplies company, date, address and total labels. This prototype evaluates company, date and total. Real arithmetic outcomes lack reference labels here, so arithmetic correctness is demonstrated on synthetic cases and unit tests.
- A threshold selected on 48 labeled examples can fail to transfer across shops and cameras. The test results describe only the evaluated subset. The score is uncalibrated as a probability.

## Primary research

- Huang et al., *ICDAR2019 Competition on Scanned Receipt OCR and Information Extraction*. Defines the underlying benchmark. [Competition paper](https://arxiv.org/abs/2103.10213)
- Kim et al., *OCR-free Document Understanding Transformer* (ECCV 2022). Direct document-to-structure extraction is a useful comparison point for the evidence-based approach. [Donut paper](https://arxiv.org/abs/2111.15664)
- Cui et al., *PaddleOCR 3.0 Technical Report* (2025). Covers recent text recognition, layout parsing and field extraction systems. [Technical report](https://arxiv.org/abs/2507.05595)
