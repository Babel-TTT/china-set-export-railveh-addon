#!/usr/bin/env python3
"""Check the workbench front end's API calls against the server's route table.

The front end never writes a URL directly: it calls `jsonFetch('/save', ...)`
and `jsonFetch` prepends the `API` constant.  So a call site that already
includes the prefix asks for `/api/api/save`, which the server answers with a
plain 404 -- no error message, no stack trace, just a dead button.  That is
exactly what happened to the tier 3 rule editor's write-back, and it was found
only by clicking the button in a browser.

This tool reads both files and reports, without needing a server:

  * a call site whose path already starts with the API prefix (double prefix)
  * a call site for a route `server.py` never dispatches
  * a call site whose method does not match the handler that owns the route
    (posting to a GET-only route 404s just as silently)

It also lists routes no call site uses, as information: some are reached from
other pages or by hand, so that is not an error.

Usage:

    python3 tools/check_workbench_routes.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_JS = ROOT / "web" / "workbench" / "app.js"
SERVER_PY = ROOT / "web" / "workbench" / "server.py"

# jsonFetch(  'literal'   or   jsonFetch(  `template`
CALL_RE = re.compile(r"jsonFetch\(\s*([`'\"])(?P<path>[^`'\"]*)\1")
# the options object, if any, starts right after the comma: jsonFetch('/save', {
METHOD_RE = re.compile(r"^[,]\s*\{\s*method:\s*['\"](\w+)['\"]")
# server.py dispatches with `parsed.path == "/api/x"` (GET) / `self.path == ...`
ROUTE_RE = re.compile(r"(?:parsed|self)\.path == \"(/api/[A-Za-z0-9_./-]*)\"")


def api_prefix() -> str:
    match = re.search(r"const API = '([^']*)'", APP_JS.read_text(encoding="utf-8"))
    if not match:
        raise SystemExit("app.js: no `const API = '...'` found")
    return match.group(1)


def call_sites() -> list[tuple[int, str, str]]:
    """(line number, path as written, HTTP method) for every jsonFetch call."""
    text = APP_JS.read_text(encoding="utf-8")
    sites = []
    for match in CALL_RE.finditer(text):
        path = match.group("path")
        # a template may hold ${...}: keep the literal part before the query
        path = path.split("?")[0].split("${")[0]
        method = "GET"
        following = text[match.end():match.end() + 80]
        found = METHOD_RE.match(following)
        if found:
            method = found.group(1).upper()
        line = text.count("\n", 0, match.start()) + 1
        sites.append((line, path, method))
    return sites


def routes() -> dict[str, set[str]]:
    """route -> set of methods that dispatch it, split by handler function."""
    text = SERVER_PY.read_text(encoding="utf-8")
    boundaries = []
    for name in ("def do_GET", "def do_POST"):
        at = text.find(name)
        if at < 0:
            raise SystemExit("server.py: no %s found" % name)
        boundaries.append((at, "GET" if name.endswith("GET") else "POST"))
    boundaries.sort()

    table: dict[str, set[str]] = {}
    for match in ROUTE_RE.finditer(text):
        at = match.start()
        method = "GET"
        for start, name in boundaries:
            if start <= at:
                method = name
        table.setdefault(match.group(1), set()).add(method)
    return table


def main() -> int:
    prefix = api_prefix()
    prefix_re = re.compile(r"^" + re.escape(prefix) + r"/")
    table = routes()
    problems: list[str] = []
    used: set[str] = set()

    for line, path, method in call_sites():
        shown = "app.js:%d jsonFetch(%r)" % (line, path)
        if prefix_re.match(path):
            problems.append(
                "%s -- jsonFetch already prepends %r, so this asks for %s%s "
                "(404). Write %r instead."
                % (shown, prefix, prefix, path, path[len(prefix):]))
            continue
        if not path.startswith("/"):
            problems.append("%s -- path must start with '/' after the prefix" % shown)
            continue
        route = prefix + path
        used.add(route)
        if route not in table:
            problems.append(
                "%s -- server.py dispatches no route %s. Known routes: %s"
                % (shown, route, ", ".join(sorted(table))))
            continue
        if method not in table[route]:
            problems.append(
                "%s -- %s is %s-only, so this %s call 404s"
                % (shown, route, "/".join(sorted(table[route])), method))

    unused = sorted(set(table) - used)
    print("workbench API routes: %d call site(s), %d route(s) in server.py"
          % (len(call_sites()), len(table)))
    if unused:
        print("note: no call site uses " + ", ".join(unused))

    if problems:
        print("\n%d problem(s):" % len(problems))
        for problem in problems:
            print("  " + problem)
        return 1
    print("OK: every jsonFetch call resolves to a route the server dispatches")
    return 0


if __name__ == "__main__":
    sys.exit(main())
