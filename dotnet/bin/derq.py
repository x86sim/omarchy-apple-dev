"""derq for Linux: `derq query -f xml -i ENTITLEMENTS.plist -o OUT.der --raw`, the DER form of an entitlements plist
that Apple's derq writes (a simulator app embeds it in its executable's __ents_der section):
  [APPLICATION 16] { INTEGER 1, <dict> }
  dict   [CONTEXT 16] { SEQUENCE { UTF8String key, value } ... }, keys in order
  array  SEQUENCE { value ... }
  string UTF8String, bool BOOLEAN, integer INTEGER
(byte-identical to Apple's derq for application-identifier + keychain-access-groups, Xcode 27.2)"""
import plistlib
import sys


def tlv(tag, body):
    n = len(body)
    if n < 0x80:
        size = bytes([n])
    else:
        b = n.to_bytes((n.bit_length() + 7) // 8, "big")
        size = bytes([0x80 | len(b)]) + b
    return bytes([tag]) + size + body


def ctx16(body):
    return tlv(0xB0, body)


def enc(v):
    if isinstance(v, bool):
        return tlv(0x01, b"\xff" if v else b"\x00")
    if isinstance(v, int):
        return tlv(0x02, v.to_bytes(max(1, (v.bit_length() + 8) // 8), "big", signed=True))
    if isinstance(v, str):
        return tlv(0x0C, v.encode("utf-8"))
    if isinstance(v, (list, tuple)):
        return tlv(0x30, b"".join(enc(x) for x in v))
    if isinstance(v, dict):
        return ctx16(b"".join(tlv(0x30, enc(k) + enc(v[k])) for k in sorted(v)))
    raise SystemExit(f"derq (linux): unsupported entitlement value {v!r}")


def main(argv):
    args = argv[1:]
    if not args or args[0] != "query":
        raise SystemExit("derq (linux): only `derq query -f xml -i IN -o OUT --raw`")
    i = args.index("-i") + 1 if "-i" in args else None
    o = args.index("-o") + 1 if "-o" in args else None
    if i is None or o is None:
        raise SystemExit("derq (linux): -i and -o are needed")
    with open(args[i], "rb") as f:
        ents = plistlib.load(f)
    der = tlv(0x70, tlv(0x02, b"\x01") + enc(ents))
    with open(args[o], "wb") as f:
        f.write(der)


if __name__ == "__main__":
    main(sys.argv)
