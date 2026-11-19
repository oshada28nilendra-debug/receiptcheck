from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def make_demo(output):
    destination = Path(output)
    destination.mkdir(parents=True, exist_ok=True)
    try:
        font = ImageFont.truetype("DejaVuSansMono.ttf", 27)
    except OSError:
        font = ImageFont.load_default(size=27)
    cases = {"matching": "23.50", "mismatch": "26.50"}
    for case, total in cases.items():
        image = Image.new("L", (680, 490), 255)
        draw = ImageDraw.Draw(image)
        lines = [
            "DEMO MARKET SDN BHD", "Date: 19/11/2026", "Rice          15.00",
            "Fruit          8.00", "Subtotal      23.00", "Tax            1.50",
            "Discount       1.00", f"Grand Total   {total}", "Thank you",
        ]
        for index, line in enumerate(lines):
            draw.text((32, 25 + 49 * index), line, font=font, fill=0)
        image.save(destination / f"{case}.png")
    return {"source": "synthetic", "images": [str(destination / f"{case}.png") for case in cases]}
