"""Child entry point: page 1 of a PDF as PNG, plus meta.json beside it.

Runs as python -I -m pii_redaction_backend.workers.render <src> <out_png> <dpi>
inside run_child (empty environment, own process group, time limit). It logs
nothing and prints nothing: exit 0 means the PNG and meta.json exist, exit 2
means the file could not be rendered (the parent maps that to render_failed).
meta.json carries numbers only: pages, width, height.
"""

import json
import sys
from pathlib import Path

MIN_DPI = 36
MAX_DPI = 300


def main(argv: list[str]) -> int:
    if len(argv) != 3 or not argv[2].isdigit() or not MIN_DPI <= int(argv[2]) <= MAX_DPI:
        return 2
    source, out = Path(argv[0]), Path(argv[1])
    meta = out.with_name("meta.json")
    try:
        import pymupdf

        with pymupdf.open(source) as document:
            if document.page_count < 1:
                return 2
            pixmap = document[0].get_pixmap(dpi=int(argv[2]))
            pixmap.save(out)
            info = {"pages": document.page_count, "width": pixmap.width, "height": pixmap.height}
        meta.write_text(json.dumps(info), encoding="utf-8")
    except Exception:
        out.unlink(missing_ok=True)
        meta.unlink(missing_ok=True)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
