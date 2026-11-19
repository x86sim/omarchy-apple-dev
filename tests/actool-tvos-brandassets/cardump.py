"""Dump an Assets.car's renditions: key attributes, CSI header and TVL blocks.

usage: cardump.py Assets.car [--hex KIND ...]
Uses the BOM reader of tools/car_check.py. For comparing AssetKit output with Apple's actool.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "tools"))
import car_check  # noqa: E402

ATTR = {1: "look", 2: "element", 3: "part", 4: "size", 5: "direction", 6: "placeholder", 7: "value",
        8: "appearance", 9: "dimension1", 10: "dimension2", 11: "state", 12: "scale", 13: "localization",
        14: "presentationState", 15: "idiom", 16: "subtype", 17: "identifier", 18: "previousValue",
        19: "previousState", 20: "sizeClassHorizontal", 21: "sizeClassVertical", 22: "memoryClass",
        23: "graphicsClass", 24: "displayGamut", 25: "deploymentTarget", 26: "glyphWeight", 27: "glyphSize"}


def main():
    data = open(sys.argv[1], "rb").read()
    hex_kinds = {int(k) for k in sys.argv[3:]} if "--hex" in sys.argv else set()
    bom = car_check._Bom(data)
    fmt = car_check._key_format(bom)
    print("KEYFORMAT", [ATTR.get(a, a) for a in fmt])
    names = {}
    if "FACETKEYS" in bom.vars:
        for key_block, value in bom.leaves("FACETKEYS"):
            name = bom.block(key_block).decode("utf-8", "replace")
            raw = bom.block(value)
            n = struct.unpack_from("<H", raw, 4)[0]
            attrs = dict(struct.unpack_from("<HH", raw, 6 + 4 * i) for i in range(n))
            names[attrs.get(17)] = name
            print(f"FACET {name!r}: {{{', '.join(f'{ATTR.get(k, k)}={v}' for k, v in attrs.items())}}}")
    for key_block, value in bom.leaves("RENDITIONS"):
        key = bom.block(key_block)
        tokens = struct.unpack(f"<{len(key) // 2}H", key)
        attrs = {ATTR.get(a, a): t for a, t in zip(fmt, tokens) if t}
        csi = bom.block(value)
        (magic, version, flags, width, height, scale, pixfmt, colorspace_layout) = struct.unpack_from("<4s7I", csi, 0)
        layout = struct.unpack_from("<H", csi, 36)[0]
        name = csi[40:168].split(b"\0")[0].decode("utf-8", "replace")
        tvl_len = struct.unpack_from("<I", csi, 168)[0]
        body_len = struct.unpack_from("<I", csi, 180)[0] if len(csi) >= 184 else 0
        print(f"\nREND {names.get(attrs.get('identifier'), '?')!r} {attrs}")
        print(f"  csi name={name!r} layout={layout} flags={flags:#x} {width}x{height} scale={scale} "
              f"pixfmt={pixfmt.to_bytes(4, 'big') if pixfmt else 0} tvl={tvl_len} body={body_len} total={len(csi)}")
        pos, end = 184, 184 + tvl_len
        while pos + 8 <= end:
            kind, size = struct.unpack_from("<2I", csi, pos)
            payload = csi[pos + 8:pos + 8 + size]
            shown = payload.hex() if (kind in hex_kinds or size <= 32) else f"{payload[:48].hex()}... ({size} bytes)"
            print(f"  tvl {kind} [{size}] {shown}")
            pos += 8 + size
        body = csi[end:]
        print(f"  body[{len(body)}] {body[:64].hex()}{'...' if len(body) > 64 else ''}")


if __name__ == "__main__":
    main()
