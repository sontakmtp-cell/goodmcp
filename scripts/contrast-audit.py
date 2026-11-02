"""Contrast audit for apps/web/src/styles.css color pairs (WCAG 2.1)."""

PAIRS = [
    # (label, foreground, background)
    ("Portal: chu cot #f6f9ff", "f6f9ff", "030910"),
    ("Portal: mo ta hero #b8cbe3", "b8cbe3", "030910"),
    ("Portal: goi y URL #b5c7de", "b5c7de", "0c1829"),
    ("Portal: hint huong dan #a8bdd7", "a8bdd7", "0c1829"),
    ("Portal: nut nen tang #d9e5fa", "d9e5fa", "0c1726"),
    ("Portal: buoc huong dan #d4e0ef", "d4e0ef", "0c1829"),
    ("Portal: mo ta catalog #b6c8df", "b6c8df", "030910"),
    ("Portal: mo ta the #b6c8df", "b6c8df", "0b1522"),
    ("Portal: lien ket nav #c4d0e4", "c4d0e4", "030910"),
    ("Portal: footer #8fa4bf", "8fa4bf", "030910"),
    ("Portal: nut dong chuyen dong #a4b7d0", "a4b7d0", "07101b"),
    ("Portal: eyebrow #bed7fb", "bed7fb", "030a14"),
    ("Portal: eyebrow catalog #a3c5fb", "a3c5fb", "030910"),
    ("Portal: lien ket huong dan #a7c6ff", "a7c6ff", "0c1829"),
    ("Portal: empty/pagination #bed0e4", "bed0e4", "030910"),
    ("Portal: url input #d4e4fb", "d4e4fb", "192536"),
    ("Admin: chu cot #172338", "172338", "f5f7fb"),
    ("Admin: muted #5b6a80 tren trang", "5b6a80", "ffffff"),
    ("Admin: muted #5b6a80 tren nen", "5b6a80", "f5f7fb"),
    ("Admin: item p #63738c", "63738c", "ffffff"),
    ("Admin: intro #607088", "607088", "f5f7fb"),
    ("Admin: private-note #667792", "667792", "ffffff"),
    ("Admin: quick-card span #61718a", "61718a", "ffffff"),
    ("Admin: panel p #566780", "566780", "ffffff"),
    ("Admin: badge #395173", "395173", "eff3fb"),
    ("Admin: sidebar-label #5f6f87", "5f6f87", "ffffff"),
    ("Admin: plugin-card p #51627e", "51627e", "fafcff"),
    ("Admin: hash #63728c", "63728c", "ffffff"),
    ("Notice: error #981d30", "981d30", "fff2f3"),
    ("Notice: success #176046", "176046", "eaf8f1"),
    ("Notice: portal error #771b29", "771b29", "fff2f3"),
    ("Admin: link #2448c8", "2448c8", "ffffff"),
    ("Admin: eyebrow #607088", "607088", "f5f7fb"),
]


def lum(hex_color: str) -> float:
    r, g, b = (int(hex_color[i : i + 2], 16) / 255 for i in (0, 2, 4))
    vals = []
    for c in (r, g, b):
        vals.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * vals[0] + 0.7152 * vals[1] + 0.0722 * vals[2]


def ratio(fg: str, bg: str) -> float:
    l1, l2 = lum(fg), lum(bg)
    if l1 < l2:
        l1, l2 = l2, l1
    return (l1 + 0.05) / (l2 + 0.05)


print(f"{'Cap mau':44} {'Ty le':>7}  Danh gia (van thuong 4.5, chu to 3.0)")
print("-" * 100)
fails = []
for label, fg, bg in PAIRS:
    r = ratio(fg, bg)
    ok = "DAT" if r >= 4.5 else ("chu to OK" if r >= 3 else "KHONG DAT")
    if r < 4.5:
        fails.append((label, fg, bg, r))
    print(f"{label:44} {r:6.2f}:1  {ok}")

print()
if fails:
    print(f"{len(fails)} cap can sua (duoi 4.5:1 cho van thuong):")
    for label, fg, bg, r in fails:
        print(f"  - {label} (#{fg} / #{bg}): {r:.2f}:1")
else:
    print("Tat ca cap mau dat 4.5:1.")
