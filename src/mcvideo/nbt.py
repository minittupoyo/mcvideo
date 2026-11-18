"""Just enough NBT to write Minecraft structure files (``data/<ns>/structure/*.nbt``).

Only the tags a structure needs are supported: compound, list, string and int. Files are big-endian and gzipped;
the gzip header carries no timestamp, so the same input always gives the same bytes.
"""
import gzip
import struct

INT, STRING, LIST, COMPOUND = 3, 8, 9, 10


class Int(int):
    """Marks a Python int as an NBT ``int`` (the only integer type needed here)."""


def _string(s):
    raw = s.encode("utf-8")
    return struct.pack(">H", len(raw)) + raw


def _tag_type(v):
    if isinstance(v, Int):
        return INT
    if isinstance(v, str):
        return STRING
    if isinstance(v, list):
        return LIST
    if isinstance(v, dict):
        return COMPOUND
    raise TypeError(f"unsupported NBT value: {v!r}")


def _payload(v):
    if isinstance(v, Int):
        return struct.pack(">i", v)
    if isinstance(v, str):
        return _string(v)
    if isinstance(v, list):
        if not v:  # an empty list has the type "end"
            return struct.pack(">bi", 0, 0)
        t = _tag_type(v[0])
        return struct.pack(">bi", t, len(v)) + b"".join(_payload(x) for x in v)
    out = bytearray()
    for k, x in v.items():
        out += struct.pack(">b", _tag_type(x)) + _string(k) + _payload(x)
    out += b"\x00"  # TAG_End
    return bytes(out)


def dumps(root):
    """Serialise ``root`` (a dict) as a gzipped NBT file with an unnamed root compound."""
    raw = struct.pack(">b", COMPOUND) + _string("") + _payload(root)
    return gzip.compress(raw, mtime=0)


def loads(data):
    """Parse a file written by ``dumps`` (used by the tests to check the output)."""
    raw, pos = gzip.decompress(data), 0

    def take(fmt):
        nonlocal pos
        size = struct.calcsize(fmt)
        (v,) = struct.unpack_from(fmt, raw, pos)
        pos += size
        return v

    def string():
        nonlocal pos
        n = take(">H")
        s = raw[pos:pos + n].decode("utf-8")
        pos += n
        return s

    def payload(t):
        if t == INT:
            return Int(take(">i"))
        if t == STRING:
            return string()
        if t == LIST:
            et, n = take(">b"), take(">i")
            return [payload(et) for _ in range(n)]
        if t == COMPOUND:
            d = {}
            while True:
                et = take(">b")
                if et == 0:
                    return d
                k = string()
                d[k] = payload(et)
        raise ValueError(f"unsupported tag type {t}")

    assert take(">b") == COMPOUND
    string()
    return payload(COMPOUND)
