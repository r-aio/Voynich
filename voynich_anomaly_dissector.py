#!/usr/bin/env python3
"""
Voynich Manuscript (MS 408) — Surgical Anomaly Dissector (ZL3b-n.txt & RF1b-e.txt)
Zero external dependencies (Python 3.11 stdlib only). No L0-ISM / No semantic labels.

Dissects the 3 strongest non-trivial signals isolated by Deep Probes 1-4:
  DISSECT 1: Cross-Space Coupling Anatomy (End(i) -> Start(i+lag))
             - Exact per-pair MI contribution, O/E ratios (top attractors & repulsors),
               concentration in top-5 pairs, lag-1..3 decay, long-token isolation,
               Currier A/B stratification, and ZL3b-n vs. RF1b-e parity.
  DISSECT 2: 2D Vertical Alignment Dissection (Line k-d above Line k, Interior Only)
             - Vertical lag decay (k-1, k-2, k-3, k-4) vs. Ctrl A (within-line shuffle)
               & Ctrl B (line-order shuffle).
             - Exact horizontal column offset profile (offset -2, -1, 0, +1, +2).
             - Stratification by Scribe ($H) and Currier style ($L).
  DISSECT 3: Length-Burst Dissection (Detrended r=+0.1548, Z=+27)
             - Lag-1..4 autocorrelation decay of (pos + folio) detrended length residuals.
             - Fragmentation / short-token ablation (excluding len<=2 and len<=3 tokens)
               with exact matched full-line shuffle geometry.
             - Short-Short (<=3 -> <=3) vs. Long-Long (>=6 -> >=6) enrichment.
"""

from __future__ import annotations

import math
import random
import re
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass
class LineEntry:
    folio: str
    line_id: str
    line_idx_in_folio: int
    quire: str
    section: str
    currier: str
    scribe: str
    tokens: List[str]


TOKEN_CLEAN_RE = re.compile(r"[^a-zA-Z0-9]+")
FOLIO_HEADER_RE = re.compile(r"^#?\s*<(f[0-9]+[rv][0-9]*|fRos)>\s*<!(.*?)>", re.IGNORECASE)
LOCUS_RE = re.compile(r"^<(f[0-9]+[rv][0-9]*|fRos)\.([^>\s]+)>\s*(.*)$", re.IGNORECASE)


def tokenize_ivtff_body(body: str) -> List[str]:
    s = re.sub(r"#.*$", "", body)
    s = re.sub(r"<[^>]*>", " ", s)
    s = re.sub(r"\{[^}]*\}", " ", s)
    s = re.sub(r"\[[^\]]*\]", " ", s)
    s = s.replace("!", " ").replace("*", " ").replace("?", " ")
    raw_parts = re.split(r"[.,\s;]+", s)
    out: List[str] = []
    for part in raw_parts:
        cleaned = TOKEN_CLEAN_RE.sub("", part).lower()
        if cleaned:
            out.append(cleaned)
    return out


def parse_ivtff(filepath: str) -> List[LineEntry]:
    folio_meta: Dict[str, Dict[str, str]] = {}
    line_counts: Dict[str, int] = defaultdict(int)
    entries: List[LineEntry] = []

    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue

            hm = FOLIO_HEADER_RE.match(line)
            if hm:
                fid = hm.group(1).lower()
                meta = hm.group(2)
                q_m = re.search(r"\$Q=([A-Z0-9]+)", meta)
                i_m = re.search(r"\$I=([A-Z])", meta)
                l_m = re.search(r"\$L=([A-Z])", meta)
                h_m = re.search(r"\$H=([A-Z0-9]+)", meta)
                folio_meta[fid] = {
                    "quire": q_m.group(1) if q_m else "?",
                    "section": i_m.group(1) if i_m else "?",
                    "currier": l_m.group(1) if l_m else "?",
                    "scribe": h_m.group(1) if h_m else "?",
                }
                continue

            lm = LOCUS_RE.match(line)
            if not lm:
                continue

            fid = lm.group(1).lower()
            loc_id = lm.group(2).strip()
            body = lm.group(3)

            fmeta = folio_meta.get(fid, {})
            quire = fmeta.get("quire", "?")
            section = fmeta.get("section", "?")
            currier = fmeta.get("currier", "?")
            scribe = fmeta.get("scribe", "?")

            q_ov = re.search(r"\$Q=([A-Z0-9]+)", body)
            if q_ov:
                quire = q_ov.group(1)
            i_ov = re.search(r"\$I=([A-Z])", body)
            if i_ov:
                section = i_ov.group(1)
            l_ov = re.search(r"\$L=([A-Z])", body)
            if l_ov:
                currier = l_ov.group(1)
            h_ov = re.search(r"\$H=([A-Z0-9]+)", body)
            if h_ov:
                scribe = h_ov.group(1)

            toks = tokenize_ivtff_body(body)
            if not toks:
                continue

            idx = line_counts[fid]
            line_counts[fid] += 1
            entries.append(
                LineEntry(
                    folio=fid,
                    line_id=f"{fid}.{loc_id}",
                    line_idx_in_folio=idx,
                    quire=quire,
                    section=section,
                    currier=currier,
                    scribe=scribe,
                    tokens=toks,
                )
            )

    return entries


def is_edit_le_1(a: str, b: str) -> bool:
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if la == lb:
        return sum(1 for x, y in zip(a, b) if x != y) <= 1
    if la > lb:
        a, b = b, a
        la, lb = lb, la
    i = j = diffs = 0
    while i < la and j < lb:
        if a[i] == b[j]:
            i += 1
            j += 1
        else:
            diffs += 1
            if diffs > 1:
                return False
            j += 1
    return True


def pearson_corr(xs: List[float], ys: List[float]) -> float:
    n = len(xs)
    if n < 2:
        return 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    num = 0.0
    dx2 = 0.0
    dy2 = 0.0
    for x, y in zip(xs, ys):
        dx = x - mx
        dy = y - my
        num += dx * dy
        dx2 += dx * dx
        dy2 += dy * dy
    den = math.sqrt(dx2 * dy2)
    return (num / den) if den > 1e-12 else 0.0


def z_score(obs: float, nulls: List[float]) -> Tuple[float, float, float]:
    m = statistics.mean(nulls) if nulls else 0.0
    sd = statistics.stdev(nulls) if len(nulls) > 1 else 0.0
    z = ((obs - m) / sd) if sd > 1e-12 else 0.0
    return m, sd, z


def mutual_info_details(pairs: List[Tuple[str, str]]) -> Tuple[float, List[Tuple[str, str, int, float, float, float]]]:
    """
    Returns (total_MI_bits, details) where each detail tuple is:
      (x, y, obs_count, exp_count, oe_ratio, mi_contrib_bits)
    """
    n = len(pairs)
    if n == 0:
        return 0.0, []
    cx: Counter = Counter()
    cy: Counter = Counter()
    cxy: Counter = Counter()
    for x, y in pairs:
        cx[x] += 1
        cy[y] += 1
        cxy[(x, y)] += 1

    total_mi = 0.0
    details: List[Tuple[str, str, int, float, float, float]] = []
    for (x, y), obs in cxy.items():
        exp = (cx[x] * cy[y]) / n
        pxy = obs / n
        oe = obs / exp if exp > 0 else 0.0
        contrib = pxy * math.log2(oe) if oe > 0 else 0.0
        total_mi += contrib
        details.append((x, y, obs, exp, oe, contrib))

    return max(0.0, total_mi), details


def dissect1_cross_space_anatomy(zl_entries: List[LineEntry], rf_entries: List[LineEntry]) -> None:
    print("=== DISSECT 1: CROSS-SPACE COUPLING ANATOMY (END(i) -> START(i+lag)) ===")

    def get_lag_pairs(entries: List[LineEntry], lag: int) -> List[Tuple[str, str]]:
        pairs: List[Tuple[str, str]] = []
        for e in entries:
            toks = e.tokens
            for i in range(len(toks) - lag):
                pairs.append((toks[i][-1], toks[i + lag][0]))
        return pairs

    # 1A. Lag-1 vs. Lag-2 vs. Lag-3 within lines + within-line shuffle null
    rng = random.Random(408)
    print("  Within-Line Cross-Space 1-Char MI by Token Lag (ZL3b-n):")
    for lag in (1, 2, 3):
        obs_pairs = get_lag_pairs(zl_entries, lag)
        obs_mi, _ = mutual_info_details(obs_pairs)
        null_mis: List[float] = []
        for _ in range(10):
            sh_pairs: List[Tuple[str, str]] = []
            for e in zl_entries:
                if len(e.tokens) > lag:
                    cp = e.tokens[:]
                    rng.shuffle(cp)
                    for i in range(len(cp) - lag):
                        sh_pairs.append((cp[i][-1], cp[i + lag][0]))
            null_mis.append(mutual_info_details(sh_pairs)[0])
        m_n, sd_n, z_n = z_score(obs_mi, null_mis)
        print(
            f"    Lag={lag} (n={len(obs_pairs):5d}) : MI = {obs_mi:.4f} bits | "
            f"LineShuf = {m_n:.4f} (SD={sd_n:.4f}) | Lift = {obs_mi - m_n:+.4f} bits | Z = {z_n:+.2f}"
        )

    # 1B. Exact pair breakdown for Lag-1 (ZL3b-n)
    lag1_pairs = get_lag_pairs(zl_entries, 1)
    total_mi, details = mutual_info_details(lag1_pairs)
    n_lag1 = len(lag1_pairs)

    attractors = sorted([d for d in details if d[5] > 0], key=lambda d: d[5], reverse=True)

    cx = Counter(x for x, _ in lag1_pairs)
    cy = Counter(y for _, y in lag1_pairs)
    cxy = Counter(lag1_pairs)
    repulsors: List[Tuple[str, str, int, float, float, float]] = []
    for x, nx in cx.items():
        for y, ny in cy.items():
            exp = (nx * ny) / n_lag1
            if exp >= 30.0:
                obs = cxy.get((x, y), 0)
                oe = obs / exp
                if oe < 0.75:
                    deficit = obs - exp
                    repulsors.append((x, y, obs, exp, oe, deficit))
    repulsors.sort(key=lambda r: r[5])

    top5_pos_bits = sum(d[5] for d in attractors[:5])
    top10_pos_bits = sum(d[5] for d in attractors[:10])
    sum_all_pos = sum(d[5] for d in attractors)

    print(f"\n  Lag-1 Total MI (ZL3b-n) = {total_mi:.4f} bits (Sum of positive terms = {sum_all_pos:.4f} bits)")
    if sum_all_pos > 0:
        print(
            f"  Concentration: Top-5 positive pairs = {top5_pos_bits:.4f} bits ({top5_pos_bits/sum_all_pos*100:.1f}% of pos MI) | "
            f"Top-10 = {top10_pos_bits:.4f} bits ({top10_pos_bits/sum_all_pos*100:.1f}%)"
        )

    print("\n  Top 15 Cross-Space ATTRACTORS (LastChar(i) -> FirstChar(i+1), ZL3b-n):")
    print("    Pair   |   Obs |    Exp |   O/E  | MI_Bits")
    print("    -------------------------------------------")
    for x, y, obs, exp, oe, bits in attractors[:15]:
        print(f"    {x} -> {y} | {obs:5d} | {exp:6.1f} | {oe:5.2f}x | {bits:+.5f}")

    print("\n  Top 12 Cross-Space REPULSORS / AVOIDED BOUNDARIES (Exp >= 30, ZL3b-n):")
    print("    Pair   |   Obs |    Exp |   O/E  | Deficit")
    print("    -------------------------------------------")
    for x, y, obs, exp, oe, deficit in repulsors[:12]:
        print(f"    {x} -> {y} | {obs:5d} | {exp:6.1f} | {oe:5.2f}x | {deficit:+7.1f}")

    # 1C. Currier A vs. Currier B & Long-Token Only (exact matched full-line shuffle geometry)
    print("\n  Stratified Lag-1 Cross-Space MI (ZL3b-n):")
    for label, subset in [
        ("Currier A only", [e for e in zl_entries if e.currier == "A"]),
        ("Currier B only", [e for e in zl_entries if e.currier == "B"]),
        ("Long Tokens Only (both len >= 4)", None),
    ]:
        if subset is not None:
            ps = get_lag_pairs(subset, 1)
            mi_s, _ = mutual_info_details(ps)
            n_sh: List[float] = []
            for _ in range(8):
                sp = []
                for e in subset:
                    if len(e.tokens) >= 2:
                        cp = e.tokens[:]
                        rng.shuffle(cp)
                        for i in range(len(cp) - 1):
                            sp.append((cp[i][-1], cp[i + 1][0]))
                n_sh.append(mutual_info_details(sp)[0])
            mn, _, zn = z_score(mi_s, n_sh)
            print(f"    {label:<34} (n={len(ps):5d}) : MI={mi_s:.4f} | Shuf={mn:.4f} | Lift={mi_s-mn:+.4f} | Z={zn:+.1f}")
        else:
            ps = []
            for e in zl_entries:
                toks = e.tokens
                for i in range(len(toks) - 1):
                    if len(toks[i]) >= 4 and len(toks[i + 1]) >= 4:
                        ps.append((toks[i][-1], toks[i + 1][0]))
            mi_s, _ = mutual_info_details(ps)
            n_sh = []
            for _ in range(8):
                sp = []
                for e in zl_entries:
                    if len(e.tokens) >= 2:
                        cp = e.tokens[:]
                        rng.shuffle(cp)
                        for i in range(len(cp) - 1):
                            if len(cp[i]) >= 4 and len(cp[i + 1]) >= 4:
                                sp.append((cp[i][-1], cp[i + 1][0]))
                n_sh.append(mutual_info_details(sp)[0])
            mn, _, zn = z_score(mi_s, n_sh)
            print(f"    {label:<34} (n={len(ps):5d}) : MI={mi_s:.4f} | Shuf={mn:.4f} | Lift={mi_s-mn:+.4f} | Z={zn:+.1f}")

    # 1D. Independent Transcription Parity Check (RF1b-e.txt)
    if rf_entries:
        rf_pairs = get_lag_pairs(rf_entries, 1)
        rf_mi, rf_det = mutual_info_details(rf_pairs)
        rf_attr = sorted([d for d in rf_det if d[5] > 0], key=lambda d: d[5], reverse=True)
        rf_null: List[float] = []
        for _ in range(8):
            sp = []
            for e in rf_entries:
                if len(e.tokens) >= 2:
                    cp = e.tokens[:]
                    rng.shuffle(cp)
                    for i in range(len(cp) - 1):
                        sp.append((cp[i][-1], cp[i + 1][0]))
            rf_null.append(mutual_info_details(sp)[0])
        rmn, _, rzn = z_score(rf_mi, rf_null)
        top5_str = ", ".join(f"{x}->{y}({oe:.2f}x)" for x, y, _, _, oe, _ in rf_attr[:5])
        print(
            f"\n  Cross-Transcription Parity (RF1b-e, n={len(rf_pairs):5d}) : MI={rf_mi:.4f} | "
            f"Shuf={rmn:.4f} | Lift={rf_mi-rmn:+.4f} bits | Z={rzn:+.1f}"
        )
        print(f"    RF1b-e Top-5 Attractors: {top5_str}")
    print()


def dissect2_vertical_alignment(entries: List[LineEntry]) -> None:
    print("=== DISSECT 2: 2D VERTICAL ALIGNMENT (LAG DECAY, OFFSET PROFILE & SCRIBES) ===")

    by_folio_lines: Dict[str, List[List[str]]] = defaultdict(list)
    by_scribe_folio: Dict[str, Dict[str, List[List[str]]]] = defaultdict(lambda: defaultdict(list))
    by_currier_folio: Dict[str, Dict[str, List[List[str]]]] = defaultdict(lambda: defaultdict(list))

    for e in entries:
        if len(e.tokens) >= 3:
            by_folio_lines[e.folio].append(e.tokens)
            by_scribe_folio[e.scribe][e.folio].append(e.tokens)
            cur = e.currier if e.currier in ("A", "B") else "OTHER"
            by_currier_folio[cur][e.folio].append(e.tokens)

    def vertical_lag_rates(
        lines_map: Dict[str, List[List[str]]], lag: int = 1, radius: int = 1
    ) -> Tuple[float, float, int]:
        """Interior-only (excluding line-init and line-final) match against line (li - lag)."""
        ex_hits = e1_hits = tot = 0
        for lines in lines_map.values():
            for li in range(lag, len(lines)):
                prev = lines[li - lag]
                curr = lines[li]
                lp, lc = len(prev), len(curr)
                for i in range(1, lc - 1):
                    tok = curr[i]
                    proj = round(i * (lp - 1) / (lc - 1)) if lc > 1 else 0
                    lo = max(0, proj - radius)
                    hi = min(lp, proj + radius + 1)
                    has_ex = False
                    has_e1 = False
                    for j in range(lo, hi):
                        other = prev[j]
                        if other == tok:
                            has_ex = True
                            has_e1 = True
                            break
                        if not has_e1 and is_edit_le_1(tok, other):
                            has_e1 = True
                    tot += 1
                    if has_ex:
                        ex_hits += 1
                    if has_e1:
                        e1_hits += 1
        return (ex_hits / tot * 100.0 if tot else 0.0), (e1_hits / tot * 100.0 if tot else 0.0), tot

    rng = random.Random(2026)

    # 2A. Vertical Lag Decay: k-1, k-2, k-3, k-4 (Interior Only, Col +/-1)
    print("  [2A. Vertical Lag Decay (Interior Only, Col +/-1) vs. Within-Line Shuffle (Ctrl A)]")
    print("    Lag  |     N | ObsExact (CtrlA,  Z   ) | ObsEdit1 (CtrlA,  Z   ) | LineOrdShuf Edit1 (Z)")
    print("    -----------------------------------------------------------------------------------------")
    for lag in (1, 2, 3, 4):
        obs_ex, obs_e1, n_t = vertical_lag_rates(by_folio_lines, lag=lag, radius=1)
        a_ex, a_e1 = [], []
        b_e1 = []
        for _ in range(12):
            map_a = {
                f: [rng.sample(ln, len(ln)) for ln in lines]
                for f, lines in by_folio_lines.items()
            }
            ea, e1a, _ = vertical_lag_rates(map_a, lag=lag, radius=1)
            a_ex.append(ea)
            a_e1.append(e1a)

            map_b = {
                f: rng.sample(lines, len(lines))
                for f, lines in by_folio_lines.items()
            }
            _, e1b, _ = vertical_lag_rates(map_b, lag=lag, radius=1)
            b_e1.append(e1b)

        ma_ex, _, za_ex = z_score(obs_ex, a_ex)
        ma_e1, _, za_e1 = z_score(obs_e1, a_e1)
        mb_e1, _, zb_e1 = z_score(obs_e1, b_e1)
        print(
            f"    k-{lag}  | {n_t:5d} | {obs_ex:5.2f}% ({ma_ex:5.2f}%, {za_ex:+5.2f}) | "
            f"{obs_e1:5.2f}% ({ma_e1:5.2f}%, {za_e1:+5.2f}) | {mb_e1:5.2f}% ({zb_e1:+5.2f})"
        )

    # 2B. Exact Single-Column Offset Profile on Line k-1 (offset = -2, -1, 0, +1, +2)
    print("\n  [2B. Horizontal Offset Profile on Line k-1 (Interior Only, Exact Single-Slot Hit)]")
    print("    Offset |     N | ObsExact (CtrlA,  Z   ) | ObsEdit1 (CtrlA,  Z   )")
    print("    -------------------------------------------------------------------")
    for offset in (-2, -1, 0, 1, 2):
        def offset_rate(lines_map: Dict[str, List[List[str]]]) -> Tuple[float, float, int]:
            ex = e1 = tot = 0
            for lines in lines_map.values():
                for li in range(1, len(lines)):
                    prev = lines[li - 1]
                    curr = lines[li]
                    lp, lc = len(prev), len(curr)
                    for i in range(1, lc - 1):
                        proj = round(i * (lp - 1) / (lc - 1)) if lc > 1 else 0
                        j = proj + offset
                        if 0 <= j < lp:
                            tok = curr[i]
                            other = prev[j]
                            tot += 1
                            if other == tok:
                                ex += 1
                                e1 += 1
                            elif is_edit_le_1(tok, other):
                                e1 += 1
            return (ex / tot * 100.0 if tot else 0.0), (e1 / tot * 100.0 if tot else 0.0), tot

        o_ex, o_e1, nt = offset_rate(by_folio_lines)
        c_ex, c_e1 = [], []
        for _ in range(12):
            map_a = {
                f: [rng.sample(ln, len(ln)) for ln in lines]
                for f, lines in by_folio_lines.items()
            }
            ea, e1a, _ = offset_rate(map_a)
            c_ex.append(ea)
            c_e1.append(e1a)
        mx, _, zx = z_score(o_ex, c_ex)
        me, _, ze = z_score(o_e1, c_e1)
        print(
            f"    {offset:+3d}    | {nt:5d} | {o_ex:5.2f}% ({mx:5.2f}%, {zx:+5.2f}) | "
            f"{o_e1:5.2f}% ({me:5.2f}%, {ze:+5.2f})"
        )

    # 2C. Stratified by Scribe ($H) and Currier ($L) on Line k-1 (Interior Only, Col +/-1)
    print("\n  [2C. Line k-1 Vertical Alignment Stratified by Scribe ($H) & Currier ($L)]")
    print("    Group       |     N | ObsExact (CtrlA,  Z   ) | ObsEdit1 (CtrlA,  Z   )")
    print("    ------------------------------------------------------------------------")
    groups: List[Tuple[str, Dict[str, List[List[str]]]]] = []
    for h in sorted(by_scribe_folio.keys()):
        groups.append((f"Scribe $H={h}", by_scribe_folio[h]))
    for c in ("A", "B", "OTHER"):
        if c in by_currier_folio:
            groups.append((f"Currier {c}", by_currier_folio[c]))

    for gname, gmap in groups:
        o_ex, o_e1, nt = vertical_lag_rates(gmap, lag=1, radius=1)
        if nt < 100:
            continue
        c_ex, c_e1 = [], []
        for _ in range(15):
            map_a = {
                f: [rng.sample(ln, len(ln)) for ln in lines]
                for f, lines in gmap.items()
            }
            ea, e1a, _ = vertical_lag_rates(map_a, lag=1, radius=1)
            c_ex.append(ea)
            c_e1.append(e1a)
        mx, _, zx = z_score(o_ex, c_ex)
        me, _, ze = z_score(o_e1, c_e1)
        print(
            f"    {gname:<11} | {nt:5d} | {o_ex:5.2f}% ({mx:5.2f}%, {zx:+5.2f}) | "
            f"{o_e1:5.2f}% ({me:5.2f}%, {ze:+5.2f})"
        )
    print()


def dissect3_length_burst_mechanism(entries: List[LineEntry]) -> None:
    print("=== DISSECT 3: LENGTH-BURST MECHANISM (LAG DECAY & SHORT-TOKEN ABLATION) ===")

    def pos_bucket(idx: int, length: int) -> str:
        if length <= 1:
            return "SINGLE"
        if idx == 0:
            return "INIT"
        if idx == length - 1:
            return "FINAL"
        rel = idx / (length - 1)
        b = min(4, int(rel * 5))
        return f"MID_{b}"

    bucket_lens: Dict[Tuple[str, str], List[int]] = defaultdict(list)
    folio_lens: Dict[str, List[int]] = defaultdict(list)
    for e in entries:
        cur = e.currier if e.currier in ("A", "B") else "OTHER"
        n = len(e.tokens)
        for i, t in enumerate(e.tokens):
            bucket_lens[(cur, pos_bucket(i, n))].append(len(t))
            folio_lens[e.folio].append(len(t))

    bucket_mean = {k: statistics.mean(v) for k, v in bucket_lens.items()}
    folio_mean = {k: statistics.mean(v) for k, v in folio_lens.items()}
    global_mean = statistics.mean(len(t) for e in entries for t in e.tokens)

    res_lines: List[List[Tuple[int, float]]] = []
    for e in entries:
        cur = e.currier if e.currier in ("A", "B") else "OTHER"
        n = len(e.tokens)
        if n < 2:
            continue
        f_shift = folio_mean[e.folio] - global_mean
        row = [
            (len(t), len(t) - bucket_mean[(cur, pos_bucket(i, n))] - f_shift)
            for i, t in enumerate(e.tokens)
        ]
        res_lines.append(row)

    rng = random.Random(408)

    # 3A. Multi-lag decay of detrended length autocorrelation (lag 1..4)
    print("  [3A. Within-Line Detrended Length Autocorrelation by Lag (Pos + Folio Detrended)]")
    for lag in (1, 2, 3, 4):
        xs, ys = [], []
        for row in res_lines:
            for i in range(len(row) - lag):
                xs.append(row[i][1])
                ys.append(row[i + lag][1])
        r_obs = pearson_corr(xs, ys)
        null_r: List[float] = []
        for _ in range(12):
            nx, ny = [], []
            for row in res_lines:
                if len(row) > lag:
                    cp = [val for _, val in row]
                    rng.shuffle(cp)
                    for i in range(len(cp) - lag):
                        nx.append(cp[i])
                        ny.append(cp[i + lag])
            null_r.append(pearson_corr(nx, ny))
        mn, sdn, zn = z_score(r_obs, null_r)
        print(
            f"    Lag={lag} (n={len(xs):5d}) : r = {r_obs:+.4f} | "
            f"ResShuf = {mn:+.4f} (SD={sdn:.4f}, Z={zn:+.2f})"
        )

    # 3B. Short-Token Ablation (exact matched full-line shuffle geometry)
    print("\n  [3B. Short-Token Ablation (Lag-1 Detrended r After Excluding Short Tokens)]")
    for min_len, desc in [
        (1, "All tokens (baseline, min_len >= 1)"),
        (3, "Exclude len<=2 fragments (min_len >= 3)"),
        (4, "Exclude len<=3 short tokens (min_len >= 4)"),
        (5, "Long tokens only (min_len >= 5)"),
    ]:
        xs, ys = [], []
        for row in res_lines:
            for i in range(len(row) - 1):
                if row[i][0] >= min_len and row[i + 1][0] >= min_len:
                    xs.append(row[i][1])
                    ys.append(row[i + 1][1])

        r_obs = pearson_corr(xs, ys)
        null_r = []
        for _ in range(12):
            nx, ny = [], []
            for row in res_lines:
                cp = row[:]
                rng.shuffle(cp)
                for i in range(len(cp) - 1):
                    if cp[i][0] >= min_len and cp[i + 1][0] >= min_len:
                        nx.append(cp[i][1])
                        ny.append(cp[i + 1][1])
            null_r.append(pearson_corr(nx, ny))
        mn, _, zn = z_score(r_obs, null_r)
        print(
            f"    {desc:<44} (n={len(xs):5d}) : r = {r_obs:+.4f} | "
            f"FullLineShuf = {mn:+.4f} (Z={zn:+.2f})"
        )

    # 3C. Short-Short & Long-Long Transition Enrichment (Lag-1)
    short_th = 3
    long_th = 6
    ss = ll = 0
    for e in entries:
        toks = e.tokens
        for i in range(len(toks) - 1):
            l1, l2 = len(toks[i]), len(toks[i + 1])
            if l1 <= short_th and l2 <= short_th:
                ss += 1
            elif l1 >= long_th and l2 >= long_th:
                ll += 1

    n_ss, n_ll = [], []
    for _ in range(12):
        tss = tll = 0
        for e in entries:
            if len(e.tokens) >= 2:
                cp = [len(t) for t in e.tokens]
                rng.shuffle(cp)
                for i in range(len(cp) - 1):
                    if cp[i] <= short_th and cp[i + 1] <= short_th:
                        tss += 1
                    elif cp[i] >= long_th and cp[i + 1] >= long_th:
                        tll += 1
        n_ss.append(float(tss))
        n_ll.append(float(tll))

    mss, _, zss = z_score(float(ss), n_ss)
    mll, _, zll = z_score(float(ll), n_ll)
    print("\n  [3C. Short-Short (<=3 -> <=3) vs. Long-Long (>=6 -> >=6) Pair Enrichment]")
    if mss > 0:
        print(f"    Short-Short (len<=3 -> len<=3) : Obs={ss:5d} | LineShuf={mss:7.1f} (O/E={ss/mss:.2f}x, Z={zss:+.2f})")
    if mll > 0:
        print(f"    Long-Long   (len>=6 -> len>=6) : Obs={ll:5d} | LineShuf={mll:7.1f} (O/E={ll/mll:.2f}x, Z={zll:+.2f})")
    print()


def main() -> None:
    zl_path = sys.argv[1] if len(sys.argv) > 1 else "ZL3b-n.txt"
    rf_path = sys.argv[2] if len(sys.argv) > 2 else "RF1b-e.txt"

    print("==========================================================================")
    print("VOYNICH SURGICAL ANOMALY DISSECTOR (NO L0-ISM / NO SEMANTIC LABELS)")
    print("==========================================================================\n")

    zl_entries = parse_ivtff(zl_path)
    print(f"Loaded {len(zl_entries)} lines across {len({e.folio for e in zl_entries})} folios from {zl_path}.")

    rf_entries: List[LineEntry] = []
    try:
        rf_entries = parse_ivtff(rf_path)
        print(f"Loaded {len(rf_entries)} lines across {len({e.folio for e in rf_entries})} folios from {rf_path}.\n")
    except FileNotFoundError:
        print(f"[INFO] Secondary corpus {rf_path} not found; skipping RF parity check.\n")

    dissect1_cross_space_anatomy(zl_entries, rf_entries)
    dissect2_vertical_alignment(zl_entries)
    dissect3_length_burst_mechanism(zl_entries)


if __name__ == "__main__":
    main()
