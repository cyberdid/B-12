"""Render docs/images/feature-effects.svg: passes out of 6 without / with each runtime feature.

Numbers are from reports/unified/FRONTIER_RECALL_2026-11-23.md (sections 5, 7, 7a) and
reports/unified/SKILLS_LEARN_2026-11-24.md. Two series in the documented dataviz palette
(slot 1 blue = feature on, slot 2 orange = without), direct value labels, one axis per panel.

    python docs/images/make_feature_chart.py && \
      google-chrome --headless=new --screenshot=docs/images/feature-effects.png \
        --window-size=1200,620 docs/images/feature-effects.svg
"""

from pathlib import Path

ON, OFF = "#2a78d6", "#eb6834"
INK, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#e1e0d9", "#fcfcfb"

PANELS = [
    (
        "gpt-6-luna (frontier)",
        [
            ("Пам'ять: свіжий факт (M103)", 3, 6),
            ("Наміри власника (M107)", 0, 6),
            ("Навички: читання (M108)", 0, 6),
            ("Розбір навичок: нова (M115)", 0, 6),
            ("Розбір навичок: оновлення (M116)", 0, 5),
        ],
    ),
    (
        "gemma4:12b (локально)",
        [
            ("Минулі розмови (M100)", 0, 6),
            ("Минулі розмови (M101)", 0, 6),
            ("Наміри власника (M107)", 0, 6),
            ("Навички: читання (M108)", 0, 6),
        ],
    ),
]


def svg() -> str:
    width, row, top, label_w, bar_w = 1180, 46, 92, 330, 200
    height = top + max(len(p[1]) for p in PANELS) * row + 60
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'font-family="DejaVu Sans, sans-serif">',
        f'<rect width="100%" height="100%" fill="{SURFACE}"/>',
        f'<text x="24" y="34" font-size="20" font-weight="bold" fill="{INK}">'
        "Що дають функції рантайму: правильних відповідей із 6</text>",
        f'<rect x="24" y="50" width="14" height="14" rx="3" fill="{OFF}"/>'
        f'<text x="44" y="62" font-size="14" fill="{MUTED}">без функції</text>'
        f'<rect x="150" y="50" width="14" height="14" rx="3" fill="{ON}"/>'
        f'<text x="170" y="62" font-size="14" fill="{MUTED}">з функцією</text>',
    ]
    panel_w = (width - 48) // 2
    for index, (title, rows) in enumerate(PANELS):
        x0 = 24 + index * panel_w
        out.append(
            f'<text x="{x0}" y="{top - 10}" font-size="15" font-weight="bold" fill="{INK}">'
            f"{title}</text>"
        )
        scale = bar_w / 6
        bx = x0 + label_w
        for tick in (0, 3, 6):
            gx = bx + tick * scale
            out.append(
                f'<line x1="{gx}" y1="{top}" x2="{gx}" y2="{top + len(rows) * row}" '
                f'stroke="{GRID}" stroke-width="1"/>'
                f'<text x="{gx}" y="{top + len(rows) * row + 16}" font-size="11" '
                f'fill="{MUTED}" text-anchor="middle">{tick}</text>'
            )
        for r, (label, off, on) in enumerate(rows):
            y = top + r * row
            out.append(
                f'<text x="{x0}" y="{y + 26}" font-size="13" fill="{INK}">{label}</text>'
            )
            for k, (value, color) in enumerate(((off, OFF), (on, ON))):
                by = y + 8 + k * 16
                w = max(value * scale, 2)
                out.append(
                    f'<rect x="{bx}" y="{by}" width="{w}" height="13" rx="3" fill="{color}"/>'
                    f'<text x="{bx + w + 6}" y="{by + 11}" font-size="12" fill="{MUTED}">'
                    f"{value}</text>"
                )
    out.append(
        f'<text x="24" y="{height - 16}" font-size="11" fill="{MUTED}">'
        "3 повтори × 2 варіанти питання; судді Gemini + Opus (luna) або Codex + Gemini (gemma). "
        "Розбір навичок на gemma — у звіті SKILLS_LEARN.</text>"
    )
    out.append("</svg>")
    return "\n".join(out)


if __name__ == "__main__":
    target = Path(__file__).with_name("feature-effects.svg")
    target.write_text(svg(), encoding="utf-8")
    print(target)
