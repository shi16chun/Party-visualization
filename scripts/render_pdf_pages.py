#!/usr/bin/env python3
"""Rasterize a PDF to per-page PNGs for visual QA."""

from pathlib import Path
import sys
import fitz


if len(sys.argv) != 3:
    raise SystemExit("Usage: render_pdf_pages.py INPUT.pdf OUTPUT_DIR")

pdf_path = Path(sys.argv[1]).resolve()
out_dir = Path(sys.argv[2]).resolve()
out_dir.mkdir(parents=True, exist_ok=True)
doc = fitz.open(pdf_path)
matrix = fitz.Matrix(2.0, 2.0)
for i, page in enumerate(doc, start=1):
    pix = page.get_pixmap(matrix=matrix, alpha=False)
    pix.save(out_dir / f"page-{i:03d}.png")
print(f"Rendered {len(doc)} pages to {out_dir}")
