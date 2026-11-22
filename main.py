#!/usr/bin/env python3
"""The World Today -- Sunday 22 November 2026 in one image.

A standard-library-only program that composes a newspaper front page
for the make.fun bounty news-image-20261122 and writes it to
/output/entry.png (or $MAKEFUN_OUTPUT_DIR/entry.png).

The page is drawn, not pasted together: this file carries its own PNG
reader (for the hero illustration in hero.png), its own PNG writer
with per-row adaptive filtering, a small RGB canvas, and a 5x7 bitmap
typeface that sets every word on the page.  Nothing is read from the
network and nothing is left to chance: two runs write the same bytes.
"""

import os
import struct
import zlib

PAGE_W = 1024
PAGE_H = 1024

PAPER = (247, 244, 236)
INK = (24, 22, 20)
RED = (172, 30, 44)
DARKRED = (128, 20, 32)
GREY = (110, 104, 96)
RULE = (24, 22, 20)
TILE_LINE = (196, 188, 172)
WHITE = (252, 250, 246)


# ---------------------------------------------------------------- PNG read

def _paeth(a, b, c):
    """PNG Paeth predictor for one byte."""
    p = a + b - c
    pa = abs(p - a)
    pb = abs(p - b)
    pc = abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def decode_png(path):
    """Decode an 8-bit PNG (grey, palette, RGB or RGBA) to RGB rows.

    Returns (width, height, list of bytearray rows, 3 bytes a pixel).
    Only the non-interlaced layout is supported, which is what the
    illustration in this repository uses.
    """
    with open(path, "rb") as fh:
        blob = fh.read()
    if blob[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG file: %s" % path)
    pos = 8
    width = height = None
    bit_depth = color_type = None
    palette = None
    idat = bytearray()
    while pos < len(blob):
        (length,) = struct.unpack(">I", blob[pos:pos + 4])
        kind = blob[pos + 4:pos + 8]
        data = blob[pos + 8:pos + 8 + length]
        if kind == b"IHDR":
            width, height = struct.unpack(">II", data[:8])
            bit_depth = data[8]
            color_type = data[9]
            if data[12] != 0:
                raise ValueError("interlaced PNG not supported")
        elif kind == b"PLTE":
            palette = data
        elif kind == b"IDAT":
            idat.extend(data)
        elif kind == b"IEND":
            break
        pos += 12 + length
    if bit_depth != 8:
        raise ValueError("only 8-bit PNGs are supported")
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color_type]
    stride = width * channels
    raw = zlib.decompress(bytes(idat))
    rows = []
    prev = bytearray(stride)
    cursor = 0
    for _y in range(height):
        filt = raw[cursor]
        cursor += 1
        line = bytearray(raw[cursor:cursor + stride])
        cursor += stride
        if filt == 1:
            for i in range(channels, stride):
                line[i] = (line[i] + line[i - channels]) & 0xFF
        elif filt == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif filt == 3:
            for i in range(stride):
                left = line[i - channels] if i >= channels else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif filt == 4:
            for i in range(stride):
                left = line[i - channels] if i >= channels else 0
                up = prev[i]
                up_left = prev[i - channels] if i >= channels else 0
                line[i] = (line[i] + _paeth(left, up, up_left)) & 0xFF
        elif filt != 0:
            raise ValueError("unknown PNG filter %d" % filt)
        rows.append(line)
        prev = line
    rgb = []
    for line in rows:
        if color_type == 2:
            rgb.append(line)
        elif color_type == 6:
            out = bytearray(width * 3)
            for x in range(width):
                out[x * 3:x * 3 + 3] = line[x * 4:x * 4 + 3]
            rgb.append(out)
        elif color_type == 3:
            out = bytearray(width * 3)
            for x in range(width):
                base = line[x] * 3
                out[x * 3:x * 3 + 3] = palette[base:base + 3]
            rgb.append(out)
        elif color_type == 0:
            out = bytearray(width * 3)
            for x in range(width):
                out[x * 3] = out[x * 3 + 1] = out[x * 3 + 2] = line[x]
            rgb.append(out)
        else:
            out = bytearray(width * 3)
            for x in range(width):
                out[x * 3] = out[x * 3 + 1] = out[x * 3 + 2] = line[x * 2]
            rgb.append(out)
    return width, height, rgb


# ---------------------------------------------------------------- PNG write

def _filter_row(kind, line, prev, bpp):
    """Apply one PNG filter to a row, returning the filtered bytes."""
    if kind == 0:
        return bytes(line)
    out = bytearray(len(line))
    if kind == 1:
        for i in range(len(line)):
            left = line[i - bpp] if i >= bpp else 0
            out[i] = (line[i] - left) & 0xFF
    elif kind == 2:
        for i in range(len(line)):
            out[i] = (line[i] - prev[i]) & 0xFF
    elif kind == 3:
        for i in range(len(line)):
            left = line[i - bpp] if i >= bpp else 0
            out[i] = (line[i] - ((left + prev[i]) >> 1)) & 0xFF
    else:
        for i in range(len(line)):
            left = line[i - bpp] if i >= bpp else 0
            up = prev[i]
            up_left = prev[i - bpp] if i >= bpp else 0
            out[i] = (line[i] - _paeth(left, up, up_left)) & 0xFF
    return bytes(out)


def _row_score(filtered):
    """PNG's classic heuristic: sum of absolute values of signed bytes."""
    total = 0
    for byte in filtered:
        total += byte if byte < 128 else 256 - byte
    return total


def encode_png(width, height, rows):
    """Encode RGB rows as a PNG, choosing each row's filter by score."""
    bpp = 3
    payload = bytearray()
    prev = bytearray(width * bpp)
    for line in rows:
        best_kind = 0
        best = None
        best_score = None
        for kind in range(5):
            candidate = _filter_row(kind, line, prev, bpp)
            score = _row_score(candidate)
            if best_score is None or score < best_score:
                best_kind = kind
                best = candidate
                best_score = score
        payload.append(best_kind)
        payload.extend(best)
        prev = line
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)

    def chunk(kind, data):
        body = kind + data
        return (struct.pack(">I", len(data)) + body
                + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(bytes(payload), 9))
            + chunk(b"IEND", b""))


# ---------------------------------------------------------------- canvas

class Canvas:
    """A flat RGB pixel buffer with just the drawing this page needs."""

    def __init__(self, width, height, color):
        self.width = width
        self.height = height
        self.rows = [bytearray(color * width) for _ in range(height)]

    def fill_rect(self, x, y, w, h, color):
        if w <= 0 or h <= 0:
            return
        segment = bytes(color) * w
        for yy in range(max(0, y), min(self.height, y + h)):
            row = self.rows[yy]
            row[x * 3:(x + w) * 3] = segment

    def hline(self, x, y, w, color, thickness=1):
        self.fill_rect(x, y, w, thickness, color)

    def vline(self, x, y, h, color, thickness=1):
        self.fill_rect(x, y, thickness, h, color)

    def blit_cover(self, src_w, src_h, src_rows, dx, dy, dw, dh):
        """Draw a source image into a box, centre-cropped to cover it."""
        scale = max(dw / src_w, dh / src_h)
        vis_w = dw / scale
        vis_h = dh / scale
        off_x = (src_w - vis_w) / 2.0
        off_y = (src_h - vis_h) / 2.0
        for yy in range(dh):
            sy = int(off_y + (yy + 0.5) * vis_h / dh)
            sy = min(src_h - 1, max(0, sy))
            src = src_rows[sy]
            dst = self.rows[dy + yy]
            for xx in range(dw):
                sx = int(off_x + (xx + 0.5) * vis_w / dw)
                sx = min(src_w - 1, max(0, sx))
                dst[(dx + xx) * 3:(dx + xx) * 3 + 3] = src[sx * 3:sx * 3 + 3]


# ---------------------------------------------------------------- typeface
#
# A 5x7 bitmap face drawn on a 6x8 cell.  Each glyph is seven rows of
# five marks; '#' sets a pixel.  Only the characters the page sets are
# included: capitals, digits and newspaper punctuation.

GLYPHS = {
    "A": (".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    "B": ("####.", "#...#", "#...#", "####.", "#...#", "#...#", "####."),
    "C": (".####", "#....", "#....", "#....", "#....", "#....", ".####"),
    "D": ("####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####."),
    "E": ("#####", "#....", "#....", "####.", "#....", "#....", "#####"),
    "F": ("#####", "#....", "#....", "####.", "#....", "#....", "#...."),
    "G": (".####", "#....", "#....", "#.###", "#...#", "#...#", ".###."),
    "H": ("#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    "I": ("#####", "..#..", "..#..", "..#..", "..#..", "..#..", "#####"),
    "J": ("..###", "...#.", "...#.", "...#.", "...#.", "#..#.", ".##.."),
    "K": ("#...#", "#..#.", "#.#..", "##...", "#.#..", "#..#.", "#...#"),
    "L": ("#....", "#....", "#....", "#....", "#....", "#....", "#####"),
    "M": ("#...#", "##.##", "#.#.#", "#.#.#", "#...#", "#...#", "#...#"),
    "N": ("#...#", "#...#", "##..#", "#.#.#", "#..##", "#...#", "#...#"),
    "O": (".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    "P": ("####.", "#...#", "#...#", "####.", "#....", "#....", "#...."),
    "Q": (".###.", "#...#", "#...#", "#...#", "#.#.#", "#..#.", ".##.#"),
    "R": ("####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"),
    "S": (".####", "#....", "#....", ".###.", "....#", "....#", "####."),
    "T": ("#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."),
    "U": ("#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    "V": ("#...#", "#...#", "#...#", "#...#", "#...#", ".#.#.", "..#.."),
    "W": ("#...#", "#...#", "#...#", "#.#.#", "#.#.#", "##.##", "#...#"),
    "X": ("#...#", ".#.#.", "..#..", "..#..", "..#..", ".#.#.", "#...#"),
    "Y": ("#...#", "#...#", ".#.#.", "..#..", "..#..", "..#..", "..#.."),
    "Z": ("#####", "....#", "...#.", "..#..", ".#...", "#....", "#####"),
    "0": (".###.", "#...#", "#..##", "#.#.#", "##..#", "#...#", ".###."),
    "1": ("..#..", ".##..", "..#..", "..#..", "..#..", "..#..", "#####"),
    "2": (".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####"),
    "3": ("####.", "....#", "....#", ".###.", "....#", "....#", "####."),
    "4": ("...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."),
    "5": ("#####", "#....", "####.", "....#", "....#", "#...#", ".###."),
    "6": (".###.", "#....", "#....", "####.", "#...#", "#...#", ".###."),
    "7": ("#####", "....#", "...#.", "..#..", ".#...", ".#...", ".#..."),
    "8": (".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###."),
    "9": (".###.", "#...#", "#...#", ".####", "....#", "....#", ".###."),
    " ": (".....", ".....", ".....", ".....", ".....", ".....", "....."),
    ".": (".....", ".....", ".....", ".....", ".....", ".##..", ".##.."),
    ",": (".....", ".....", ".....", ".....", ".##..", ".##..", ".#..."),
    ":": (".....", ".##..", ".##..", ".....", ".##..", ".##..", "....."),
    ";": (".....", ".##..", ".##..", ".....", ".##..", ".##..", ".#..."),
    "'": (".##..", ".##..", ".#...", ".....", ".....", ".....", "....."),
    "-": (".....", ".....", ".....", "#####", ".....", ".....", "....."),
    "+": (".....", "..#..", "..#..", "#####", "..#..", "..#..", "....."),
    "(": ("....#", "...#.", "..#..", "..#..", "..#..", "...#.", "....#"),
    ")": (".#...", "..#..", "..#..", "..#..", "..#..", "..#..", ".#..."),
    "%": ("##..#", "##.#.", "....#", "...#.", "..#..", ".#...", "#.##."),
    "$": ("..#..", ".####", "#.#..", ".###.", "..#.#", "####.", "..#.."),
    "/": ("....#", "....#", "...#.", "..#..", ".#...", "#....", "#...."),
    "!": ("..#..", "..#..", "..#..", "..#..", "..#..", ".....", "..#.."),
    "?": (".###.", "#...#", "....#", "..##.", "..#..", ".....", "..#.."),
    "&": (".##..", "#..#.", "#.#..", ".#...", "#.#.#", "#..#.", ".##.#"),
}

CELL_W = 6
CELL_H = 8


def text_width(text, scale):
    """Width in pixels of a string set at the given scale."""
    if not text:
        return 0
    return (len(text) * CELL_W - 1) * scale


def draw_text(canvas, x, y, text, scale, color, bold=False):
    """Set one line of text with its top-left corner at (x, y)."""
    offsets = (0, max(1, scale // 5)) if bold else (0,)
    for index, char in enumerate(text.upper()):
        glyph = GLYPHS.get(char, GLYPHS[" "])
        gx = x + index * CELL_W * scale
        for row_i, row in enumerate(glyph):
            for col_i, mark in enumerate(row):
                if mark != "#":
                    continue
                for off in offsets:
                    canvas.fill_rect(gx + col_i * scale + off,
                                     y + row_i * scale,
                                     scale, scale, color)
    return text_width(text, scale)


def draw_centered(canvas, y, text, scale, color, bold=False):
    x = (canvas.width - text_width(text, scale)) // 2
    draw_text(canvas, x, y, text, scale, color, bold)
    return x


def wrap_text(text, scale, max_width):
    """Greedy word wrap: lines that fit max_width at the given scale."""
    words = text.split()
    lines = []
    current = ""
    for word in words:
        trial = word if not current else current + " " + word
        if text_width(trial, scale) <= max_width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def draw_wrapped(canvas, x, y, text, scale, color, max_width, leading,
                 bold=False, max_lines=None):
    """Set wrapped text; returns the y just past the last line."""
    lines = wrap_text(text, scale, max_width)
    if max_lines is not None:
        lines = lines[:max_lines]
    for i, line in enumerate(lines):
        draw_text(canvas, x, y + i * leading, line, scale, color, bold)
    return y + len(lines) * leading


# ---------------------------------------------------------------- the news
#
# Sunday 22 November 2026, as the wires carried it.  The lead is the
# Iranian strike on the US bases in Bahrain; six more stories run as
# tiles and the rest of the day rides the ticker.

KICKER = "MIDDLE EAST / GULF CRISIS"
HEADLINE = "IRAN STRIKES US BASES IN BAHRAIN"
STANDFIRST = (
    "TEHRAN'S IRGC SAYS ITS MISSILES AND DRONES HIT TWO US PATRIOT "
    "RADAR SITES AT AL-RIFFA AND AWALI LATE ON SATURDAY. BAHRAIN "
    "REPORTS AN IRANIAN ATTACK ON A CIVILIAN INDUSTRIAL SITE: FIRE, "
    "BUT NO INJURIES. WASHINGTON HAS NOT CONFIRMED ANY DAMAGE."
)
CAPTION = "MISSILE TRAILS OVER THE GULF AT DUSK"

TILES = [
    ("CLIMATE",
     "COP31 TALKS RUN INTO OVERTIME ON FOSSIL FUELS",
     "NEGOTIATORS WORK THROUGH A THIRD DRAFT INTO SUNDAY MORNING, "
     "WITH A 9AM PLENARY SET AND A NO-DEAL END TO THE SUMMIT LOOMING."),
    ("MEXICO",
     "FBI MOST-WANTED 'EL CHAPO ISIDRO' CAPTURED",
     "MEXICAN FORCES TAKE THE CARTEL FIGURE IN GUASAVE. ELEVEN PEOPLE "
     "DIE IN THE OPERATION, AMONG THEM FOUR SOLDIERS."),
    ("BALTIC SEA",
     "RUSSIAN SHIP SPARTA II STILL BURNING",
     "THE CARGO VESSEL BURNS ON AFTER A DRONE ATTACK. ALL 16 CREW ARE "
     "SAFE, FINLAND LEADS THE RESCUE, AND EYES TURN TO UKRAINE."),
    ("HONG KONG",
     "CITY VOTES FOR ITS POWER COMMITTEE",
     "ABOUT 5,700 VOTERS CHOOSE THE ELECTION COMMITTEE THAT HELPS "
     "PICK THE CITY'S NEXT LEADER AND ITS LAWMAKERS."),
    ("TENNIS",
     "ZVEREV V ALCARAZ FOR THE TURIN CROWN",
     "THE ATP FINALS CLOSE TONIGHT WITH A BLOCKBUSTER: ALEXANDER "
     "ZVEREV AGAINST CARLOS ALCARAZ FOR THE SEASON'S LAST BIG TITLE."),
    ("UKRAINE",
     "DOUBLE-TAP STRIKE HITS KRYVYI RIH",
     "A SECOND RUSSIAN STRIKE HITS RESCUERS AT THE SCENE OF THE "
     "FIRST. TWO PEOPLE ARE KILLED AND 60 ARE WOUNDED."),
]

TICKER = (
    "BOLSONARO IN ICU +++ AL-SHABAAB AMBUSH IN SOMALIA +++ ZELENSKYY: "
    "NATO BEST GUARANTEE +++ EU-INDONESIA DEAL SIGNED +++ "
    "TRUMP SEES 20-YEAR IRAN DEAL"
)


# ---------------------------------------------------------------- the page

MARGIN = 28
CONTENT_W = PAGE_W - 2 * MARGIN


def draw_tile(canvas, x, y, w, kicker, headline, body):
    """One story tile: red kicker, bold headline, small body text."""
    draw_text(canvas, x, y, kicker, 2, RED, bold=True)
    head_end = draw_wrapped(canvas, x, y + 18, headline, 2, INK,
                            w - 6, 19, bold=True, max_lines=2)
    draw_wrapped(canvas, x, head_end + 3, body, 1, INK, w - 6, 10,
                 max_lines=4)


def build_front_page(hero_path):
    page = Canvas(PAGE_W, PAGE_H, PAPER)

    # Folio line, then the masthead between two rules.
    draw_text(page, MARGIN, 5, "VOL. I / NO. 22", 1, GREY)
    folio = "ONE IMAGE EDITION"
    draw_text(page, PAGE_W - MARGIN - text_width(folio, 1), 5, folio,
              1, GREY)
    page.hline(MARGIN, 16, CONTENT_W, RULE, 3)
    draw_centered(page, 26, "THE WORLD TODAY", 10, INK, bold=True)
    page.hline(MARGIN, 104, CONTENT_W, RULE, 3)

    # The date band: the day this page sums up, in red.
    page.fill_rect(0, 112, PAGE_W, 42, RED)
    draw_centered(page, 116, "SUNDAY 22 NOVEMBER 2026", 5, WHITE,
                  bold=True)

    # The hero picture, framed.
    src_w, src_h, src_rows = decode_png(hero_path)
    page.blit_cover(src_w, src_h, src_rows, MARGIN, 166, CONTENT_W, 380)
    page.vline(MARGIN - 2, 164, 384, INK, 2)
    page.vline(PAGE_W - MARGIN, 164, 384, INK, 2)
    page.hline(MARGIN - 2, 164, CONTENT_W + 4, INK, 2)
    page.hline(MARGIN - 2, 546, CONTENT_W + 4, INK, 2)
    cap_w = text_width(CAPTION, 1)
    draw_text(page, PAGE_W - MARGIN - cap_w, 552, CAPTION, 1, GREY)

    # Lead story: kicker, headline, standfirst.
    draw_text(page, MARGIN, 560, KICKER, 3, RED, bold=True)
    draw_text(page, MARGIN, 590, HEADLINE, 5, INK, bold=True)
    draw_wrapped(page, MARGIN, 636, STANDFIRST, 2, INK, CONTENT_W, 19,
                 max_lines=4)
    page.hline(MARGIN, 716, CONTENT_W, RULE, 2)

    # Six tiles in two rows of three, with hairline separators.
    col_w = (CONTENT_W - 20) // 3
    top = 726
    row_h = 104
    for i, (kicker, headline, body) in enumerate(TILES):
        col = i % 3
        row = i // 3
        x = MARGIN + col * (col_w + 10)
        y = top + row * (row_h + 8)
        draw_tile(page, x, y, col_w, kicker, headline, body)
    for col in (1, 2):
        page.vline(MARGIN + col * (col_w + 10) - 5, top, row_h * 2 + 8,
                   TILE_LINE, 1)
    page.hline(MARGIN, top + row_h + 3, CONTENT_W, TILE_LINE, 1)

    # The wire ticker along the foot of the page.
    page.fill_rect(0, 954, PAGE_W, 56, INK)
    draw_wrapped(page, 22, 964, "WIRE: " + TICKER, 2, WHITE,
                 PAGE_W - 44, 19, max_lines=2)
    return page


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    page = build_front_page(os.path.join(here, "hero.png"))
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    os.makedirs(out_dir, exist_ok=True)
    target = os.path.join(out_dir, "entry.png")
    with open(target, "wb") as fh:
        fh.write(encode_png(page.width, page.height, page.rows))


if __name__ == "__main__":
    main()
