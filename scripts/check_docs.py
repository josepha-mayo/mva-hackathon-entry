"""Lint the markdown corpus: dead links and dead command references.

Checks every ``*.md`` file in the repository (working tree, not history):

* Markdown links ``[text](relative/path)`` resolve to a committed-or-present
  file relative to the document's directory. External URLs and in-page
  anchors are skipped.
* Inline-code or fenced commands of the form ``python scripts/<name>.py``
  resolve to an existing file under ``scripts/``. Lines inside fenced code
  blocks are included; lines that name a placeholder like ``<new-path>`` are
  not commands and do not match.

Usage: python scripts/check_docs.py <repo-root>
Exit 0 when every reference resolves; nonzero with a per-file report.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path, PurePosixPath

MD_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
CMD_REF = re.compile(r"python(?:\.exe)?\s+(scripts/[A-Za-z0-9_\-]+\.py)")
MODULE_REF = re.compile(r"python\s+-m\s+unittest\s+((?:tests\.[A-Za-z0-9_]+)(?:\s+tests\.[A-Za-z0-9_]+)*)")
SKIP_PREFIXES = ("http://", "https://", "mailto:", "#")


def _markdown_files(root: Path) -> list[Path]:
    return sorted(
        p
        for p in root.rglob("*.md")
        if ".git" not in p.parts and p.is_file()
    )


def _resolve_link(doc: Path, link: str) -> Path:
    target = link.split("#", 1)[0].split("?", 1)[0]
    return (doc.parent / target).resolve()


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    problems: list[str] = []
    links = 0
    commands = 0
    docs = 0

    for doc in _markdown_files(root):
        docs += 1
        try:
            text = doc.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            problems.append(f"{doc.relative_to(root)}: unreadable ({exc})")
            continue
        rel_doc = PurePosixPath(doc.relative_to(root).as_posix())
        for lineno, line in enumerate(text.splitlines(), start=1):
            for match in MD_LINK.finditer(line):
                link = match.group(1)
                if link.startswith(SKIP_PREFIXES) or link.startswith("data:"):
                    continue
                links += 1
                target = _resolve_link(doc, link)
                if not target.exists():
                    problems.append(
                        f"{rel_doc}:{lineno}: dead link -> {link}"
                    )
            for match in CMD_REF.finditer(line):
                commands += 1
                script = root / match.group(1)
                if not script.is_file():
                    problems.append(
                        f"{rel_doc}:{lineno}: missing script -> {match.group(1)}"
                    )
            for match in MODULE_REF.finditer(line):
                commands += 1
                for mod in match.group(1).split():
                    name = mod.split(".")[-1]
                    if not (root / "tests" / f"{name}.py").is_file():
                        problems.append(
                            f"{rel_doc}:{lineno}: missing test module -> {mod}"
                        )

    print(f"checked {links} link(s) and {commands} command reference(s) across {docs} markdown file(s)")
    if problems:
        for problem in problems:
            print(f"  FAIL {problem}")
        print(f"result: {len(problems)} broken reference(s)")
        return 1
    print("result: all documentation references resolve")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
