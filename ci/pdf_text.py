"""The text of every content stream of a PDF, standard library only.

usage: python3 ci/pdf_text.py <pdf>

The copy check of the integration proof reads the placeholder copy with this
and not with the engine that wrote it (owner rule: the counter check never
uses the pattern of the implementation). It decodes unfiltered and
FlateDecode streams, skips images and embedded fonts, and prints every string
operand: literal strings with their escapes, hex strings, the parts of one TJ
array joined, one text run per line. Simple fonts are read as cp1252, a hex
string with a byte order mark as UTF-16BE.

This is deliberately crude: it is a reader for a canary search, not a text
extractor. It reads more than the visible text (every string of every content
stream), which only makes a negative search stricter.
"""

import re
import sys
import zlib
from pathlib import Path
from typing import Final

_STREAM: Final = re.compile(rb"<<(?P<dict>(?:(?!stream).){0,4096}?)>>\s*stream\r?\n", re.DOTALL)
_SKIP: Final = re.compile(rb"/Subtype\s*/Image|/Length1|/Length2|/Length3|/Type\s*/XRef|/Subtype\s*/Type1C|/FontFile")
_FLATE: Final = re.compile(rb"/Filter\s*(?:\[\s*)?/FlateDecode\s*\]?")
_OTHER_FILTER: Final = re.compile(rb"/Filter")
_ESCAPES: Final = {ord("n"): 10, ord("r"): 13, ord("t"): 9, ord("b"): 8, ord("f"): 12}


def streams(data: bytes) -> list[bytes]:
    """The decoded bodies of every stream that may carry text."""
    found = []
    for match in _STREAM.finditer(data):
        head = match.group("dict")
        start = match.end()
        end = data.find(b"endstream", start)
        if end < 0 or _SKIP.search(head):
            continue
        body = data[start:end]
        if _FLATE.search(head):
            try:
                body = zlib.decompressobj().decompress(body)
            except zlib.error:
                continue
        elif _OTHER_FILTER.search(head):
            continue
        found.append(body)
    return found


def _literal(body: bytes, index: int) -> tuple[bytes, int]:
    """One literal string starting after its "(", with nesting and escapes."""
    out = bytearray()
    depth = 1
    while index < len(body):
        char = body[index]
        index += 1
        if char == 0x5C and index < len(body):  # backslash
            nxt = body[index]
            index += 1
            if nxt in _ESCAPES:
                out.append(_ESCAPES[nxt])
            elif 0x30 <= nxt <= 0x37:
                digits = bytes([nxt])
                while len(digits) < 3 and index < len(body) and 0x30 <= body[index] <= 0x37:
                    digits += bytes([body[index]])
                    index += 1
                out.append(int(digits, 8) & 0xFF)
            elif nxt in (0x0A, 0x0D):
                if nxt == 0x0D and index < len(body) and body[index] == 0x0A:
                    index += 1
            else:
                out.append(nxt)
        elif char == 0x28:
            depth += 1
            out.append(char)
        elif char == 0x29:
            depth -= 1
            if depth == 0:
                break
            out.append(char)
        else:
            out.append(char)
    return bytes(out), index


def _hex(body: bytes, index: int) -> tuple[bytes, int]:
    end = body.find(b">", index)
    end = len(body) if end < 0 else end
    digits = re.sub(rb"[^0-9A-Fa-f]", b"", body[index:end])
    if len(digits) % 2:
        digits += b"0"
    return bytes.fromhex(digits.decode("ascii")), end + 1


def _decode(raw: bytes) -> str:
    if raw.startswith(b"\xfe\xff"):
        return raw[2:].decode("utf-16-be", errors="replace")
    return raw.decode("cp1252", errors="replace")


def runs(body: bytes) -> list[str]:
    """Every string operand; the strings of one array form one run."""
    out: list[str] = []
    array: list[str] | None = None
    index = 0
    while index < len(body):
        char = body[index]
        if char == 0x28:
            raw, index = _literal(body, index + 1)
        elif char == 0x3C and body[index + 1 : index + 2] != b"<":
            raw, index = _hex(body, index + 1)
        elif char == 0x3C:
            index += 2
            continue
        elif char == 0x5B:
            array = []
            index += 1
            continue
        elif char == 0x5D:
            if array:
                out.append("".join(array))
            array = None
            index += 1
            continue
        elif char == 0x25:  # comment up to the end of the line
            newline = re.compile(rb"[\r\n]").search(body, index)
            index = len(body) if newline is None else newline.end()
            continue
        else:
            index += 1
            continue
        text = _decode(raw)
        if array is not None:
            array.append(text)
        else:
            out.append(text)
    return out


def text_of(data: bytes) -> str:
    return "\n".join(run for body in streams(data) for run in runs(body))


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: pdf_text.py <pdf>", file=sys.stderr)
        return 2
    try:
        data = Path(argv[0]).read_bytes()
    except OSError:
        print("pdf_text.py: the file could not be read", file=sys.stderr)
        return 2
    sys.stdout.buffer.write((text_of(data) + "\n").encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
