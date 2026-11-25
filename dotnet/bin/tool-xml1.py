"""Text output of the Linux actool / ibtool ("/* com.apple.actool.compilation-results */" then one file a line, or
"/* com.apple.ibtool.errors */" ...) as the xml1 plist Xcode's prints with --output-format xml1"""
import plistlib
import re
import sys

out, key = {}, None
for line in sys.stdin.read().splitlines():
    m = re.match(r"/\* (com\.apple\.[\w.]+?)\.([\w-]+) \*/$", line.strip())
    if m:
        key = m.group(1) + "." + m.group(2)
        out.setdefault(key, {} if key.endswith("compilation-results") else [])
        continue
    if not line.strip() or key is None:
        continue
    if key.endswith("compilation-results"):
        out[key].setdefault("output-files", []).append(line.strip())
    else:
        out[key].append({"description": line.strip()})
sys.stdout.buffer.write(plistlib.dumps(out, fmt=plistlib.FMT_XML))
