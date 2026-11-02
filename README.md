# Dubied manual

An HTML reproduction of the *Mode d'emploi* for Dubied hand knitting machines, in French, from a 1930 printed manual.

- [index.html](index.html) is the manual, with one `<article>` per printed page (3–62). It's hand-maintained, with no build step.
- [en.html](en.html) is a full English translation, built on the same page structure.
- [compare.html](compare.html) shows each page beside the original scan, with its transcription notes.
- [transcription-notes.md](transcription-notes.md) records misprints, doubtful readings and restored text.
- [pdf/](pdf/) holds the original scan, with a searchable OCR layer, and PDFs of both versions.

The scan is the authority. Peculiarities of the period style and spelling errors in the original are kept; other misprints are not generally meant to be.

## Viewing it

The comparison page needs HTTP, so serve the folder locally:

```sh
python3 -m http.server 8765 --bind 127.0.0.1
```

Then open <http://127.0.0.1:8765/>. The repo can also be published as is with GitHub Pages, from the root of `main`.

## Checking edits

```sh
python3 check_manual.py --print
```

This must report 0 problems. `--print` also checks the printed page count (60, or 61 in English with its notes page), and needs Google Chrome and `pdfinfo`.

## Rebuilding the PDFs

```sh
python3 build_pdfs.py
```

This prints both versions to `pdf/` with Google Chrome and recompresses their images, so it needs `pikepdf` and `Pillow`. Run it after any edit to the manual.

## Licences

The fonts are under the SIL Open Font License (`assets/LibreBodoni-OFL.txt`, `assets/OldStandard-OFL.txt`). `assets/libre-bodoni-slim-*` are Libre Bodoni with thinned outlines, for the lighter headings. PDF.js is under the Apache License 2.0 (`vendor/pdfjs/LICENSE`).
