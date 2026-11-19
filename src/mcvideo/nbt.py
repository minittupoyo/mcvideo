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


class StructureWriter:
    """Fast path for ``dumps`` of a ``width x height x 1`` structure (same bytes as the generic serialiser).

    Every block is ``{"pos": [x, y, 0], "state": i}``, so the bytes of each cell's ``pos`` and of each ``state`` are
    built once and just concatenated per frame. ``level`` is the gzip level (6 is as small as 9 here but much faster).
    """

    def __init__(self, width, height, data_version, level=6):
        self.width, self.height, self.level = width, height, level
        self._head = (struct.pack(">b", INT) + _string("DataVersion") + struct.pack(">i", data_version)
                      + struct.pack(">b", LIST) + _string("size") + struct.pack(">bi3i", INT, 3, width, height, 1))
        self._pos = [struct.pack(">b", LIST) + _string("pos")
                     + struct.pack(">bi3i", INT, 3, width - 1 - k % width, height - 1 - k // width, 0)
                     for k in range(width * height)]
        self._state = {}

    def _state_bytes(self, i):
        if i not in self._state:
            self._state[i] = struct.pack(">b", INT) + _string("state") + struct.pack(">i", i) + b"\x00"
        return self._state[i]

    def dumps(self, pixels, names):
        """``pixels``: ``{row * width + col: key}``; ``names[key]`` is the block id. Keys are numbered in sorted order."""
        used = sorted(set(pixels.values()))
        index = {p: self._state_bytes(i) for i, p in enumerate(used)}
        palette = b"".join(struct.pack(">b", STRING) + _string("Name") + _string(names[p]) + b"\x00" for p in used)
        pos = self._pos
        body = b"".join([pos[k] + index[v] for k, v in sorted(pixels.items())])
        raw = (struct.pack(">b", COMPOUND) + _string("") + self._head
               + struct.pack(">b", LIST) + _string("palette") + struct.pack(">bi", COMPOUND, len(used)) + palette
               + struct.pack(">b", LIST) + _string("blocks") + struct.pack(">bi", COMPOUND, len(pixels)) + body
               + struct.pack(">b", LIST) + _string("entities") + struct.pack(">bi", 0, 0) + b"\x00")
        return gzip.compress(raw, compresslevel=self.level, mtime=0)


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
