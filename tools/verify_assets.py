#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tools/verify_assets.py -- check the generated PNML against the files on disk

For every sprite template call in the generated code it checks that the
_32bpp.png sheet the renderer will produce actually exists, and it prints the
palette indices of a few placeholder models so that liveries and cargo
appearances can be told apart.

Run it after `make gen && make` -- a missing sheet is what makes nmlc stop with
"Path ... does not exist".
"""

from __future__ import annotations

import os
import re
import struct
import sys

GENERATED_DIRS = ("25-electric", "25-emu", "coaches", "diesel", "dmu", "steam",
                  "unit-wagons", "wagons")

TEMPLATE_CALL = re.compile(r'template_\w+ \("([^"]+)", "([^"]+)"\)')


def generated_files():
    for root, _dirs, files in os.walk("src"):
        for name in sorted(files):
            if name.endswith(".pnml"):
                yield os.path.join(root, name)


def main() -> int:
    refs = set()
    for path in generated_files():
        with open(path, encoding="utf-8") as handle:
            refs.update(TEMPLATE_CALL.findall(handle.read()))

    if not refs:
        print("no generated code found -- run `make gen` first")
        return 1

    missing = []
    for folder, base in sorted(refs):
        path = "gfx/%s/%s_32bpp.png" % (folder, base)
        if not os.path.exists(path):
            missing.append(path)

    print("sprite sheets referenced: %d" % len(refs))
    if missing:
        print("MISSING %d sprite sheets:" % len(missing))
        for path in missing:
            print("  %s" % path)
        print("fix: make gen && make sprites")
        return 1
    print("missing _32bpp.png: none")

    # every switch target should be defined somewhere in the generated code
    defined, targets = set(), set()
    for path in generated_files():
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        defined.update(re.findall(r'^(?:spriteset|switch|random_switch) \(([^,)\s]+)',
                                 text, re.M))
        defined.update(re.findall(r'^(?:spriteset|switch|random_switch) '
                                  r'\(FEAT_TRAINS, \w+, ([^,)\s]+)', text, re.M))
        targets.update(re.findall(r'^\s+\S+:\s*([A-Za-z_][A-Za-z_0-9]*);', text, re.M))
        targets.update(re.findall(r'^\s+return ([A-Za-z_][A-Za-z_0-9]*);', text, re.M))
    print("named blocks defined: %d, referenced as targets: %d"
          % (len(defined), len(targets)))

    samples = ("df4bex", "df4bex-dprk", "df4bex-ukraine",
               "c70ex", "c70ex-coal", "c70ex-cover", "ckd8f", "ckd8f-exblue")
    for name in samples:
        for folder in GENERATED_DIRS:
            path = "gfx/%s/%s.vox" % (folder, name)
            if os.path.exists(path):
                print("%-18s palette indices %s" % (name, vox_colours(path)))
                break
    return 0


def vox_colours(path):
    """Palette indices used by a .vox file, parsed from its XYZI chunk."""
    raw = open(path, "rb").read()
    offset = 8
    while offset < len(raw) - 12:
        chunk_id = raw[offset:offset + 4]
        size, children = struct.unpack('<ii', raw[offset + 4:offset + 12])
        if chunk_id == b'XYZI':
            count = struct.unpack('<i', raw[offset + 12:offset + 16])[0]
            start = offset + 16
            return sorted({raw[start + 4 * k + 3] for k in range(count)})
        offset += 12 + size + children
    return []


if __name__ == "__main__":
    sys.exit(main())
