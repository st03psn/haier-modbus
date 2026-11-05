"""Erzeugt eigene, maßstäbliche SVG-Abbilder der Haier-M7-Modelle (Issue #29).

Keine Haier-Bilder: alles hier ist selbst gezeichnet; die Maße stammen aus dem
Haier-Datenblatt „M7 HPWH R290“ (haierhvac.eu, 09/2025), siehe docs/m7-modelle.md.
1 SVG-Einheit = 5 mm. Aufruf: python tools/gen_model_svgs.py  -> docs/images/models/
"""
from __future__ import annotations

import pathlib

MM = 1 / 5  # mm -> SVG-Einheit
# Datenblatt: Breite 600 (Ø Mantel), Tiefe 620, Gesamthöhe D; C = Höhe oberer Anschluss
MODELS = {
    "hp200m7_f9": {"name": "HP200M7-F9", "D": 1694, "C": 980, "coil": False, "vol": 194},
    "hp200m7c_f9": {"name": "HP200M7C-F9", "D": 1694, "C": 980, "coil": True, "vol": 185},
    "hp250m7_f9": {"name": "HP250M7-F9", "D": 1989, "C": 1275, "coil": False, "vol": 250},
    "hp250m7c_f9": {"name": "HP250M7C-F9", "D": 1989, "C": 1275, "coil": True, "vol": 240},
}
HEAD_MM = 455   # Wärmepumpen-Kopf bis Trennfuge (aus Produktfoto geschätzt, beide Größen gleich)
FOOT_MM = 45    # Sockel
VB_H = 2050 * MM  # gemeinsame Höhe, damit beide Größen im selben Maßstab erscheinen


def svg(key: str, m: dict, fill_pct: float | None = 70) -> str:
    w = 600 * MM
    x0 = 20
    h = m["D"] * MM
    y0 = VB_H - h - 4
    head = HEAD_MM * MM
    foot = FOOT_MM * MM
    band_y = y0 + head
    tank_top = band_y + 3
    tank_bot = y0 + h - foot - 3
    tx, tw = x0 + 9, w - 18                      # „Röntgen“-Fenster in den Speicher
    th = tank_bot - tank_top - 6
    ty = tank_top + 3
    cx = x0 + w / 2
    p = []
    p.append(f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 {x0 * 2 + w:.0f} {VB_H:.0f}' "
             f"width='{(x0 * 2 + w) * 2:.0f}' height='{VB_H * 2:.0f}'>")
    p.append("<title>" + m["name"] + " – eigene schematische Darstellung</title>")
    p.append("<defs>"
             "<linearGradient id='body' x1='0' x2='1'>"
             "<stop offset='0' stop-color='#c9ccd0'/><stop offset='.18' stop-color='#f4f5f6'/>"
             "<stop offset='.55' stop-color='#ffffff'/><stop offset='.88' stop-color='#e3e5e8'/>"
             "<stop offset='1' stop-color='#b9bdc2'/></linearGradient>"
             "<linearGradient id='dark' x1='0' x2='1'>"
             "<stop offset='0' stop-color='#1f2226'/><stop offset='.5' stop-color='#3a3e44'/>"
             "<stop offset='1' stop-color='#1b1d20'/></linearGradient>"
             "<linearGradient id='water' x1='0' y1='1' x2='0' y2='0'>"
             "<stop offset='0' stop-color='hsl(60,70%,45%)'/><stop offset='1' stop-color='hsl(120,70%,40%)'/>"
             "</linearGradient>"
             "<linearGradient id='glass' x1='0' x2='1'>"
             "<stop offset='0' stop-color='#000' stop-opacity='.18'/><stop offset='.3' stop-color='#fff' stop-opacity='.10'/>"
             "<stop offset='1' stop-color='#000' stop-opacity='.22'/></linearGradient>"
             f"<clipPath id='win'><rect x='{tx}' y='{ty}' width='{tw}' height='{th}' rx='10'/></clipPath>"
             "</defs>")
    # Luftkanal-Stutzen (Ø 160 mm) oben links
    dw = 160 * MM
    p.append(f"<rect x='{cx - 14 - dw / 2:.1f}' y='{y0 - 4:.1f}' width='{dw:.1f}' height='7' rx='1.5' "
             "fill='#e8eaec' stroke='#a9adb2' stroke-width='.6'/>")
    # Sockel
    p.append(f"<rect x='{x0 + 2}' y='{y0 + h - foot:.1f}' width='{w - 4}' height='{foot:.1f}' rx='3' fill='url(#dark)'/>")
    # Mantel
    p.append(f"<path d='M{x0},{y0 + 8:.1f} Q{x0},{y0:.1f} {x0 + 10},{y0:.1f} H{x0 + w - 10} "
             f"Q{x0 + w},{y0:.1f} {x0 + w},{y0 + 8:.1f} V{y0 + h - foot:.1f} H{x0} Z' fill='url(#body)' "
             "stroke='#9ea3a9' stroke-width='.7'/>")
    # Trennfuge Kopf/Speicher
    p.append(f"<rect x='{x0}' y='{band_y:.1f}' width='{w}' height='2.6' fill='url(#dark)'/>")
    # Bedienfeld
    pw, ph = 21, 61
    py = y0 + 4
    p.append(f"<rect x='{cx - pw / 2:.1f}' y='{py:.1f}' width='{pw}' height='{ph}' rx='1.5' fill='url(#dark)'/>")
    p.append(f"<rect x='{cx - 6:.1f}' y='{py + 26:.1f}' width='12' height='7' rx='.8' fill='#cfe3f2'/>")
    p.append(f"<circle cx='{cx:.1f}' cy='{py + 40:.1f}' r='2.6' fill='none' stroke='#8a9097' stroke-width='.7'/>")
    # Seitlicher Anschluss (Kondensatablauf) an der Fuge links
    p.append(f"<rect x='{x0 - 2.5}' y='{band_y - 3:.1f}' width='4' height='3' rx='.6' fill='#2a2d31'/>")
    # Speicher-Fenster: Wasser + optional Register
    p.append(f"<rect x='{tx}' y='{ty}' width='{tw}' height='{th}' rx='10' fill='#dfe3e7' opacity='.55'/>")
    if fill_pct is not None:
        fy = ty + th * (1 - fill_pct / 100)
        p.append(f"<g clip-path='url(#win)'><rect x='{tx}' y='{fy:.1f}' width='{tw}' height='{ty + th - fy:.1f}' "
                 "fill='url(#water)' opacity='.9'/></g>")
    # Heizstab (beide Varianten): seitlich eingeschraubt, Stopfen am Mantel, etwa Speichermitte
    hy = ty + th * 0.52
    p.append(f"<line x1='{x0 + 3}' y1='{hy:.1f}' x2='{cx + 18:.1f}' y2='{hy:.1f}' stroke='#8d9399' "
             "stroke-width='4.5' stroke-linecap='round'/>")
    p.append(f"<line x1='{x0 + 5}' y1='{hy - 1:.1f}' x2='{cx + 16:.1f}' y2='{hy - 1:.1f}' "
             "stroke='rgba(255,255,255,.45)' stroke-width='1.1' stroke-linecap='round'/>")
    if m["coil"]:
        # Rohrschlange (Solar-/Kessel-Register) im unteren Speicherdrittel
        turns = 6
        c_top = ty + th * 0.60
        c_bot = ty + th - 12
        step = (c_bot - c_top) / turns
        rx = tw / 2 - 9
        g = [f"<g class='coil' clip-path='url(#win)' fill='none' stroke-linecap='round'>"]
        ry = 5.5
        for i in range(turns):
            yy = c_top + step * i
            # Rückseite (oberer Ellipsenbogen, dünn/dunkel), Vorderseite (unterer Bogen, kräftig)
            g.append(f"<path d='M{cx - rx:.1f},{yy:.1f} A{rx:.1f},{ry} 0 0 1 {cx + rx:.1f},{yy + step / 2:.1f}' "
                     "stroke='#8a4b16' stroke-width='1.8' opacity='.5'/>")
            g.append(f"<path d='M{cx + rx:.1f},{yy + step / 2:.1f} A{rx:.1f},{ry} 0 0 1 {cx - rx:.1f},{yy + step:.1f}' "
                     "stroke='#d9792b' stroke-width='2.8'/>")
        # Zu- und Ablauf seitlich hinaus
        g.append(f"<path d='M{cx - rx:.1f},{c_top:.1f} H{tx - 2:.1f}' stroke='#d9792b' stroke-width='2.6'/>")
        g.append(f"<path d='M{cx - rx:.1f},{c_bot:.1f} H{tx - 2:.1f}' stroke='#d9792b' stroke-width='2.6'/>")
        g.append("</g>")
        p.extend(g)
        for yy in (c_top, c_bot):
            p.append(f"<circle cx='{x0 + 1:.1f}' cy='{yy:.1f}' r='2.6' fill='#d9792b' stroke='#7a3f10' stroke-width='.6'/>")
    p.append(f"<rect x='{tx}' y='{ty}' width='{tw}' height='{th}' rx='10' fill='url(#glass)' "
             "stroke='#9ea3a9' stroke-width='.6'/>")
    p.append(f"<rect x='{x0 - 4}' y='{ty + th * 0.52 - 6:.1f}' width='9' height='12' rx='1.8' fill='url(#dark)'/>")
    p.append(f"<rect x='{x0 - 2.5}' y='{ty + th * 0.52 - 3.5:.1f}' width='6' height='7' rx='1' fill='#5f656c'/>")
    # Wasseranschlüsse rechts (Rp 3/4) oben/unten
    for yy in (ty + 10, tank_bot - 10):
        p.append(f"<circle cx='{x0 + w - 1:.1f}' cy='{yy:.1f}' r='2.4' fill='#c3c7cc' stroke='#7f858b' stroke-width='.6'/>")
    p.append("</svg>")
    return "\n".join(p)


def main() -> None:
    out = pathlib.Path(__file__).resolve().parent.parent / "docs" / "images" / "models"
    out.mkdir(parents=True, exist_ok=True)
    for key, m in MODELS.items():
        (out / f"{key}.svg").write_text(svg(key, m), encoding="utf-8")
        print("geschrieben:", out / f"{key}.svg")


if __name__ == "__main__":
    main()
