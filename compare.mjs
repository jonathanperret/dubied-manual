import * as pdfjs from "./vendor/pdfjs/pdf.min.mjs";

const PDF = "pdf/Dubied_Manual_Searchable_OCR.pdf";
const RENDER_MARGIN = "1500px";

pdfjs.GlobalWorkerOptions.workerSrc = new URL("vendor/pdfjs/pdf.worker.min.mjs", import.meta.url).href;

const manual = document.getElementById("manual");
const reference = document.getElementById("reference");
const status = document.getElementById("status");

function loaded(frame) {
  return new Promise((resolve, reject) => {
    function check() {
      const doc = frame.contentDocument;
      if (!doc || !doc.body) {
        reject(new Error(`Cannot load ${frame.title}.`));
      } else {
        resolve(doc);
      }
    }
    if (frame.contentDocument?.readyState === "complete"
        && frame.contentDocument.URL !== "about:blank") {
      check();
    } else {
      frame.addEventListener("load", check, { once: true });
      frame.addEventListener("error", () => reject(new Error(`Cannot load ${frame.title}.`)), { once: true });
    }
  });
}

function json(url) {
  return fetch(url).then(response => {
    if (!response.ok) throw new Error(`Cannot load ${url}: HTTP ${response.status}.`);
    return response.json();
  });
}

function parseNotes(text) {
  const notes = new Map();
  let items = null;
  for (const line of text.split("\n")) {
    const heading = line.match(/^## (.+)/);
    if (heading) {
      items = [];
      notes.set(heading[1], items);
    } else if (line.startsWith("- ")) {
      items?.push(line.slice(2));
    }
  }
  return notes;
}

function noteItem(note) {
  const item = document.createElement("li");
  const [, kind, text] = note.match(/^\*\*(.+?):\*\* (.*)$/) ?? [];
  if (kind) {
    const label = document.createElement("strong");
    label.textContent = `${kind}:`;
    item.append(label, ` ${text}`);
  } else {
    item.textContent = note;
  }
  return item;
}

async function renderPair(pdf, pair) {
  const { figure, canvas, entry } = pair;
  // Landscape pages are printed sideways: turn the scan to match the manual.
  const rotation = pair.page.querySelector(".landscape") ? 90 : 0;
  const [left, top, right, bottom] = entry.crop;
  const [x0, y0, x1, y1] = rotation ? [1 - bottom, left, 1 - top, right] : entry.crop;
  const page = await pdf.getPage(entry.pdfPage);
  const base = page.getViewport({ scale: 1, rotation });
  const cropWidth = (x1 - x0) * base.width;
  const cropHeight = (y1 - y0) * base.height;
  const fit = Math.min(figure.clientWidth / cropWidth, figure.clientHeight / cropHeight);
  const scale = fit * Math.max(window.devicePixelRatio, 2);
  canvas.width = Math.ceil(cropWidth * scale);
  canvas.height = Math.ceil(cropHeight * scale);
  const viewport = page.getViewport({
    scale,
    rotation,
    offsetX: -x0 * base.width * scale,
    offsetY: -y0 * base.height * scale,
  });
  await page.render({ canvasContext: canvas.getContext("2d"), viewport }).promise;
}

async function start() {
  const [manualDocument, referenceDocument, manifest, notesText] = await Promise.all([
    loaded(manual),
    loaded(reference),
    json("reference-pages.json"),
    fetch("transcription-notes.md").then(response => (response.ok ? response.text() : "")),
  ]);
  const notes = parseNotes(notesText);
  document.getElementById("notes").hidden = !notes.size;
  await manualDocument.fonts.ready;
  const pages = [...manualDocument.querySelectorAll("article.page")];
  if (!pages.length) throw new Error("The manual contains no pages.");
  const loading = pdfjs.getDocument({ url: PDF, disableAutoFetch: true, disableStream: true });
  loading.onProgress = ({ loaded, total }) => {
    if (total) status.textContent = `Loading PDF… ${Math.round(loaded / total * 100)}%`;
  };
  const pdf = await loading.promise;
  const pairs = pages.map(page => {
    const entry = manifest[page.id];
    if (!entry?.crop) throw new Error(`Missing reference for ${page.id}.`);
    const figure = referenceDocument.createElement("figure");
    figure.className = "reference-page";
    figure.id = page.id;
    const canvas = referenceDocument.createElement("canvas");
    canvas.setAttribute("role", "img");
    canvas.setAttribute("aria-label", `Reference scan — ${page.id.replace("page-", "page ")}`);
    figure.append(canvas);
    referenceDocument.body.append(figure);
    return { page, figure, canvas, entry, wanted: false, rendered: false };
  });

  // Pages render one at a time as they near the view, and are dropped when
  // they leave it, because every canvas holds about 10 MB of pixels.
  let rendering = false;
  async function renderNext() {
    if (rendering) return;
    const pair = pairs.find(candidate => candidate.wanted && !candidate.rendered);
    if (!pair) return;
    rendering = true;
    pair.rendered = true;
    try {
      await renderPair(pdf, pair);
    } catch (error) {
      showError(error);
    }
    rendering = false;
    renderNext();
  }

  const byFigure = new Map(pairs.map(pair => [pair.figure, pair]));
  const visibility = new reference.contentWindow.IntersectionObserver(changes => {
    for (const { target, isIntersecting } of changes) {
      const pair = byFigure.get(target);
      pair.wanted = isIntersecting;
      if (!isIntersecting && pair.rendered) {
        pair.rendered = false;
        pair.canvas.width = 0;
      }
    }
    renderNext();
  }, { root: referenceDocument, rootMargin: RENDER_MARGIN });

  // The notes follow the page crossing the upper third of the manual pane;
  // above the first page they show the general notes.
  let shownNotes = null;
  function updateNotes() {
    const y = manual.contentWindow.scrollY + manual.clientHeight / 3;
    const current = pairs.findLast(({ figure }) => parseFloat(figure.style.top) <= y);
    const section = current ? `Page ${current.page.id.replace("page-", "")}` : "General";
    if (section === shownNotes) return;
    shownNotes = section;
    const items = notes.get(section) ?? [];
    document.getElementById("notes-title").textContent = `Transcription notes — ${section} (${items.length})`;
    const list = document.getElementById("notes-list");
    list.replaceChildren(...items.map(noteItem));
    list.scrollTop = 0;
  }

  function align() {
    for (const { page, figure } of pairs) {
      const rect = page.getBoundingClientRect();
      figure.style.top = `${rect.top + manual.contentWindow.scrollY}px`;
      figure.style.width = `min(${rect.width}px, 100%)`;
      figure.style.height = `${rect.height}px`;
    }
    referenceDocument.body.style.height = `${manualDocument.documentElement.scrollHeight}px`;
    sync(manual, reference);
    updateNotes();
  }

  function sync(from, to) {
    const y = from.contentWindow.scrollY;
    if (Math.abs(to.contentWindow.scrollY - y) > 1) {
      to.contentWindow.scrollTo(to.contentWindow.scrollX, y);
    }
  }

  manual.contentWindow.addEventListener("scroll", () => {
    sync(manual, reference);
    updateNotes();
  }, { passive: true });
  reference.contentWindow.addEventListener("scroll", () => sync(reference, manual), { passive: true });
  const observer = new ResizeObserver(align);
  observer.observe(manualDocument.body);
  for (const page of pages) observer.observe(page);
  window.addEventListener("resize", align);
  align();
  for (const { figure } of pairs) visibility.observe(figure);
  status.hidden = true;
}

function showError(error) {
  console.error(error);
  status.textContent = `Comparison failed: ${error.message} Serve this folder over HTTP to view the comparison.`;
  status.setAttribute("role", "alert");
  status.hidden = false;
}

start().catch(showError);
