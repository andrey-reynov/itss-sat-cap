from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parent
MARKED_UMD = ROOT / "node_modules" / "marked" / "lib" / "marked.umd.js"
MERMAID_JS = ROOT / "node_modules" / "mermaid" / "dist" / "mermaid.min.js"
CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


HTML_TEMPLATE = """<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <title>{title}</title>
  <style>
    @page {{
      size: A4;
      margin: 18mm 14mm 18mm 14mm;
    }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
      color: #111827;
      line-height: 1.55;
      font-size: 12px;
      background: #ffffff;
    }}
    main {{
      max-width: 980px;
      margin: 0 auto;
    }}
    h1, h2, h3 {{
      color: #0f172a;
      page-break-after: avoid;
    }}
    h1 {{
      border-bottom: 2px solid #dbeafe;
      padding-bottom: 8px;
    }}
    h2 {{
      margin-top: 1.8em;
      border-bottom: 1px solid #e5e7eb;
      padding-bottom: 6px;
    }}
    table {{
      border-collapse: collapse;
      width: 100%;
      margin: 16px 0;
      font-size: 11px;
    }}
    th, td {{
      border: 1px solid #d1d5db;
      padding: 8px 10px;
      text-align: left;
      vertical-align: top;
    }}
    th {{
      background: #f3f4f6;
    }}
    code {{
      background: #f3f4f6;
      padding: 0.15em 0.35em;
      border-radius: 4px;
      font-size: 0.95em;
    }}
    pre {{
      background: #0f172a;
      color: #e5e7eb;
      padding: 14px;
      border-radius: 8px;
      overflow-x: auto;
      white-space: pre-wrap;
    }}
    pre code {{
      background: transparent;
      padding: 0;
      color: inherit;
    }}
    blockquote {{
      border-left: 4px solid #93c5fd;
      margin: 1em 0;
      padding: 0.4em 1em;
      color: #334155;
      background: #f8fafc;
    }}
    img {{
      max-width: 100%;
    }}
    a {{
      color: #1d4ed8;
      text-decoration: none;
    }}
    ul, ol {{
      padding-left: 1.5em;
    }}
    .mermaid {{
      text-align: center;
      margin: 18px 0;
      page-break-inside: avoid;
      break-inside: avoid;
    }}
    .mermaid svg {{
      max-width: 100%;
      height: auto;
    }}
  </style>
</head>
<body>
  <main id="content"></main>
  <script>{marked_js}</script>
  <script>{mermaid_js}</script>
  <script>
    const markdownText = {markdown_json};
    marked.setOptions({{
      gfm: true,
      breaks: false
    }});
    document.getElementById("content").innerHTML = marked.parse(markdownText);
    mermaid.initialize({{
      startOnLoad: false,
      securityLevel: "loose",
      theme: "default",
      flowchart: {{ useMaxWidth: true, htmlLabels: true }}
    }});
  </script>
</body>
</html>
"""


def render_one(md_path: Path, out_dir: Path) -> Path:
    if not md_path.exists():
        raise FileNotFoundError(f"Markdown file not found: {md_path}")

    if not MARKED_UMD.exists() or not MERMAID_JS.exists():
        raise FileNotFoundError("Missing node_modules assets. Run `npm install` in the repository root first.")

    markdown_text = md_path.read_text(encoding="utf-8")
    html_text = HTML_TEMPLATE.format(
        title=html.escape(md_path.stem),
        marked_js=MARKED_UMD.read_text(encoding="utf-8"),
        mermaid_js=MERMAID_JS.read_text(encoding="utf-8"),
        markdown_json=json.dumps(markdown_text, ensure_ascii=False),
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = out_dir / f"{md_path.stem}.pdf"

    with sync_playwright() as p:
        launch_kwargs = {"headless": True}
        if Path(CHROME_PATH).exists():
            launch_kwargs["executable_path"] = CHROME_PATH
        browser = p.chromium.launch(**launch_kwargs)
        page = browser.new_page(viewport={"width": 1440, "height": 2200}, device_scale_factor=2)
        page.set_content(html_text, wait_until="load")
        page.wait_for_timeout(300)
        mermaid_blocks = page.locator("pre code.language-mermaid")
        count = mermaid_blocks.count()
        for i in range(count):
            code_text = mermaid_blocks.nth(i).inner_text()
            page.evaluate(
                """({ index, text }) => {
                    const blocks = Array.from(document.querySelectorAll('pre code.language-mermaid'));
                    const codeBlock = blocks[index];
                    const pre = codeBlock.closest('pre');
                    const wrapper = document.createElement('div');
                    wrapper.className = 'mermaid';
                    wrapper.textContent = text;
                    pre.replaceWith(wrapper);
                }""",
                {"index": i, "text": code_text},
            )
        if count:
            page.evaluate(
                """async () => {
                    const nodes = Array.from(document.querySelectorAll('.mermaid'));
                    for (let i = 0; i < nodes.length; i += 1) {
                        const node = nodes[i];
                        const definition = node.textContent;
                        const { svg } = await mermaid.render(`mermaid-diagram-${i}`, definition);
                        node.innerHTML = svg;
                    }
                }"""
            )
            page.wait_for_timeout(500)
        page.pdf(
            path=str(pdf_path),
            print_background=True,
            format="A4",
            margin={"top": "16mm", "right": "12mm", "bottom": "16mm", "left": "12mm"},
        )
        browser.close()
    return pdf_path


def collect_markdown_files(paths: list[str]) -> list[Path]:
    collected: list[Path] = []
    for raw in paths:
        path = (ROOT / raw).resolve() if not Path(raw).is_absolute() else Path(raw)
        if path.is_dir():
            collected.extend(sorted(path.glob("*.md")))
        else:
            collected.append(path)
    return collected


def main() -> None:
    parser = argparse.ArgumentParser(description="Render Markdown files with Mermaid diagrams to PDF.")
    parser.add_argument("paths", nargs="+", help="Markdown files or directories to render.")
    parser.add_argument("--output-dir", default="pdf", help="Output directory for generated PDFs.")
    args = parser.parse_args()

    md_files = collect_markdown_files(args.paths)
    if not md_files:
        raise SystemExit("No markdown files found.")

    output_dir = (ROOT / args.output_dir).resolve()
    for md_file in md_files:
        pdf_path = render_one(md_file, output_dir)
        print(f"Rendered: {pdf_path}")


if __name__ == "__main__":
    main()
