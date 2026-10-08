"""Check the Markdown documents: tables line up, and the text is really UTF-8.

Two failures this catches, both of which are easy to make and hard to see:

* an unescaped `|` inside a table cell splits it into two, so GitHub renders extra
  columns and the row silently stops lining up.  The escape is `\\|`, and the
  backslash count matters: `\\\\|` is an escaped backslash followed by a real
  delimiter, which still splits the cell.
* a document that was read as the ANSI code page and written back as UTF-8 turns
  every Chinese character into its GBK reading.  That happened here once, from a
  throwaway PowerShell snippet (`Get-Content` decodes UTF-8 without a BOM as GBK,
  `WriteAllText` writes UTF-8), and nothing in the build noticed.  The result is
  full of private-use characters and cannot be reversed losslessly, so it is worth
  refusing loudly.

    python3 tools/check_markdown_tables.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEPARATOR = re.compile(r"^\|[\s:|-]+\|$")
# CP936 turns byte pairs it cannot map into the private use area, and a document
# that came back through the wrong codec is full of them
PRIVATE_USE = (0xE000, 0xF8FF)
REPLACEMENT = "\ufffd"


def columns(line: str) -> int:
    """Cells in a table row: the pipes that are not escaped.

    A pipe is escaped by an **odd** number of backslashes in front of it.
    """
    cells = 0
    for index, char in enumerate(line):
        if char != "|":
            continue
        backslashes = 0
        position = index - 1
        while position >= 0 and line[position] == "\\":
            backslashes += 1
            position -= 1
        if backslashes % 2 == 0:
            cells += 1
    return cells - 1


def encoding_problems(path: Path, text: str) -> list[str]:
    """Signs that the file went through the wrong codec on the way in or out."""
    if REPLACEMENT in text:
        return ["%s contains U+FFFD, so characters were lost while decoding it"
                % path.relative_to(ROOT)]
    private = sum(1 for char in text if PRIVATE_USE[0] <= ord(char) <= PRIVATE_USE[1])
    if private:
        return ["%s has %d private-use character(s) (U+E000..U+F8FF), which is "
                "what a UTF-8 file read as GBK and written back looks like"
                % (path.relative_to(ROOT), private)]
    return []


def table_problems(path: Path, text: str) -> list[str]:
    problems = []
    header = None
    in_fence = False
    for number, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            header = None
            continue
        if in_fence:
            continue
        stripped = line.strip()
        if not stripped.startswith("|"):
            header = None
            continue
        if header is None:
            header = (columns(stripped), number)
            continue
        if SEPARATOR.match(stripped):
            continue
        if columns(stripped) != header[0]:
            problems.append("%s:%d has %d column(s), the header on line %d has %d: %s"
                            % (path.relative_to(ROOT), number, columns(stripped),
                               header[1], header[0], stripped[:90]))
    return problems


def main() -> int:
    problems = []
    documents = 0
    for path in sorted(ROOT.rglob("*.md")):
        if any(part in (".git", "node_modules") for part in path.parts):
            continue
        documents += 1
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as error:
            problems.append("%s is not valid UTF-8: %s" % (path.relative_to(ROOT), error))
            continue
        problems.extend(encoding_problems(path, text))
        problems.extend(table_problems(path, text))

    for problem in problems:
        print(problem)
    print("%d document(s) checked, %d problem(s)" % (documents, len(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
