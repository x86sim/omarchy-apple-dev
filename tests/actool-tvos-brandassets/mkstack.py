"""Write small tvOS asset catalogs with image stacks for probing Apple's actool.

usage: mkstack.py OUTDIR
Catalogs: two.xcassets (2 layers, front 200x120 on a 400x240 back),
five.xcassets (5 layers, 400x240 each). Single 1x images, solid colors.
"""
import json
import os
import struct
import sys
import zlib


def png(path, w, h, rgba):
    raw = b"".join(b"\0" + bytes(rgba) * w for _ in range(h))
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    data = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)) \
        + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")
    open(path, "wb").write(data)


def write_json(path, obj):
    with open(path, "w") as f:
        json.dump(obj, f, indent=2)


INFO = {"author": "xcode", "version": 1}


def catalog(root, layers):
    """layers: front-to-back list of (name, w, h, rgba)."""
    cat = os.path.join(root, "Assets.xcassets")
    brand = os.path.join(cat, "Icon.brandassets")
    stack = os.path.join(brand, "App Icon.imagestack")
    os.makedirs(stack, exist_ok=True)
    write_json(os.path.join(cat, "Contents.json"), {"info": INFO})
    write_json(os.path.join(brand, "Contents.json"), {"assets": [
        {"filename": "App Icon.imagestack", "idiom": "tv", "role": "primary-app-icon", "size": "400x240"}],
        "info": INFO})
    write_json(os.path.join(stack, "Contents.json"),
               {"info": INFO, "layers": [{"filename": f"{n}.imagestacklayer"} for n, *_ in layers]})
    for name, w, h, rgba in layers:
        layer = os.path.join(stack, f"{name}.imagestacklayer")
        iset = os.path.join(layer, "Content.imageset")
        os.makedirs(iset, exist_ok=True)
        write_json(os.path.join(layer, "Contents.json"), {"info": INFO})
        png(os.path.join(iset, "a.png"), w, h, rgba)
        write_json(os.path.join(iset, "Contents.json"),
                   {"images": [{"filename": "a.png", "idiom": "tv", "scale": "1x"}], "info": INFO})


out = sys.argv[1]
catalog(os.path.join(out, "two"), [("Front", 200, 120, (255, 0, 0, 128)), ("Back", 400, 240, (0, 0, 255, 255))])
catalog(os.path.join(out, "five"), [(f"L{i}", 400, 240, (40 * i, 0, 0, 255 if i == 4 else 100)) for i in range(5)])
