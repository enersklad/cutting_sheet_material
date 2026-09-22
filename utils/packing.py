import random
from utils.models import PlacedPart, Sheet, FreeRect


# ============================================================
#  ГИЛЬОТИННЫЙ РАСКРОЙ
# ============================================================

def find_best_fit(free_rects, w, h, allow_rotation=True):
    candidates = []
    for idx, rect in enumerate(free_rects):
        if rect.w >= w and rect.h >= h:
            leftover = (rect.w - w) * (rect.h - h)
            penalty = 0
            if rect.w - w < 100:
                penalty += 10000
            if rect.h - h < 100:
                penalty += 10000
            candidates.append((leftover + penalty, idx, (w, h, False)))

        if allow_rotation and rect.w >= h and rect.h >= w:
            leftover = (rect.w - h) * (rect.h - w)
            penalty = 0
            if rect.w - h < 100:
                penalty += 10000
            if rect.h - w < 100:
                penalty += 10000
            candidates.append((leftover + penalty, idx, (h, w, True)))

    if not candidates:
        return None
    candidates.sort(key=lambda c: c[0])
    _, idx, dims = candidates[0]
    return idx, dims


def split_guillotine(rect, pw, ph, kerf):
    x, y, w, h = rect.x, rect.y, rect.w, rect.h
    pw_kerf = pw + kerf
    ph_kerf = ph + kerf
    right_w = w - pw_kerf
    bottom_h = h - ph_kerf
    rects = []

    if right_w > 0 and bottom_h > 0:
        area_a_max = right_w * h
        area_b_max = w * bottom_h

        if right_w < 100 and bottom_h >= 100:
            rects.append(FreeRect(x, y + ph_kerf, w, bottom_h))
        elif bottom_h < 100 and right_w >= 100:
            rects.append(FreeRect(x + pw_kerf, y, right_w, h))
        else:
            if area_a_max >= area_b_max:
                rects.append(FreeRect(x + pw_kerf, y, right_w, h))
                rects.append(FreeRect(x, y + ph_kerf, pw, bottom_h))
            else:
                rects.append(FreeRect(x, y + ph_kerf, w, bottom_h))
                rects.append(FreeRect(x + pw_kerf, y, right_w, ph))
    elif right_w > 0:
        rects.append(FreeRect(x + pw_kerf, y, right_w, h))
    elif bottom_h > 0:
        rects.append(FreeRect(x, y + ph_kerf, w, bottom_h))

    return rects


def pack_parts_single(parts_flat, sheet_w, sheet_h, kerf, allow_rotation=True):
    sheets = []
    remaining = list(parts_flat)

    while remaining:
        sheet = Sheet(sheet_w, sheet_h)
        free_rects = [FreeRect(0, 0, sheet_w, sheet_h)]
        placed_any = False
        i = 0
        while i < len(remaining):
            name, w, h = remaining[i]
            best = find_best_fit(free_rects, w, h, allow_rotation)
            if best is None:
                i += 1
                continue
            rect_idx, (pw, ph, rotated) = best
            rect = free_rects.pop(rect_idx)
            sheet.placed.append(PlacedPart(name, rect.x, rect.y, pw, ph, rotated))
            new_rects = split_guillotine(rect, pw, ph, kerf)
            free_rects.extend(new_rects)
            remaining.pop(i)
            placed_any = True
        sheets.append(sheet)
        if not placed_any:
            break
    return sheets


def pack_parts(parts, sheet_w, sheet_h, kerf, allow_rotation=True,
               multi_start=True):
    flat = []
    for p in parts:
        for _ in range(p.qty):
            flat.append((p.name, p.w, p.h))
    if not flat:
        return []

    oversized = []
    valid = []
    for item in flat:
        name, w, h = item
        fits = False
        if w <= sheet_w and h <= sheet_h:
            fits = True
        elif allow_rotation and h <= sheet_w and w <= sheet_h:
            fits = True
        if fits:
            valid.append(item)
        else:
            oversized.append(item)

    if oversized:
        print("Детали, не помещающиеся в лист:")
        for name, w, h in oversized:
            print(f"  {name}: {w}×{h}")
    if not valid:
        return []

    if not multi_start:
        strategies = [("площадь", lambda x: (x[1] * x[2], max(x[1], x[2])), True)]
    else:
        strategies = [
            ("площадь",       lambda x: (x[1] * x[2], max(x[1], x[2])), True),
            ("макс. сторона", lambda x: (max(x[1], x[2]), x[1] * x[2]), True),
            ("периметр",      lambda x: (x[1] + x[2], x[1] * x[2]), True),
            ("мин. сторона",  lambda x: (min(x[1], x[2]), x[1] * x[2]), True),
            ("ширина",        lambda x: (x[1], x[2]), True),
            ("высота",        lambda x: (x[2], x[1]), True),
        ]

    best_sheets = None
    best_score = None
    best_name = ""

    for name, key_func, rev in strategies:
        sorted_flat = sorted(valid, key=key_func, reverse=rev)
        sheets = pack_parts_single(sorted_flat, sheet_w, sheet_h, kerf,
                                    allow_rotation)
        avg_fill = sum(s.fill_percent for s in sheets) / len(sheets) if sheets else 0
        score = (len(sheets), -avg_fill)
        if best_score is None or score < best_score:
            best_score = score
            best_sheets = sheets
            best_name = name

    if multi_start:
        base_sorted = sorted(valid,
                             key=lambda x: (x[1] * x[2], max(x[1], x[2])),
                             reverse=True)
        for trial in range(8):
            shuffled = base_sorted.copy()
            n = max(1, len(shuffled) // 3)
            for _ in range(n):
                i = random.randint(0, min(len(shuffled) - 1, n))
                j = random.randint(0, min(len(shuffled) - 1, n))
                shuffled[i], shuffled[j] = shuffled[j], shuffled[i]
            sheets = pack_parts_single(shuffled, sheet_w, sheet_h, kerf,
                                        allow_rotation)
            avg_fill = sum(s.fill_percent for s in sheets) / len(sheets) if sheets else 0
            score = (len(sheets), -avg_fill)
            if score < best_score:
                best_score = score
                best_sheets = sheets
                best_name = f"случайный #{trial+1}"

    print(f"Лучшая стратегия: {best_name}, "
          f"листов: {len(best_sheets)}, "
          f"среднее заполнение: {-best_score[1]:.1f}%")
    return best_sheets
