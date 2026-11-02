#!/usr/bin/env python3
"""Regression checks for index.html and en.html. Usage: check_manual.py [--print]

--print also renders to PDF with Chrome and checks the printed page count.
"""
import re
import subprocess
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).parent
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
FIRST_PAGE, LAST_PAGE = 3, 62
PAGES = ("index.html", "en.html")
VOID = {"meta", "link", "img", "br", "hr", "col"}
OPENING = r"^[a-zà-ÿœ]"
CLOSING = r"[.,:;!?»“)\]…*]$"


class Manual(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.problems = []
        self.ids = []
        self.hrefs = []
        self.classes = set()
        self.headings = []
        self.pages = []
        self.images = []
        self.figures = {}
        self.stack = []
        self.paragraph = None
        self.page = None
        self.containers = set()
        self.open_ended = False

    def problem(self, message):
        self.problems.append(f"{self.page or 'head'}: {message}")

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = (attrs.get("class") or "").split()
        self.classes.update(classes)
        if "style" in attrs:
            self.problem(f"inline style on <{tag}>")
        if "id" in attrs:
            self.ids.append(attrs["id"])
        if tag == "article":
            self.containers.clear()
            self.page = attrs.get("id")
            self.pages.append(self.page)
            if attrs.get("aria-label") != f"Page {self.page.split('-')[1]}":
                self.problem("aria-label does not match id")
        if tag == "a":
            self.hrefs.append((self.page, attrs.get("href", "")))
        if re.fullmatch(r"h[1-6]", tag):
            self.headings.append((self.page, int(tag[1])))
        if tag == "img":
            self.images.append((self.page, attrs.get("src"), attrs.get("alt", "")))
            if not ("width" in attrs and "height" in attrs) and not attrs["src"].endswith(".svg"):
                self.problem(f"image without dimensions: {attrs['src']}")
        if tag == "figure" and "id" in attrs:
            self.figures[attrs["id"]] = self.page
        if tag == "p" and self.page and "sheet" not in self.containers:
            self.paragraph = {"classes": classes, "text": ""}
        if tag == "div" and "sheet" in classes:
            self.containers.add("sheet")
        if tag not in VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag == "p" and self.paragraph:
            self.finish_paragraph()
        while self.stack and self.stack.pop() != tag:
            pass

    def handle_data(self, data):
        if self.paragraph is not None:
            self.paragraph["text"] += data
        if self.page and "a" not in self.stack and "figcaption" not in self.stack:
            for mention in re.findall(r"\b[Ff]ig\.\s*\d+", data):
                self.problem(f"unlinked reference: {mention}")

    def finish_paragraph(self):
        text = re.sub(r"\s+", " ", self.paragraph["text"]).strip()
        classes = self.paragraph["classes"]
        self.paragraph = None
        if not text or "folio" in classes:
            return
        split = self.open_ended and re.search(OPENING, text) and "cont" not in classes
        if split:
            self.problem(f"sentence split across paragraphs: {text[:50]}…")
        self.open_ended = not re.search(CLOSING, text) and "more" not in classes

def css_selectors():
    css = re.sub(r"/\*.*?\*/", "", (ROOT / "manual.css").read_text(), flags=re.S)
    return set(re.findall(r"\.([a-zA-Z][\w-]*)", css))


def check(manual, html):
    problems = list(manual.problems)
    expected = [f"page-{n}" for n in range(FIRST_PAGE, LAST_PAGE + 1)]
    if manual.pages != expected:
        problems.append("article pages are missing or out of order")
    duplicates = {i for i in manual.ids if manual.ids.count(i) > 1}
    if duplicates:
        problems.append(f"duplicate ids: {sorted(duplicates)}")
    for page, href in manual.hrefs:
        if href.startswith("#") and href[1:] not in manual.ids:
            problems.append(f"{page}: broken link {href}")
    for page, src, alt in manual.images:
        if not (ROOT / src).is_file():
            problems.append(f"{page}: missing image {src}")
        if not alt.strip() or alt == "Illustration":
            problems.append(f"{page}: missing alt text for {src}")
    previous = 1
    for page, level in manual.headings:
        if level > previous + 1:
            problems.append(f"{page}: heading jumps from h{previous} to h{level}")
        previous = level
    if sum(1 for _, level in manual.headings if level == 1) != 1:
        problems.append("expected exactly one h1")
    undefined = manual.classes - css_selectors()
    if undefined:
        problems.append(f"classes with no CSS: {sorted(undefined)}")
    for src in re.findall(r'src="(assets/[^"]+)"', html):
        if src.endswith(".png"):
            problems.append(f"PNG still referenced: {src}")
    used = set(re.findall(r'src="assets/([^"]+)"', html))
    used |= set(re.findall(r'url\("assets/([^"]+)"\)', (ROOT / "manual.css").read_text()))
    for file in (ROOT / "assets").iterdir():
        if file.name not in used and file.suffix != ".txt":
            problems.append(f"unused asset: {file.name}")
    return problems


def printed_pages(name):
    with tempfile.TemporaryDirectory() as tmp:
        pdf = Path(tmp) / "manual.pdf"
        subprocess.run(
            [CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
             f"--user-data-dir={tmp}/profile", f"--print-to-pdf={pdf}",
             (ROOT / name).as_uri()],
            check=True, capture_output=True, timeout=120,
        )
        info = subprocess.check_output(["pdfinfo", str(pdf)], text=True)
    return int(re.search(r"Pages:\s+(\d+)", info).group(1))


def main():
    failed = False
    for name in PAGES:
        html = (ROOT / name).read_text(encoding="utf8")
        manual = Manual()
        manual.feed(html)
        problems = check(manual, html)
        if "--print" in sys.argv:
            count = printed_pages(name)
            expected = LAST_PAGE - FIRST_PAGE + 1
            if count != expected:
                problems.append(f"prints to {count} pages, expected {expected}")
        for problem in problems:
            print(f"{name}: {problem}")
        print(f"{name}: {len(problems)} problem(s), {len(manual.pages)} pages, "
              f"{len(manual.images)} images, {len(html) // 1024} KB of HTML")
        failed = failed or bool(problems)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
