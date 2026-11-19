"""Decode DYLD_CHAINED_PTR_32 fixup chains the way dyld walks them.

usage: chain32.py BINARY [--raw]
Prints one line per chain entry: segment, segment offset, kind and target.
Kinds: rebase (target vmaddr), bind (import name + addend), nonptr (filler entry
that dyld turns back into a plain value). Exits 1 on a malformed chain.
"""
import struct
import sys

FAT_MAGIC = 0xCAFEBABE
MH_MAGIC = 0xFEEDFACE
CPU_ARM64_32 = 0x0200000C
LC_SEGMENT = 0x1
LC_DYLD_CHAINED_FIXUPS = 0x80000034
START_NONE = 0xFFFF
START_MULTI = 0x8000
START_LAST = 0x8000


def thin_slice(data):
    if struct.unpack_from(">I", data, 0)[0] != FAT_MAGIC:
        return data
    (n,) = struct.unpack_from(">I", data, 4)
    for i in range(n):
        cpu, _, off, size, _ = struct.unpack_from(">5I", data, 8 + 20 * i)
        if cpu == CPU_ARM64_32:
            return data[off:off + size]
    sys.exit("no arm64_32 slice")


def main():
    data = thin_slice(open(sys.argv[1], "rb").read())
    magic, cpu, _, _, ncmds, _, _ = struct.unpack_from("<7I", data, 0)
    assert magic == MH_MAGIC and cpu == CPU_ARM64_32, hex(magic)
    off = 28
    segs, fixups = [], None
    for _ in range(ncmds):
        cmd, size = struct.unpack_from("<2I", data, off)
        if cmd == LC_SEGMENT:
            name = data[off + 8:off + 24].rstrip(b"\0").decode()
            vmaddr, vmsize, fileoff, filesize = struct.unpack_from("<4I", data, off + 24)
            segs.append((name, vmaddr, vmsize, fileoff, filesize))
        elif cmd == LC_DYLD_CHAINED_FIXUPS:
            fixups = struct.unpack_from("<2I", data, off + 8)
        off += size
    if fixups is None:
        print("no LC_DYLD_CHAINED_FIXUPS")
        return 0
    base = fixups[0]
    (version, starts_off, imports_off, symbols_off, imports_count, imports_fmt,
     _) = struct.unpack_from("<7I", data, base)
    names = []
    for i in range(imports_count):
        if imports_fmt == 1:    # dyld_chained_import
            (raw,) = struct.unpack_from("<I", data, base + imports_off + 4 * i)
            name_off, extra = raw >> 9, 0
        elif imports_fmt == 2:  # dyld_chained_import_addend
            raw, extra = struct.unpack_from("<Ii", data, base + imports_off + 8 * i)
            name_off = raw >> 9
        elif imports_fmt == 3:  # dyld_chained_import_addend64
            raw, extra = struct.unpack_from("<Qq", data, base + imports_off + 16 * i)
            name_off = raw >> 32
        else:
            sys.exit(f"imports_format {imports_fmt}")
        s = base + symbols_off + name_off
        name = data[s:data.index(b"\0", s)].decode()
        names.append(name + (f"{extra:+d}" if extra else ""))
    (seg_count,) = struct.unpack_from("<I", data, base + starts_off)
    bad = 0
    for si in range(seg_count):
        (info_off,) = struct.unpack_from("<I", data, base + starts_off + 4 + 4 * si)
        if not info_off:
            continue
        p = base + starts_off + info_off
        size, page_size, fmt, seg_offset, max_valid, page_count = struct.unpack_from("<IHHQIH", data, p)
        assert fmt == 3, f"pointer_format {fmt}"
        starts = struct.unpack_from(f"<{(size - 22) // 2}H", data, p + 22)
        name, vmaddr, _, fileoff, _ = segs[si]
        bias = (0x04000000 + max_valid) // 2
        print(f"# imports_format={imports_fmt}")
        print(f"# {name} max_valid_pointer={max_valid:#x} page_count={page_count} starts={list(starts[:page_count])}")
        for page in range(page_count):
            s = starts[page]
            if s == START_NONE:
                continue
            chain_starts = []
            if s & START_MULTI:
                idx = s & ~START_MULTI
                while True:
                    v = starts[idx]
                    chain_starts.append(v & ~START_LAST)
                    if v & START_LAST:
                        break
                    idx += 1
            else:
                chain_starts.append(s)
            for cs in chain_starts:
                loc = page * page_size + cs
                while True:
                    (raw,) = struct.unpack_from("<I", data, fileoff + loc)
                    is_bind = raw >> 31
                    nxt = (raw >> 26) & 0x1F
                    if is_bind:
                        ordinal, addend = raw & 0xFFFFF, (raw >> 20) & 0x3F
                        if ordinal >= len(names):
                            print(f"BAD ordinal {ordinal} at {name}+{loc:#x}")
                            bad += 1
                        else:
                            print(f"{name}+{loc:#x} bind {names[ordinal]} +{addend}")
                    else:
                        target = raw & 0x3FFFFFF
                        if target > max_valid:
                            print(f"{name}+{loc:#x} nonptr {target - bias:#x}")
                        else:
                            print(f"{name}+{loc:#x} rebase {target:#x}")
                    if nxt == 0:
                        break
                    loc += nxt * 4
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
