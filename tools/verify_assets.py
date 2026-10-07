#!/usr/bin/env python3
"""Verification helper: check the generated PNML against the files on disk."""
import os
import re
import struct

pnml = open('src/usercode.pnml', encoding='utf-8').read()

refs = set(re.findall(r'template_\w+ \("([^"]+)", "([^"]+)"\)', pnml))
missing = []
for folder, base in sorted(refs):
    path = 'gfx/%s/%s_32bpp.png' % (folder, base)
    if not os.path.exists(path):
        missing.append(path)
print('sprite sheets referenced: %d' % len(refs))
print('missing _32bpp.png: %s' % (missing or 'none'))

# every switch target must be defined somewhere
defined = set(re.findall(r'^(?:spriteset|switch|random_switch) \(([^,)\s]+)', pnml, re.M))
defined |= set(re.findall(r'^(?:spriteset|switch|random_switch) \(FEAT_TRAINS, \w+, ([^,)\s]+)', pnml, re.M))
targets = set(re.findall(r'^\s+\S+:\s*([A-Za-z_][A-Za-z_0-9]*);', pnml, re.M))
targets |= set(re.findall(r'^\s+return ([A-Za-z_][A-Za-z_0-9]*);', pnml, re.M))
targets |= set(re.findall(r'^\s+([A-Za-z_][A-Za-z_0-9]*);$', pnml, re.M))
print('named blocks defined: %d, referenced as targets: %d' % (len(defined), len(targets)))


def vox_colour(path):
    """Palette indices used by a .vox file, parsed from its XYZI chunk."""
    raw = open(path, 'rb').read()
    offset = 8
    while offset < len(raw):
        chunk_id = raw[offset:offset + 4]
        size, children = struct.unpack('<ii', raw[offset + 4:offset + 12])
        if chunk_id == b'XYZI':
            count = struct.unpack('<i', raw[offset + 12:offset + 16])[0]
            start = offset + 16
            return sorted({raw[start + 4 * k + 3] for k in range(count)})
        offset += 12 + size + children
    return []


for name in ('df4bex', 'df4bex-dprk', 'df4bex-ukraine',
             'c70ex', 'c70ex-coal', 'c70ex-cover', 'ckd8f', 'ckd8f-exblue'):
    for folder in ('diesel', 'wagons'):
        path = 'gfx/%s/%s.vox' % (folder, name)
        if os.path.exists(path):
            print('%-18s palette indices %s' % (name, vox_colour(path)))
            break
