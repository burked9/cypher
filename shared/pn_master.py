"""Bloom-filter-backed master list for cross-checking aviation reference data.

Rationale
---------
Cypher needs to validate extracted PART_NUMBER (and optionally MFR_CODE / ATA)
against an authoritative master list, but **must not ship the master list
itself**:

- the deployed site is a static asset on GitHub Pages, fully visible to anyone
- a 1 M-row CSV would be a PyPI/registry honey-pot for scrapers
- the master list represents months of curation work elsewhere

A Bloom filter solves this: it answers "is `x` in the set?" with a tunable
false-positive rate while being **mathematically one-way** — you cannot
enumerate the set from the filter. Even if the binary file is downloaded by
every visitor, the contents of the master list are not recoverable.

Three lookups are supported:

    is_known_pn(value)         # part numbers
    is_known_mfr_code(value)   # 5-char manufacturer / vendor / CAGE codes
    is_known_ata(value)        # ATA chapter strings

When the binary file is missing (no master loaded yet), every lookup returns
`None`, signalling "no opinion". `clean_record` then leaves `_pn_known`
unset — the absence of a check is distinct from a negative check.

Format
------
Single binary file (default `shared/pn_master.bloom`):

    bytes  0..  3   magic "CYPM"           (Cypher PN Master)
    bytes  4..  4   format version (=1)
    bytes  5..  5   reserved
    bytes  6..  7   namespace count N (uint16 LE)
    repeat N times:
        4 bytes  namespace tag, ASCII, padded with '\\0'  (e.g. "pn  ", "mfr ", "ata ")
        8 bytes  bit count m (uint64 LE)
        4 bytes  hash count k (uint32 LE)
        m/8 bytes bit array

The container holds independent filters per namespace, each tuned at build
time based on the source set's size and the desired false-positive rate.
"""
from __future__ import annotations
import hashlib
import math
import struct
from pathlib import Path
from typing import Iterable

MAGIC = b"CYPM"
VERSION = 1


# ---------------------------------------------------------------------------
# Bloom filter — pure-Python, Pyodide-safe
# ---------------------------------------------------------------------------
class _Bloom:
    __slots__ = ("m", "k", "bits")

    def __init__(self, m: int, k: int, bits: bytearray | None = None):
        self.m = m
        self.k = k
        self.bits = bits if bits is not None else bytearray((m + 7) // 8)

    @classmethod
    def for_capacity(cls, n: int, fp_rate: float = 0.001) -> "_Bloom":
        """Size a fresh filter for `n` items at the given false-positive rate."""
        n = max(1, n)
        m = max(8, int(math.ceil(-n * math.log(fp_rate) / (math.log(2) ** 2))))
        k = max(1, int(round((m / n) * math.log(2))))
        return cls(m, k)

    def _positions(self, item: str) -> Iterable[int]:
        b = item.encode("utf-8") if isinstance(item, str) else item
        h = hashlib.sha256(b).digest()
        h1 = int.from_bytes(h[:8], "little")
        h2 = int.from_bytes(h[8:16], "little") | 1   # ensure odd → independent
        for i in range(self.k):
            yield (h1 + i * h2) % self.m

    def add(self, item: str) -> None:
        for p in self._positions(item):
            self.bits[p >> 3] |= 1 << (p & 7)

    def __contains__(self, item: str) -> bool:
        for p in self._positions(item):
            if not (self.bits[p >> 3] & (1 << (p & 7))):
                return False
        return True


# ---------------------------------------------------------------------------
# Container — holds multiple namespace filters
# ---------------------------------------------------------------------------
class PNMaster:
    """Container for per-namespace Bloom filters.

    Use `PNMaster.build(...)` to create from raw item lists, then `to_bytes()`
    to serialise. Use `PNMaster.from_bytes(...)` on the deployed side.
    """
    def __init__(self, filters: dict[str, _Bloom]):
        self._filters = filters  # tag -> _Bloom

    # ── building ────────────────────────────────────────────────────────────
    @classmethod
    def build(cls, namespaces: dict[str, list[str]], fp_rate: float = 0.001) -> "PNMaster":
        filters: dict[str, _Bloom] = {}
        for tag, items in namespaces.items():
            bf = _Bloom.for_capacity(len(items), fp_rate)
            for x in items:
                if x is None:
                    continue
                s = str(x).strip().upper()
                if s:
                    bf.add(s)
            filters[tag] = bf
        return cls(filters)

    # ── lookup ──────────────────────────────────────────────────────────────
    def has(self, namespace: str, value: str) -> bool:
        bf = self._filters.get(namespace)
        if bf is None:
            return False
        s = str(value).strip().upper()
        if not s:
            return False
        return s in bf

    @property
    def namespaces(self) -> list[str]:
        return list(self._filters.keys())

    # ── serialisation ───────────────────────────────────────────────────────
    def to_bytes(self) -> bytes:
        out = bytearray()
        out += MAGIC
        out += struct.pack("<BBH", VERSION, 0, len(self._filters))
        for tag, bf in self._filters.items():
            tag_bytes = tag.encode("ascii")[:4].ljust(4, b"\x00")
            out += tag_bytes
            out += struct.pack("<QI", bf.m, bf.k)
            out += bytes(bf.bits)
        return bytes(out)

    @classmethod
    def from_bytes(cls, data: bytes) -> "PNMaster":
        if data[:4] != MAGIC:
            raise ValueError("Not a Cypher PN master file (bad magic)")
        version, _reserved, n = struct.unpack("<BBH", data[4:8])
        if version != VERSION:
            raise ValueError(f"Unsupported PN master version: {version}")
        filters: dict[str, _Bloom] = {}
        offset = 8
        for _ in range(n):
            tag = data[offset:offset + 4].rstrip(b"\x00").decode("ascii")
            m, k = struct.unpack("<QI", data[offset + 4:offset + 16])
            bits_len = (m + 7) // 8
            bits = bytearray(data[offset + 16:offset + 16 + bits_len])
            filters[tag] = _Bloom(m, k, bits)
            offset += 16 + bits_len
        return cls(filters)


# ---------------------------------------------------------------------------
# Module-level convenience: load the bundled master once
# ---------------------------------------------------------------------------
_MASTER: PNMaster | None = None
_LOAD_ATTEMPTED = False
_DEFAULT_PATH = Path(__file__).resolve().parent / "pn_master.bloom"


def _load() -> PNMaster | None:
    """Lazy single-shot load of the bundled master, if present."""
    global _MASTER, _LOAD_ATTEMPTED
    if _LOAD_ATTEMPTED:
        return _MASTER
    _LOAD_ATTEMPTED = True
    try:
        if _DEFAULT_PATH.exists():
            _MASTER = PNMaster.from_bytes(_DEFAULT_PATH.read_bytes())
    except Exception:
        # Soft failure — running without a master is a valid mode.
        _MASTER = None
    return _MASTER


def is_loaded() -> bool:
    return _load() is not None


def is_known_pn(value: str) -> bool | None:
    """True / False / None (no master loaded)."""
    m = _load()
    if m is None:
        return None
    return m.has("pn", value)


def is_known_mfr_code(value: str) -> bool | None:
    m = _load()
    if m is None:
        return None
    return m.has("mfr", value)


def is_known_ata(value: str) -> bool | None:
    m = _load()
    if m is None:
        return None
    return m.has("ata", value)
