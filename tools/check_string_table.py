"""Regression check for the string table: header handling and row stability.

Both bugs this guards against produced a list that looked fine until the user
touched it: the header line leaking into the published rows as a phantom
"STRING" entry, and a save silently changing the number of rows.  The HTTP part
starts its own server on a free port, so the check can run on its own:

    python3 tools/check_string_table.py
"""
import csv
import io
import json
import shutil
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web" / "workbench"))
import genpnml  # noqa: E402
import server  # noqa: E402

failures = []


def check(label, condition, detail=""):
    print(("  ok  " if condition else " FAIL ") + label + (" :: " + detail if detail else ""))
    if not condition:
        failures.append(label)


def start_server():
    """A private workbench on a free port, so nothing else has to be running."""
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.WorkbenchHandler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, "http://127.0.0.1:%d" % httpd.server_address[1]


def call(base, path, payload=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(base + path, data=data,
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read().decode("utf-8") or "{}")


# ---- 1. the reader never publishes the header or a non constant
rows = server.string_table_rows()
check("no phantom row is published", all(r["constant"].startswith("STR_") for r in rows),
      str([r["constant"] for r in rows if not r["constant"].startswith("STR_")]))
check("header is not a row", not any(r["constant"] == "STRING" for r in rows))
check("both readers agree", len(rows) == len(server.read_lang_table()[1]),
      "%d published vs %d read" % (len(rows), len(server.read_lang_table()[1])))

# ---- 2. the generator agrees too
table = genpnml.load_string_table(str(server.LANG_CSV))
check("generator does not see the header", "STRING" not in table)
check("generator sees every published row",
      set(table) == {r["constant"] for r in rows},
      str(set(table) ^ {r["constant"] for r in rows})[:200])

# ---- 3. a save and a delete keep the row count honest, over HTTP
httpd, base = start_server()
backup = server.LANG_CSV.read_bytes()
try:
    status, before = call(base, "/api/strings")
    count_before = len(before["strings"])
    status, saved = call(base, "/api/string", {"constant": "STR_LV_ORIGINAL",
                                               "original": "STR_LV_ORIGINAL",
                                               "english": "Original", "chinese": "原始涂装"})
    check("save succeeds", saved.get("ok") and status == 200, str(saved)[:120])
    status, after = call(base, "/api/strings")
    check("save does not add a row", len(after["strings"]) == count_before,
          "%d -> %d" % (count_before, len(after["strings"])))
    check("save did not create STRING",
          not any(r["constant"] == "STRING" for r in after["strings"]))

    target = next(r["constant"] for r in after["strings"] if r["constant"] == "STR_LV_ORIGINAL")
    status, deleted = call(base, "/api/string-delete", {"constant": target})
    check("delete succeeds", deleted.get("ok"), str(deleted)[:120])
    status, final = call(base, "/api/strings")
    check("delete removes exactly one row", len(final["strings"]) == count_before - 1,
          "%d -> %d" % (count_before, len(final["strings"])))
finally:
    server.LANG_CSV.write_bytes(backup)
    httpd.shutdown()
    httpd.server_close()

rows_again = server.string_table_rows()
check("restored to the original count", len(rows_again) == len(rows),
      "%d vs %d" % (len(rows_again), len(rows)))

# ---- 4. a livery label is what identifies a scheme, so reuse has to be visible
# Fixed rows, not the live table: this has to hold whatever the project currently
# contains, including a project with a single livery.
sibling = {"id": "probeveh", "sprite_suffix": "probe-b", "string": "LV_PROBE",
           "from_year": "0", "to_year": "9999", "graphics_parts": ""}
row = {"id": "probeveh", "sprite_suffix": "probe-a", "string": "LV_PROBE",
       "from_year": "0", "to_year": "9999", "graphics_parts": ""}

shared = server.validate_livery_row(row, {"probeveh"}, True, [sibling], None,
                                    {"probeveh": 3})
check("a label shared by two schemes of one vehicle warns",
      any("同一个字符串" in warning for warning in shared["warnings"]),
      str(shared["warnings"]))
check("...and does not block the save", not shared["errors"], str(shared["errors"]))

across = server.validate_livery_row(row, {"probeveh"}, True,
                                    [dict(sibling, id="otherveh")], None,
                                    {"probeveh": 3})
check("a label shared across vehicles does not warn",
      not any("同一个字符串" in warning for warning in across["warnings"]),
      str(across["warnings"]))

# two schemes of one vehicle may not resolve to the same sprite sheet, and that
# one is an error because the generator would declare the spriteset twice
same_sprite = server.validate_livery_row(row, {"probeveh"}, True,
                                         [dict(sibling, sprite_suffix="probe-a")],
                                         None, {"probeveh": 3})
check("a shared sprite basename is an error", bool(same_sprite["errors"]),
      str(same_sprite["errors"]))

# a malformed rule set names the scheme it came from
bad_rules = server.validate_livery_row(dict(row, graphics_parts="a;b"),
                                       {"probeveh"}, True, [], None, {"probeveh": 3})
check("a wrong section count is an error", bool(bad_rules["errors"]),
      str(bad_rules["errors"]))

# ---- 5. a row the browser holds can be saved back, decorations and all
#
# build_state decorates every row with `_`-prefixed display fields (_index,
# _basename, _graphics, _label_used, ...), and the browser posts that same object
# back.  Treating them as columns made every save fail with 「未知的列」, which in
# turn made the model and the name look unchangeable -- the whole row was
# rejected, not just those fields.  A real row of the project is used so the test
# covers whatever the tables currently contain.
httpd, base = start_server()
livery_backup = server.DATA.joinpath("liveries.csv").read_bytes()
try:
    status, state = call(base, "/api/state")
    live = next((r for r in state.get("liveries", []) if r.get("_graphics") is not None),
                None)
    if live is None:
        check("a decorated livery row can be saved back", False,
              "no livery row in the tables to test with")
    else:
        status, out = call(base, "/api/save", {
            "table": "liveries.csv", "row": live, "original": live,
            "index": live["_index"], "create": False})
        check("a decorated livery row can be saved back", status == 200 and out.get("ok"),
              str(out.get("error"))[:160])

        # the two fields that looked unchangeable: the model and the name
        suffix = (live.get("sprite_suffix") or "").strip()
        changed = dict(live, sprite_suffix=(suffix + "-probe") if suffix else "probe")
        status, out = call(base, "/api/save", {
            "table": "liveries.csv", "row": changed, "original": live,
            "index": live["_index"], "create": False})
        check("the model of a scheme can be changed", status == 200 and out.get("ok"),
              str(out.get("error"))[:160])
        if status == 200:
            now = out["state"]["liveries"][live["_index"]]
            check("...and the new basename is what the row reports",
                  now["_basename"].endswith("probe"), now["_basename"])
            status, out = call(base, "/api/save", {
                "table": "liveries.csv", "row": dict(now, sprite_suffix=suffix),
                "original": now, "index": now["_index"], "create": False})
            check("...and it can be put back", status == 200 and out.get("ok"),
                  str(out.get("error"))[:160])
finally:
    server.DATA.joinpath("liveries.csv").write_bytes(livery_backup)
    httpd.shutdown()
    httpd.server_close()

print()
print("FAILURES:", failures if failures else "none")
sys.exit(1 if failures else 0)
