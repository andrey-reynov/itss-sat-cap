from __future__ import annotations

import re
from pathlib import Path

from render_markdown_pdf import ROOT, render_one


DIAGRAMS_MD = ROOT / "docs" / "diagrams.md"
OUTPUT_DIR = ROOT / "pdf" / "diagrams_sections"
TMP_DIR = ROOT / ".tmp-diagrams"


def slugify(text: str) -> str:
    cleaned = text.lower()
    cleaned = re.sub(r"[^a-zа-я0-9]+", "-", cleaned, flags=re.IGNORECASE)
    return cleaned.strip("-") or "section"


def split_sections(markdown_text: str) -> list[tuple[str, str]]:
    intro, *parts = re.split(r"(?m)^##\s+", markdown_text)
    sections: list[tuple[str, str]] = []
    for part in parts:
        lines = part.splitlines()
        title = lines[0].strip()
        body = "\n".join(lines[1:]).strip()
        full_text = f"# {title}\n\n{body}\n"
        sections.append((title, full_text))
    return sections


def main() -> None:
    markdown_text = DIAGRAMS_MD.read_text(encoding="utf-8")
    sections = split_sections(markdown_text)
    TMP_DIR.mkdir(exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for index, (title, content) in enumerate(sections, start=1):
        filename = f"{index:02d}-{slugify(title)}.md"
        tmp_md = TMP_DIR / filename
        tmp_md.write_text(content, encoding="utf-8")
        pdf_path = render_one(tmp_md, OUTPUT_DIR)
        print(f"Rendered section: {title} -> {pdf_path}")


if __name__ == "__main__":
    main()
