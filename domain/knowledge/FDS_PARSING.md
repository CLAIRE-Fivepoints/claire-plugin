---
domain: claire-plugin
category: knowledge
name: FDS_PARSING
title: "FDS — How to parse a Word (.docx) FDS with correct section numbering"
keywords: [fds, docx, word, parse, numbering, section, heading, "persona:fivepoints-dev", "persona:fivepoints-tester", fivepoints-dev]
updated: 2026-06-30
---

# FDS — Parsing a Word (.docx) with correct section numbering

## Why naïve heading counting fails

A `.docx` is a ZIP archive.  The visible section numbers ("9.1", "9.1.1") are
**not** stored as text in `word/document.xml` — they are rendered at view time
from a numbering definition in `word/numbering.xml`.

A Heading 1 that appears as "9" in Word has **no "9"** in `document.xml`.
Its paragraph only carries a reference to a numbering list and a level index.
If you count Heading1 paragraphs naively (1, 2, 3 …) you will get the wrong
chapter number whenever a list starts at a value other than 1.

**Real example (TFI One FDS):** the Contract Management chapter starts the
Heading1 counter at **8**, so the sections are 8, 9, 10 — not 1, 2, 3.
This is declared in `numbering.xml` as `<w:start w:val="8"/>` for level 0.

---

## How to parse it correctly (pure stdlib — no extra dependencies)

```python
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

W  = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
WN = W  # same namespace for numbering.xml

def _tag(ns, local):
    return f"{{{ns}}}{local}"

def parse_fds(docx_path: str | Path) -> list[dict]:
    """Return a list of headings: [{level: int, number: str, text: str}].

    level   — 0-based heading level (0 = Heading1, 1 = Heading2, …)
    number  — computed section number, e.g. "9.1.2"
    text    — heading text content
    """
    docx_path = Path(docx_path)
    with zipfile.ZipFile(docx_path) as z:
        doc_xml = z.read("word/document.xml")
        try:
            num_xml = z.read("word/numbering.xml")
        except KeyError:
            num_xml = None

    # --- 1. Build numbering start map from numbering.xml ---
    # Maps (numId, ilvl) -> start value
    start_map: dict[tuple[int, int], int] = {}
    # Maps numId -> abstractNumId
    num_to_abstract: dict[int, int] = {}

    if num_xml:
        nroot = ET.fromstring(num_xml)

        # abstractNum definitions
        abstract_starts: dict[tuple[int, int], int] = {}
        for aNum in nroot.findall(_tag(W, "abstractNum")):
            aId = int(aNum.get(_tag(W, "abstractNumId"), -1))
            for lvl in aNum.findall(_tag(W, "lvl")):
                ilvl = int(lvl.get(_tag(W, "ilvl"), 0))
                start_el = lvl.find(_tag(W, "start"))
                start_val = int(start_el.get(_tag(W, "val"), 1)) if start_el is not None else 1
                abstract_starts[(aId, ilvl)] = start_val

        # num instances -> abstractNum
        for num in nroot.findall(_tag(W, "num")):
            numId = int(num.get(_tag(W, "numId"), -1))
            ref = num.find(_tag(W, "abstractNumId"))
            if ref is not None:
                aId = int(ref.get(_tag(W, "val"), -1))
                num_to_abstract[numId] = aId
                # Override start values if any
                for lvlOverride in num.findall(_tag(W, "lvlOverride")):
                    ilvl = int(lvlOverride.get(_tag(W, "ilvl"), 0))
                    s = lvlOverride.find(f".//{_tag(W, 'start')}")
                    if s is not None:
                        start_map[(numId, ilvl)] = int(s.get(_tag(W, "val"), 1))
                    elif (aId, ilvl) in abstract_starts:
                        start_map[(numId, ilvl)] = abstract_starts[(aId, ilvl)]

        # Fill gaps from abstract definitions
        for (numId, aId) in num_to_abstract.items():
            for ilvl in range(10):
                if (numId, ilvl) not in start_map and (aId, ilvl) in abstract_starts:
                    start_map[(numId, ilvl)] = abstract_starts[(aId, ilvl)]

    # --- 2. Walk document.xml paragraphs ---
    droot  = ET.fromstring(doc_xml)
    body   = droot.find(f".//{_tag(W, 'body')}")
    counters: list[int] = []   # current counter per level
    results: list[dict] = []

    for para in body.findall(_tag(W, "p")):
        pPr  = para.find(_tag(W, "pPr"))
        if pPr is None:
            continue
        pStyle = pPr.find(_tag(W, "pStyle"))
        if pStyle is None:
            continue
        style_val = pStyle.get(_tag(W, "val"), "")

        # Match Heading1..Heading6 (Word uses "Heading1", "1", or localised names)
        level = None
        for i in range(1, 7):
            if style_val in (f"Heading{i}", str(i), f"heading{i}"):
                level = i - 1  # 0-based
                break
        if level is None:
            continue

        # Extract numId / ilvl from paragraph numbering properties
        numPr = pPr.find(_tag(W, "numPr"))
        numId = ilvl = None
        if numPr is not None:
            ilvl_el  = numPr.find(_tag(W, "ilvl"))
            numId_el = numPr.find(_tag(W, "numId"))
            if ilvl_el is not None:
                ilvl  = int(ilvl_el.get(_tag(W, "val"), level))
            if numId_el is not None:
                numId = int(numId_el.get(_tag(W, "val"), 0))

        effective_level = ilvl if ilvl is not None else level

        # Grow/shrink counter array
        if len(counters) <= effective_level:
            # Initialise new levels from start_map or 1
            while len(counters) <= effective_level:
                l = len(counters)
                start = start_map.get((numId, l), 1) if numId is not None else 1
                counters.append(start - 1)  # will be incremented below

        counters[effective_level] += 1
        # Reset all deeper levels
        for deeper in range(effective_level + 1, len(counters)):
            start = start_map.get((numId, deeper), 1) if numId is not None else 1
            counters[deeper] = start - 1

        section_number = ".".join(str(counters[i]) for i in range(effective_level + 1))

        # Extract text
        text = "".join(
            t.text or ""
            for t in para.iter(_tag(W, "t"))
        ).strip()

        results.append({"level": effective_level, "number": section_number, "text": text})

    return results
```

---

## Usage in a dev session

```python
# In the worktree, after downloading attachments:
from pathlib import Path

docx = next(Path(".fds-cache/<pbi>").glob("*.docx"))
headings = parse_fds(docx)

# Find your section:
for h in headings:
    print(f"{'  ' * h['level']}{h['number']}  {h['text']}")

# Filter to a specific chapter:
chapter = [h for h in headings if h["number"].startswith("9.1")]
```

**Expected output for TFI One Contract Management FDS:**
```
8      Contract Management Search
9      Contract Management Face Sheets
  9.1  Agency Face Sheet
    9.1.1  Navigation
    9.1.2  User Interfaces
    9.1.3  Business Rules
    9.1.4  Element Descriptions
    9.1.5  Security
  9.2  Service Provider Face Sheet
10     Agency/Service Provider Information
```

---

## How to consume a FDS section (mandatory checklist)

Every feature section in the TFI One FDS follows a fixed structure.
**Read every subsection — skipping any one is a scope error.**

### Standard subsection map

| Subsection | Contains | What to extract |
|------------|----------|-----------------|
| **X.X.1 Navigation** | Sidebar items, routes, breadcrumbs | Exact menu labels, route paths, which items are present/absent |
| **X.X.2 User Interfaces** | Wireframe mockups (images embedded in the .docx) | Field layout, component names, tab/card structure, exact label text |
| **X.X.3 Business Rules** | Numbered rules (BR#1, BR#2 …) | Every rule, one by one — derive what the code must enforce |
| **X.X.4 Element Descriptions** | Table: Element / Type / Description / Required | Every field name, its data type, and whether it is required |
| **X.X.5 Security** | Permission codes table | `PermissionCode` values, role access (SUPER_USER bypass?) |

### Common mistakes to avoid

- **Skipping X.X.2 (User Interfaces)** — the mockup is the authoritative source
  for label text. The FDS prose often uses a different label than the wireframe.
  When they disagree, **the wireframe wins** (e.g. "Contract Information" in the
  mockup vs "Contract Documents" in the prose).
- **Reading only the parent section** — subsections are separate Word headings;
  you must navigate to each one and read it individually.
- **Inferring Business Rules from prose** — BR#1, BR#2 … are numbered explicitly.
  List every one and map it to a code assertion. Never stop at BR#1 if BR#2 exists.
- **Ignoring "organization" / scoping clauses** — Business Rules often restrict
  which records are visible based on the current user's organization. Check every BR
  for a scoping condition before assuming global access.
- **Assuming element names from memory** — always read X.X.4 for the exact field
  name. `AgencyListModel` and `AgencyEditModel` have different fields; confusing them
  causes dead-property bugs.

### How to extract mockup images from a .docx

Images in `word/document.xml` are referenced as `<a:blip r:embed="rId..."/>`.
The actual files live in `word/media/image*.png` (or `.jpeg`, `.emf`) inside the ZIP.

```python
import zipfile
from pathlib import Path

def extract_images(docx_path: str | Path, out_dir: str | Path) -> list[Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    with zipfile.ZipFile(docx_path) as z:
        for name in z.namelist():
            if name.startswith("word/media/"):
                data = z.read(name)
                dest = out_dir / Path(name).name
                dest.write_bytes(data)
                saved.append(dest)
    return saved

# Usage — extract all mockup images for visual inspection:
images = extract_images(".fds-cache/<pbi>/FDS.docx", ".fds-cache/<pbi>/mockups/")
# Then Read each image file to inspect the wireframe.
```

---

## FDS Verification Report — required format

Before creating the PR, post a verification comment on the issue for every
subsection of your assigned chapter.  Use this exact format:

```
Sous-section: X.X.1 Navigation
Statut: ✅ Fait | ✅ Déjà fonctionnel | ⚠️ Écart noté | ❌ Non couvert
Preuve: <one-line evidence — grep result, file path, commit SHA, or "N/A + reason">
────────────────────────────────────────
Sous-section: X.X.2 User Interfaces
Statut: ✅ Conforme (écarts notés si applicable)
Preuve: <describe what the mockup shows and whether the implementation matches>
────────────────────────────────────────
Sous-section: X.X.3 Business Rules
Statut: ✅ Corrigé | ✅ Pré-existant
Preuve: <list each BR# and its disposition — never aggregate>
────────────────────────────────────────
Sous-section: X.X.4 Element Descriptions
Statut: ✅ Fait
Preuve: <N fields, tokenised/mapped — list any missing>
────────────────────────────────────────
Sous-section: X.X.5 Security
Statut: ✅ Fait
Preuve: <PermissionCode(s) applied, where, which commit>
```

### Rules for the verification report

- **One entry per subsection** — never combine X.X.3 and X.X.4 into one block.
- **Evidence must be concrete** — file path + line, grep output, or commit SHA.
  "I believe it works" is not evidence.
- **Wireframe discrepancies must be called out explicitly** in X.X.2, with a
  decision: which source wins and why. Default: wireframe wins over prose.
- **Every Business Rule gets its own line** in X.X.3. If BR#2 is pre-existing
  server-side (e.g. scoped by `IOrganizationalReference`), say so explicitly —
  don't silently skip it.
- **Post the report as an issue comment before pushing the PR** — the reviewer
  uses it to scope the review.

---

## Key rules

- **Never count headings naively** — always read `numbering.xml` first.
- The `w:start` value on level 0 tells you the real first chapter number.
- Child levels reset to their own `w:start` (usually 1) when the parent increments.
- If `numbering.xml` is absent (simple documents), fall back to counting from 1.
- The section number in the FDS must match what is stated in the PBI description exactly — verify mechanically, not by inference.
