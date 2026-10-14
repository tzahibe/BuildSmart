"""CONCEPTUAL PARTI DIAGRAMS (#186, Investigation 7) — deliberately NOT floor plans.

Each figure is a hand-authored schematic of an architectural *idea* for one frozen brief: zones as
blocks, circulation as a line, the street and the garden named, the entrance marked. No dimension
here is solved, validated or claimed realizable; the realizability of each is an open question the
report states explicitly. Every figure carries that warning in its own title.

    PYTHONPATH=backend python -m app.ai_harness.arch_direction.parti_diagrams <out-dir>
"""
from __future__ import annotations

import os
import sys

W, H = 300, 230          # one parti cell
PAD = 16

FILL = {"public": "#cfe3f7", "private": "#dfeedd", "wet": "#ede0f2", "circ": "#fbe9c6",
        "out": "#eef6e6", "service": "#eceff1"}
STROKE = "#334"


def _fit(text: str, width: float, per_char: float) -> list[str]:
    """Break a block's own label so it stays inside the block — these diagrams are read, not
    measured, and a label spilling over a neighbour is the one thing that makes them unreadable."""
    if len(text) * per_char <= width:
        return [text]
    words, lines, cur = text.split(" "), [], ""
    for word in words:
        trial = f"{cur} {word}".strip()
        if cur and len(trial) * per_char > width:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines


def _rect(x, y, w, h, kind, label, sub=""):
    out = (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{FILL[kind]}" '
           f'stroke="{STROKE}" stroke-width="1.2"/>')
    lines = _fit(label, w - 8, 5.1)
    top = y + h / 2 + 3 - (len(lines) - 1) * 6
    for i, text in enumerate(lines):
        out += (f'<text x="{x + w / 2}" y="{top + i * 12}" font-size="9.5" text-anchor="middle" '
                f'font-family="Helvetica,Arial" fill="#112">{text}</text>')
    if sub:
        base = top + len(lines) * 12
        for i, text in enumerate(_fit(sub, w - 8, 4.1)):
            out += (f'<text x="{x + w / 2}" y="{base + i * 9}" font-size="7.5" '
                    f'text-anchor="middle" font-family="Helvetica,Arial" fill="#556">{text}</text>')
    return out


def _dashed(x, y, w, h, label):
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{FILL["out"]}" '
            f'stroke="#8a9" stroke-width="1" stroke-dasharray="4 3"/>'
            f'<text x="{x + w / 2}" y="{y + h / 2 + 3}" font-size="8.5" text-anchor="middle" '
            f'font-family="Helvetica,Arial" fill="#475">{label}</text>')


def _line(x1, y1, x2, y2, label=""):
    out = (f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#b4651a" '
           f'stroke-width="3.2" stroke-linecap="round"/>')
    if label:
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2 - 7
        out += (f'<rect x="{cx - len(label) * 2.3}" y="{cy - 8}" width="{len(label) * 4.6}" '
                f'height="11" rx="2" fill="#fff" opacity="0.92"/>'
                f'<text x="{cx}" y="{cy}" font-size="7.5" text-anchor="middle" '
                f'font-family="Helvetica,Arial" fill="#8a4a10">{label}</text>')
    return out


def _entry(x, y):
    return (f'<circle cx="{x}" cy="{y}" r="5" fill="#fff" stroke="#b4651a" stroke-width="2"/>'
            f'<text x="{x}" y="{y + 3}" font-size="7" text-anchor="middle" '
            f'font-family="Helvetica,Arial" fill="#b4651a">E</text>')


def cell(title, body, note):
    return (f'<text x="0" y="-18" font-size="11.5" font-weight="bold" '
            f'font-family="Helvetica,Arial" fill="#112">{title}</text>'
            f'<text x="0" y="-5" font-size="8" font-family="Helvetica,Arial" fill="#667">'
            f'{note}</text>' + body)


def _subtitle_lines(subtitle: str, width: int = 150) -> list[str]:
    words, lines, cur = subtitle.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width:
            lines.append(cur); cur = w
        else:
            cur = f"{cur} {w}".strip()
    lines.append(cur)
    return [f'<text x="{PAD}" y="{PAD + 42 + i * 12}" font-size="9" '
            f'font-family="Helvetica,Arial" fill="#556">{t}</text>' for i, t in enumerate(lines)]


def figure(brief, subtitle, cells) -> str:
    total_w = PAD * 2 + len(cells) * W + (len(cells) - 1) * 30
    total_h = PAD * 2 + H + 98
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{total_w}" height="{total_h}" '
             f'viewBox="0 0 {total_w} {total_h}">',
             f'<rect width="{total_w}" height="{total_h}" fill="#fff"/>',
             f'<text x="{PAD}" y="{PAD + 12}" font-size="14" font-weight="bold" '
             f'font-family="Helvetica,Arial" fill="#112">{brief} — three conceptual partis</text>',
             f'<text x="{PAD}" y="{PAD + 28}" font-size="9.5" font-family="Helvetica,Arial" '
             f'fill="#a33">CONCEPTUAL DIAGRAMS — NOT validated floor plans. No dimension here has '
             f'been solved or checked by any validator.</text>',
             *_subtitle_lines(subtitle)]
    for i, (title, body, note) in enumerate(cells):
        parts.append(f'<g transform="translate({PAD + i * (W + 30)},{PAD + 98})">'
                     + cell(title, body, note) + '</g>')
    parts.append('</svg>')
    return "".join(parts)


def _street_garden(label_street="STREET (north edge, parking + walk)",
                   label_garden="GARDEN (rear)"):
    return (f'<text x="{W / 2}" y="-30" font-size="7.5" text-anchor="middle" '
            f'font-family="Helvetica,Arial" fill="#667">{label_street}</text>'
            f'<text x="{W / 2}" y="{H + 14}" font-size="7.5" text-anchor="middle" '
            f'font-family="Helvetica,Arial" fill="#667">{label_garden}</text>')


# ------------------------------------------------------------------ B06: 3 bed, 2 wet, 13 x 24 m
def b06():
    sg = _street_garden()
    # 1. REAR-FACING PUBLIC BAND
    a = sg + _rect(0, 0, 190, 42, "circ", "ENTRY HALL", "arrival, street side")
    a += _rect(190, 0, 110, 42, "service", "STORE / WC", "")
    a += _rect(0, 42, 110, 90, "private", "BED 1", "")
    a += _rect(110, 42, 80, 90, "wet", "BATH", "")
    a += _rect(190, 42, 110, 90, "private", "BED 2", "")
    a += _line(6, 46, 294, 46)
    a += _rect(0, 132, 300, 98, "public", "LIVING / DINING / KITCHEN", "full width, opens to garden")
    a += _entry(95, 2)
    # 2. COURTYARD / C-PLAN
    b = sg + _rect(0, 0, 118, 58, "circ", "ENTRY", "")
    b += _rect(118, 0, 182, 58, "public", "KITCHEN / DINING", "")
    b += _rect(0, 58, 90, 172, "public", "LIVING", "two-sided light")
    b += _dashed(90, 58, 120, 104, "COURTYARD")
    b += _rect(210, 58, 90, 172, "private", "BED 1 / BED 2", "bedroom arm")
    b += _rect(90, 162, 120, 68, "wet", "BATH + MASTER", "")
    b += _line(92, 60, 92, 226)
    b += _entry(58, 2)
    # 3. SPLIT-WING / TWO VOLUMES
    c = sg + _rect(0, 0, 130, 110, "public", "LIVING / DINING", "street volume")
    c += _rect(130, 0, 40, 230, "circ", "LINK", "glazed joint")
    c += _rect(170, 0, 130, 110, "public", "KITCHEN", "")
    c += _rect(0, 110, 130, 120, "private", "MASTER + BATH", "garden volume")
    c += _rect(170, 110, 130, 120, "private", "BED 1 / BED 2", "")
    c += _entry(150, 2)
    return figure(
        "B06", "3 bedrooms, 2 wet rooms, no safe room, not open-plan, 312 m² requested on a "
               "13 × 24 m envelope. Production delivers 177 m² with the master at the garden, "
               "the living room at the street and a 27.6 m² unassigned block.",
        [("A — rear public band",
          a, "public band moved to the garden; a cross corridor, not a full-depth slot"),
         ("B — courtyard (C-plan)",
          b, "the void is the organiser; every room gets two orientations"),
         ("C — two volumes on a link",
          c, "public and private as separate masses joined by a glazed link")])


# ------------------------------------------- B16: 5 bed + safe room, 3 wet, 216 m², 18 x 12 m wide
def b16():
    sg = _street_garden()
    a = sg + _rect(0, 0, 300, 46, "circ", "ENTRY GALLERY", "along the street wall")
    a += _rect(0, 46, 96, 92, "public", "LIVING", "")
    a += _rect(96, 46, 96, 92, "public", "DINING", "")
    a += _rect(192, 46, 108, 92, "public", "KITCHEN", "")
    a += _rect(0, 138, 60, 92, "wet", "BATH", "")
    a += _rect(60, 138, 60, 92, "private", "BED 1", "")
    a += _rect(120, 138, 60, 92, "private", "BED 2", "")
    a += _rect(180, 138, 60, 92, "private", "BED 3", "")
    a += _rect(240, 138, 60, 92, "private", "MAMAD", "two envelope faces")
    a += _line(6, 43, 294, 43)
    a += _entry(150, 2)
    b = sg + _rect(0, 0, 150, 50, "circ", "FOYER", "")
    b += _rect(150, 0, 150, 50, "private", "MAMAD + BATH", "service corner at the street")
    b += _rect(0, 50, 300, 10, "circ", "", "")
    b += _rect(0, 60, 110, 170, "private", "BED 1-3 stack", "quiet wing")
    b += _rect(110, 60, 70, 170, "circ", "SPINE", "")
    b += _rect(180, 60, 120, 110, "public", "LIVING / DINING", "")
    b += _rect(180, 170, 120, 60, "public", "KITCHEN", "")
    b += _line(178, 58, 178, 226)
    b += _entry(75, 2)
    c = sg + _rect(0, 0, 105, 60, "circ", "ENTRY", "")
    c += _rect(105, 0, 195, 60, "public", "KITCHEN / DINING", "")
    c += _rect(0, 60, 105, 170, "public", "LIVING", "")
    c += _dashed(105, 60, 105, 90, "PATIO")
    c += _rect(210, 60, 90, 90, "private", "MASTER + BATH", "")
    c += _rect(105, 150, 195, 80, "private", "BED 1-3 + MAMAD", "garden-side children's wing")
    c += _line(110, 150, 295, 150, "")
    c += _line(103, 60, 103, 228)
    c += _entry(52, 2)
    return figure(
        "B16", "5 bedrooms + safe room (MAMAD), 3 wet rooms, open-plan, 216 m² on a wide "
               "18 × 12 m envelope. Production delivers 188 m² with all three public rooms on the "
               "west side and an 11.9 : 1 corridor.",
        [("A — street gallery, garden bedrooms",
          a, "circulation along the street wall becomes the acoustic buffer"),
         ("B — service corner + cross spine",
          b, "the MAMAD is put where no room wants to be: the street corner"),
         ("C — L around a patio",
          c, "the wide envelope's natural parti; two wings, one outdoor room")])


# ----------------------------------------------------- B09: 3 bed, 3 wet, 440 m², 20 x 22 m large
def b09():
    sg = _street_garden()
    a = sg + _rect(0, 0, 112, 66, "circ", "ENTRY COURT", "")
    a += _rect(112, 0, 188, 66, "service", "GARAGE / STORE / WC", "")
    a += _rect(0, 66, 112, 164, "private", "GUEST SUITE", "")
    a += _dashed(112, 66, 96, 96, "COURTYARD")
    a += _rect(208, 66, 92, 164, "private", "MASTER SUITE", "")
    a += _rect(112, 162, 96, 68, "public", "KITCHEN", "")
    a += _line(109, 66, 109, 228)
    a += _line(206, 66, 206, 228)
    a += _entry(56, 2)
    b = sg + _rect(0, 0, 300, 50, "service", "ENTRY + SERVICE STRIP", "garage, store, WC")
    b += _rect(0, 50, 300, 16, "circ", "", "")
    b += _rect(0, 66, 96, 164, "private", "BED 1 / BED 2 + BATH", "")
    b += _rect(96, 66, 72, 164, "circ", "DOUBLE-HEIGHT HALL", "the room that IS the circulation")
    b += _rect(168, 66, 132, 100, "public", "LIVING / DINING", "")
    b += _rect(168, 166, 132, 64, "public", "KITCHEN", "")
    b += _line(165, 64, 165, 228)
    b += _entry(150, 2)
    c = sg + _rect(0, 0, 140, 72, "circ", "FOYER", "")
    c += _rect(140, 0, 160, 72, "private", "MASTER SUITE", "street wing, screened")
    c += _rect(0, 72, 300, 14, "circ", "", "")
    c += _rect(0, 86, 180, 144, "public", "LIVING / DINING / KITCHEN", "one great room to the garden")
    c += _dashed(180, 86, 120, 70, "TERRACE")
    c += _rect(180, 156, 120, 74, "private", "BED 1 / BED 2 + BATH", "")
    c += _line(6, 79, 294, 79)
    c += _entry(70, 2)
    return figure(
        "B09", "3 bedrooms, 3 wet rooms, 440 m² requested on a 20 × 22 m envelope. Production "
               "delivers 227 m² — 114 % of the programme's own capacity — in which the single "
               "largest garden-facing element is a 54.3 m² unassigned block.",
        [("A — courtyard house",
          a, "at this area the void is affordable and solves depth-of-plan"),
         ("B — circulation as a room",
          b, "the hall is a space, not a 11 : 1 residual slot"),
         ("C — great room to the garden",
          c, "the surplus area goes to ONE generous public room, not to FLEX")])


def main(out_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    for name, svg in (("B06-partis.svg", b06()), ("B16-partis.svg", b16()),
                      ("B09-partis.svg", b09())):
        with open(os.path.join(out_dir, name), "w") as fh:
            fh.write(svg)
        print(f"wrote {name}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
