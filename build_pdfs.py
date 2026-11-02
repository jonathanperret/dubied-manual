#!/usr/bin/env python3
"""Render index.html and en.html to pdf/ with headless Chrome.

Chrome stores figures uncompressed, so they are recompressed as JPEG afterwards.
Needs pikepdf and Pillow.
"""
import io
import subprocess
import tempfile
from pathlib import Path

import pikepdf
from PIL import ImageChops

ROOT = Path(__file__).parent
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
OUTPUTS = {"index.html": "Dubied_Manual_FR.pdf", "en.html": "Dubied_Manual_EN.pdf"}
JPEG_QUALITY = 85


def is_neutral(image):
    red, green, blue = image.split()
    return max(ImageChops.difference(a, b).getextrema()[1]
               for a, b in ((red, green), (green, blue))) < 12


def recompress(pdf):
    images = [o for o in pdf.objects
              if isinstance(o, pikepdf.Stream) and o.get("/Subtype") == "/Image"]
    masks = {o.SMask.objgen for o in images if "/SMask" in o}
    for image in images:
        if image.objgen in masks:
            continue
        pixels = pikepdf.PdfImage(image).as_pil_image().convert("RGB")
        gray = is_neutral(pixels)
        buffer = io.BytesIO()
        (pixels.convert("L") if gray else pixels).save(
            buffer, "JPEG", quality=JPEG_QUALITY, optimize=True)
        if buffer.tell() >= len(image.read_raw_bytes()):
            continue
        image.write(buffer.getvalue(), filter=pikepdf.Name.DCTDecode)
        image.ColorSpace = pikepdf.Name.DeviceGray if gray else pikepdf.Name.DeviceRGB
        image.BitsPerComponent = 8


def main():
    for page, name in OUTPUTS.items():
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / name
            subprocess.run(
                [CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                 "--generate-pdf-document-outline", f"--user-data-dir={tmp}/profile",
                 f"--print-to-pdf={raw}", (ROOT / page).as_uri()],
                check=True, capture_output=True, timeout=120,
            )
            with pikepdf.open(raw) as pdf:
                recompress(pdf)
                pdf.save(ROOT / "pdf" / name)


if __name__ == "__main__":
    main()
