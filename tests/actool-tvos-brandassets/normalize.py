"""Canonical text of an Assets.car for comparing ours with Apple's actool output.

usage: normalize.py Assets.car
One block per rendition, sorted: the facet name and key attributes (identifier left out),
the CSI header fields, and the TVL blocks in hex with identifiers in TVL 1012 (layer
references) replaced by the facet name they point at. Pixel bodies and rendition
identifier values are left out: they depend on the image encoder and the name hash.
"""
import os
import re
import subprocess
import sys

DUMP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cardump.py")
TVLS = ["1001", "1003", "1004", "1005", "1006", "1007", "1012", "1020", "1021", "1022"]


def main():
    out = subprocess.run([sys.executable, "-I", DUMP, sys.argv[1], "--hex", *TVLS],
                         capture_output=True, text=True, check=True).stdout
    facets = {int(m.group(2)): m.group(1)
              for m in re.finditer(r"FACET '(.*)': \{.*identifier=(\d+)\}", out)}
    renditions, current = {}, None
    for line in out.splitlines():
        if line.startswith("REND"):
            m = re.match(r"REND '(.*)' (\{.*\})", line)
            attrs = re.sub(r"'identifier': \d+(, )?", "", m.group(2)).replace(", }", "}")
            current = f"{m.group(1)} {attrs}"
            renditions[current] = []
        elif current and line.strip().startswith("csi"):
            renditions[current].append(re.sub(r" body=\d+ total=\d+", "", line.strip()))
        elif current and line.strip().startswith("tvl"):
            _, kind, _size, data = line.split(maxsplit=3)
            if kind == "1012":
                # u32 count, u32 0, then one 48-byte layer record each (x, y, w, h, blend,
                # f32 opacity, u32 16, then the key: (1 look)(2 element)(17 identifier)(0 0)
                # and 4 more bytes). The identifier is at record offset 42.
                raw = bytearray(bytes.fromhex(data))
                count = int.from_bytes(raw[:4], "little")
                names = []
                for n in range(count):
                    at = 8 + 48 * n + 42
                    names.append(facets.get(int.from_bytes(raw[at:at + 2], "little"), "?"))
                    raw[at:at + 2] = b"\0\0"
                data = raw.hex() + " layers=" + ",".join(names)
            renditions[current].append(f"tvl {kind} {data}")
    for key in sorted(renditions):
        print(key)
        for line in renditions[key]:
            print("  " + line)


if __name__ == "__main__":
    main()
