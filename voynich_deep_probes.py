#!/usr/bin/env python3
"""
Voynich Manuscript (MS 408) — Deep Structural & Mechanism Probes (ZL3b-n.txt)
Zero external dependencies (Python 3.11 stdlib only). No L0-ISM / No semantic labels.

Implements 4 targeted falsification probes:
  DEEP PROBE 1: Length Autocorrelation Decomposition
                (Separates line-position layout gradient from true length bursts
                 via mid-line isolation, residual detrending, and cross-line checks).
  DEEP PROBE 2: Cross-Space Coupling (End of Token i -> Start of Token i+1)
                (Tests "false space / sub-word split" hypothesis via Mutual Information
                 within lines vs. across line breaks against line/folio shuffles).
  DEEP PROBE 3: Label -> Own Folio Linkage & Label-Only Vocabulary Audit
                (Tests whether 1-2 token labels match their own folio's body text
                 more than a random folio from the same section, and audits Edit<=1
                 proximity of non-prose label tokens).
  DEEP PROBE 4: Vertical (Line k Above Line k+1) vs. Horizontal Alignment
                (Tests visual self-citation / column-copying using both within-line
                 shuffle and within-folio line-order shuffle controls, plus interior-only).
"""

from __future__ import annotations

import math
import random
import re
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Dict, List, Set, Tuple


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


def has_edit_le_1_in_buckets(tok: str, buckets: Dict[int, Set[str]]) -> bool:
    lt = len(tok)
    for l_cand in (lt - 1, lt, lt + 1):
        cand_set = buckets.get(l_cand)
        if not cand_set:
            continue
        if l_cand == lt and tok in cand_set:
            return True
        for w in cand_set:
            if is_edit_le_1(tok, w):
                return True
    return False


def make_len_buckets(words: Set[str]) -> Dict[int, Set[str]]:
    b: Dict[int, Set[str]] = defaultdict(set)
    for w in words:
        b[len(w)].add(w)
    return b


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


def mutual_info_bits(pairs: List[Tuple[str, str]]) -> Tuple[float, float, float]:
    """Returns (H(Y), H(Y|X), MI(X;Y)) in bits."""
    n = len(pairs)
    if n == 0:
        return 0.0, 0.0, 0.0
    cx: Counter = Counter()
    cy: Counter = Counter()
    cxy: Counter = Counter()
    for x, y in pairs:
        cx[x] += 1
        cy[y] += 1
        cxy[(x, y)] += 1

    hx = -sum((c / n) * math.log2(c / n) for c in cx.values())
    hy = -sum((c / n) * math.log2(c / n) for c in cy.values())
    hxy = -sum((c / n) * math.log2(c / n) for c in cxy.values())
    mi = max(0.0, hx + hy - hxy)
    hy_given_x = max(0.0, hxy - hx)
    return hy, hy_given_x, mi


def deep_probe1_length_autocorr_decomp(entries: List[LineEntry]) -> None:
    print("=== DEEP PROBE 1: LENGTH AUTOCORRELATION DECOMPOSITION (LAYOUT VS. BURSTS) ===")

    by_folio_lines: Dict[str, List[LineEntry]] = defaultdict(list)
    for e in entries:
        by_folio_lines[e.folio].append(e)

    # 1A. Raw within-line vs. mid-line only (excluding INIT and FINAL tokens)
    raw_x, raw_y = [], []
    mid_x, mid_y = [], []
    mid_lines: List[List[int]] = []
    for e in entries:
        toks = e.tokens
        n = len(toks)
        for i in range(n - 1):
            raw_x.append(float(len(toks[i])))
            raw_y.append(float(len(toks[i + 1])))
            if i >= 1 and (i + 1) <= (n - 2):
                mid_x.append(float(len(toks[i])))
                mid_y.append(float(len(toks[i + 1])))
        if n >= 4:
            mid_lines.append([len(t) for t in toks[1:-1]])

    r_raw = pearson_corr(raw_x, raw_y)
    r_mid = pearson_corr(mid_x, mid_y)

    # 1B. Position-detrended residuals (per Currier + relative position bin, and per folio)
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

    det_pos_x, det_pos_y = [], []
    det_both_x, det_both_y = [], []
    res_both_lines: List[List[float]] = []

    for e in entries:
        cur = e.currier if e.currier in ("A", "B") else "OTHER"
        n = len(e.tokens)
        if n < 2:
            continue
        f_shift = folio_mean[e.folio] - global_mean
        res_pos = [len(t) - bucket_mean[(cur, pos_bucket(i, n))] for i, t in enumerate(e.tokens)]
        res_both = [
            len(t) - bucket_mean[(cur, pos_bucket(i, n))] - f_shift for i, t in enumerate(e.tokens)
        ]
        res_both_lines.append(res_both)
        for i in range(n - 1):
            det_pos_x.append(res_pos[i])
            det_pos_y.append(res_pos[i + 1])
            det_both_x.append(res_both[i])
            det_both_y.append(res_both[i + 1])

    r_det_pos = pearson_corr(det_pos_x, det_pos_y)
    r_det_both = pearson_corr(det_both_x, det_both_y)

    # Proper residual shuffle null: shuffle mid-line lengths and detrended residuals inside each line
    rng = random.Random(408)
    null_mid_r: List[float] = []
    null_both_r: List[float] = []
    for _ in range(15):
        nx, ny = [], []
        for ml in mid_lines:
            cp = ml[:]
            rng.shuffle(cp)
            for i in range(len(cp) - 1):
                nx.append(float(cp[i]))
                ny.append(float(cp[i + 1]))
        null_mid_r.append(pearson_corr(nx, ny))

        bx, by = [], []
        for rl in res_both_lines:
            cp_r = rl[:]
            rng.shuffle(cp_r)
            for i in range(len(cp_r) - 1):
                bx.append(cp_r[i])
                by.append(cp_r[i + 1])
        null_both_r.append(pearson_corr(bx, by))

    # 1C. Cross-line boundary: last token of line k vs. first token of line k+1
    cross_x, cross_y = [], []
    for lines in by_folio_lines.values():
        for i in range(len(lines) - 1):
            cross_x.append(float(len(lines[i].tokens[-1])))
            cross_y.append(float(len(lines[i + 1].tokens[0])))
    r_cross = pearson_corr(cross_x, cross_y)

    null_cross_r: List[float] = []
    for _ in range(15):
        cx, cy = [], []
        for lines in by_folio_lines.values():
            cp_l = lines[:]
            rng.shuffle(cp_l)
            for i in range(len(cp_l) - 1):
                cx.append(float(len(cp_l[i].tokens[-1])))
                cy.append(float(len(cp_l[i + 1].tokens[0])))
        null_cross_r.append(pearson_corr(cx, cy))

    m_mid, sd_mid, z_mid = z_score(r_mid, null_mid_r)
    m_both, sd_both, z_both = z_score(r_det_both, null_both_r)
    m_cr, sd_cr, z_cr = z_score(r_cross, null_cross_r)

    print(f"  Raw Within-Line Autocorrelation (all pairs, n={len(raw_x)})     : r = {r_raw:+.4f}")
    print(
        f"  Mid-Line Only (no INIT/FINAL, n={len(mid_x)})                   : r = {r_mid:+.4f} "
        f"| MidShuf={m_mid:+.4f} (SD={sd_mid:.4f}, Z={z_mid:+.2f})"
    )
    print(f"  Position-Detrended Only (subtract line-pos mean)                : r = {r_det_pos:+.4f}")
    print(
        f"  Position + Folio Detrended (pure local burst)                   : r = {r_det_both:+.4f} "
        f"| ResShuf={m_both:+.4f} (SD={sd_both:.4f}, Z={z_both:+.2f})"
    )
    print(
        f"  Cross-Line Boundary (End(k) -> Start(k+1), n={len(cross_x)})    : r = {r_cross:+.4f} "
        f"| LineOrdShuf={m_cr:+.4f} (SD={sd_cr:.4f}, Z={z_cr:+.2f})"
    )
    print()


def deep_probe2_cross_space_coupling(entries: List[LineEntry]) -> None:
    print("=== DEEP PROBE 2: CROSS-SPACE COUPLING (END(i) -> START(i+1) MUTUAL INFO) ===")
    by_folio_lines: Dict[str, List[LineEntry]] = defaultdict(list)
    for e in entries:
        by_folio_lines[e.folio].append(e)

    def extract_pairs(
        lines_by_f: Dict[str, List[List[str]]], k_chars: int
    ) -> Tuple[List[Tuple[str, str]], List[Tuple[str, str]]]:
        in_line: List[Tuple[str, str]] = []
        cross_line: List[Tuple[str, str]] = []
        for lines in lines_by_f.values():
            for li, toks in enumerate(lines):
                for i in range(len(toks) - 1):
                    in_line.append((toks[i][-k_chars:], toks[i + 1][:k_chars]))
                if li < len(lines) - 1:
                    cross_line.append((toks[-1][-k_chars:], lines[li + 1][0][:k_chars]))
        return in_line, cross_line

    real_map = {f: [e.tokens for e in ls] for f, ls in by_folio_lines.items()}
    rng = random.Random(2026)

    for k_chars, label in [(1, "1-Char Boundary (last->first)"), (2, "2-Char Boundary (suf2->pre2)")]:
        in_p, cr_p = extract_pairs(real_map, k_chars)
        hy_in, hcond_in, mi_in = mutual_info_bits(in_p)
        _, _, mi_cr = mutual_info_bits(cr_p)

        null_in_line: List[float] = []
        null_in_folio: List[float] = []
        null_cr_lshuf: List[float] = []

        for _ in range(10):
            # Null 1: Within-line shuffle (breaks adjacency inside lines)
            lsh_map: Dict[str, List[List[str]]] = {}
            for f, lines in real_map.items():
                new_lines = []
                for toks in lines:
                    cp = toks[:]
                    rng.shuffle(cp)
                    new_lines.append(cp)
                lsh_map[f] = new_lines
            p_in_ls, _ = extract_pairs(lsh_map, k_chars)
            null_in_line.append(mutual_info_bits(p_in_ls)[2])

            # Null 2: Within-folio token shuffle preserving line lengths
            fsh_map: Dict[str, List[List[str]]] = {}
            for f, lines in real_map.items():
                flat = [t for line in lines for t in line]
                rng.shuffle(flat)
                rebuilt = []
                pos = 0
                for line in lines:
                    rebuilt.append(flat[pos : pos + len(line)])
                    pos += len(line)
                fsh_map[f] = rebuilt
            p_in_fs, _ = extract_pairs(fsh_map, k_chars)
            null_in_folio.append(mutual_info_bits(p_in_fs)[2])

            # Null 3: Line-order shuffle within folio (for cross-line boundary)
            lo_map: Dict[str, List[List[str]]] = {}
            for f, lines in real_map.items():
                cp_l = lines[:]
                rng.shuffle(cp_l)
                lo_map[f] = cp_l
            _, p_cr_lo = extract_pairs(lo_map, k_chars)
            null_cr_lshuf.append(mutual_info_bits(p_cr_lo)[2])

        m_ls, sd_ls, z_ls = z_score(mi_in, null_in_line)
        m_fs, sd_fs, z_fs = z_score(mi_in, null_in_folio)
        m_cr, sd_cr, z_cr = z_score(mi_cr, null_cr_lshuf)

        print(f"  [{label}]")
        print(
            f"    Within-Line (n={len(in_p):5d}) : MI = {mi_in:.4f} bits (H_start={hy_in:.3f} -> H_cond={hcond_in:.3f})"
        )
        print(
            f"      vs Within-Line Shuf    : Null = {m_ls:.4f} (SD={sd_ls:.4f}) | Lift = {mi_in - m_ls:+.4f} bits | Z = {z_ls:+.2f}"
        )
        print(
            f"      vs Within-Folio Shuf   : Null = {m_fs:.4f} (SD={sd_fs:.4f}) | Lift = {mi_in - m_fs:+.4f} bits | Z = {z_fs:+.2f}"
        )
        print(
            f"    Cross-Line  (n={len(cr_p):5d}) : MI = {mi_cr:.4f} bits | "
            f"LineOrdShuf = {m_cr:.4f} (SD={sd_cr:.4f}) | Lift = {mi_cr - m_cr:+.4f} | Z = {z_cr:+.2f}"
        )
    print()


def deep_probe3_label_own_folio_linkage(entries: List[LineEntry]) -> None:
    print("=== DEEP PROBE 3: LABEL -> OWN FOLIO LINKAGE & LABEL-ONLY VOCAB AUDIT ===")

    folio_sec: Dict[str, str] = {}
    folio_labels: Dict[str, List[str]] = defaultdict(list)
    folio_body: Dict[str, List[str]] = defaultdict(list)
    prose_vocab_hbs: Counter = Counter()

    for e in entries:
        folio_sec[e.folio] = e.section
        if 1 <= len(e.tokens) <= 2:
            folio_labels[e.folio].extend(e.tokens)
        else:
            folio_body[e.folio].extend(e.tokens)
        if e.section in ("H", "B", "S") and len(e.tokens) >= 5:
            prose_vocab_hbs.update(e.tokens)

    sec_body_folios: Dict[str, List[str]] = defaultdict(list)
    for f, btoks in folio_body.items():
        if btoks:
            sec_body_folios[folio_sec[f]].append(f)

    qual_folios = [
        f for f in folio_labels
        if folio_body.get(f) and len(sec_body_folios[folio_sec[f]]) >= 2
    ]

    sec_body_sets = {f: set(btoks) for f, btoks in folio_body.items() if btoks}
    sec_body_buckets = {f: make_len_buckets(bset) for f, bset in sec_body_sets.items()}

    def eval_label_linkage(assigned_folio: Dict[str, str]) -> Tuple[float, float, int]:
        exact_h = edit1_h = tot = 0
        for f in qual_folios:
            target_f = assigned_folio[f]
            bset = sec_body_sets[target_f]
            bbuckets = sec_body_buckets[target_f]
            for tok in folio_labels[f]:
                tot += 1
                if tok in bset:
                    exact_h += 1
                    edit1_h += 1
                elif has_edit_le_1_in_buckets(tok, bbuckets):
                    edit1_h += 1
        ex_pct = (exact_h / tot * 100.0) if tot else 0.0
        e1_pct = (edit1_h / tot * 100.0) if tot else 0.0
        return ex_pct, e1_pct, tot

    own_assign = {f: f for f in qual_folios}
    obs_ex, obs_e1, n_lab_toks = eval_label_linkage(own_assign)

    rng = random.Random(408)
    null_ex: List[float] = []
    null_e1: List[float] = []

    for _ in range(25):
        rand_assign: Dict[str, str] = {}
        for f in qual_folios:
            cands = [cand for cand in sec_body_folios[folio_sec[f]] if cand != f]
            rand_assign[f] = rng.choice(cands)
        ne, ne1, _ = eval_label_linkage(rand_assign)
        null_ex.append(ne)
        null_e1.append(ne1)

    m_ex, sd_ex, z_ex = z_score(obs_ex, null_ex)
    m_e1, sd_e1, z_e1 = z_score(obs_e1, null_e1)

    print(f"  Qualifying Folios (with both labels & >=3-tok body): {len(qual_folios)} ({n_lab_toks} label tokens)")
    print(
        f"  Exact Match in Own-Folio Body     : Obs = {obs_ex:5.2f}% | Same-Sec Random Folio = {m_ex:5.2f}% "
        f"(SD={sd_ex:.2f}%) | Lift = {obs_ex - m_ex:+5.2f} pp | Z = {z_ex:+.2f}"
    )
    print(
        f"  Edit<=1 Match in Own-Folio Body   : Obs = {obs_e1:5.2f}% | Same-Sec Random Folio = {m_e1:5.2f}% "
        f"(SD={sd_e1:.2f}%) | Lift = {obs_e1 - m_e1:+5.2f} pp | Z = {z_e1:+.2f}"
    )

    print("  Own-Folio Label Match by Section (Exact / Edit<=1 vs. Same-Sec Random):")
    by_sec_q: Dict[str, List[str]] = defaultdict(list)
    for f in qual_folios:
        by_sec_q[folio_sec[f]].append(f)
    for sec in sorted(by_sec_q.keys()):
        fs = by_sec_q[sec]
        tot_s = ex_s = e1_s = 0
        for f in fs:
            bset = sec_body_sets[f]
            bbuckets = sec_body_buckets[f]
            for tok in folio_labels[f]:
                tot_s += 1
                if tok in bset:
                    ex_s += 1
                    e1_s += 1
                elif has_edit_le_1_in_buckets(tok, bbuckets):
                    e1_s += 1
        if tot_s > 0:
            r_ex_s = []
            r_e1_s = []
            for _ in range(15):
                re_h = re1_h = 0
                for f in fs:
                    cands = [c for c in sec_body_folios[sec] if c != f]
                    cf = rng.choice(cands)
                    bset = sec_body_sets[cf]
                    bbuckets = sec_body_buckets[cf]
                    for tok in folio_labels[f]:
                        if tok in bset:
                            re_h += 1
                            re1_h += 1
                        elif has_edit_le_1_in_buckets(tok, bbuckets):
                            re1_h += 1
                r_ex_s.append(re_h / tot_s * 100.0)
                r_e1_s.append(re1_h / tot_s * 100.0)
            print(
                f"    Sec {sec} (n={tot_s:3d} toks, {len(fs):2d} folios) : "
                f"Own Exact={ex_s/tot_s*100:5.1f}% (Null={statistics.mean(r_ex_s):4.1f}%) | "
                f"Own Edit<=1={e1_s/tot_s*100:5.1f}% (Null={statistics.mean(r_e1_s):4.1f}%)"
            )

    all_label_toks = [t for toks in folio_labels.values() for t in toks]
    prose_set = set(prose_vocab_hbs.keys())
    prose_buckets = make_len_buckets(prose_set)
    in_prose = [t for t in all_label_toks if t in prose_set]
    not_in_prose = [t for t in all_label_toks if t not in prose_set]
    nip_edit1 = sum(1 for t in not_in_prose if has_edit_le_1_in_buckets(t, prose_buckets))

    print("\n  Audit of Non-Prose Label Tokens (absent from H/B/S >=5-tok prose):")
    if in_prose:
        print(
            f"    Shared with H/B/S Prose         : {len(in_prose):4d}/{len(all_label_toks)} "
            f"({len(in_prose)/len(all_label_toks)*100:5.1f}%) | MeanLen={statistics.mean(len(t) for t in in_prose):.2f}"
        )
    if not_in_prose:
        print(
            f"    Label-Only (Not in H/B/S Prose) : {len(not_in_prose):4d}/{len(all_label_toks)} "
            f"({len(not_in_prose)/len(all_label_toks)*100:5.1f}%) | MeanLen={statistics.mean(len(t) for t in not_in_prose):.2f}"
        )
        print(
            f"    Label-Only within Edit<=1 Prose : {nip_edit1:4d}/{len(not_in_prose)} "
            f"({nip_edit1/len(not_in_prose)*100:5.1f}%) [near-variants vs. truly distinct forms]"
        )
    print()


def deep_probe4_vertical_alignment(entries: List[LineEntry]) -> None:
    print("=== DEEP PROBE 4: VERTICAL ALIGNMENT (LINE k ABOVE LINE k+1) VS. CONTROLS ===")
    by_folio_lines: Dict[str, List[List[str]]] = defaultdict(list)
    for e in entries:
        if len(e.tokens) >= 3:
            by_folio_lines[e.folio].append(e.tokens)

    def vertical_rates(
        lines_map: Dict[str, List[List[str]]], interior_only: bool = False, radius: int = 1
    ) -> Tuple[float, float, int]:
        ex_hits = e1_hits = tot = 0
        for lines in lines_map.values():
            for li in range(1, len(lines)):
                prev = lines[li - 1]
                curr = lines[li]
                lp, lc = len(prev), len(curr)
                start_i = 1 if interior_only else 0
                end_i = (lc - 1) if interior_only else lc
                for i in range(start_i, end_i):
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

    for interior_only, tag in [
        (False, "ALL TOKENS (Proportional Col +/-1)"),
        (True, "INTERIOR ONLY (No Line-Init/Final, Col +/-1)"),
    ]:
        obs_ex, obs_e1, n_toks = vertical_rates(by_folio_lines, interior_only=interior_only, radius=1)

        # Control A: Within-Line Shuffle (keeps exact adjacent line above, destroys column alignment)
        nA_ex, nA_e1 = [], []
        # Control B: Within-Folio Line-Order Shuffle (keeps exact column positions, destroys vertical adjacency)
        nB_ex, nB_e1 = [], []

        for _ in range(15):
            map_a: Dict[str, List[List[str]]] = {}
            for f, lines in by_folio_lines.items():
                sh = []
                for line in lines:
                    cp = line[:]
                    rng.shuffle(cp)
                    sh.append(cp)
                map_a[f] = sh
            ea, e1a, _ = vertical_rates(map_a, interior_only=interior_only, radius=1)
            nA_ex.append(ea)
            nA_e1.append(e1a)

            map_b: Dict[str, List[List[str]]] = {}
            for f, lines in by_folio_lines.items():
                cp_l = lines[:]
                rng.shuffle(cp_l)
                map_b[f] = cp_l
            eb, e1b, _ = vertical_rates(map_b, interior_only=interior_only, radius=1)
            nB_ex.append(eb)
            nB_e1.append(e1b)

        mA_ex, sdA_ex, zA_ex = z_score(obs_ex, nA_ex)
        mA_e1, sdA_e1, zA_e1 = z_score(obs_e1, nA_e1)
        mB_ex, sdB_ex, zB_ex = z_score(obs_ex, nB_ex)
        mB_e1, sdB_e1, zB_e1 = z_score(obs_e1, nB_e1)

        print(f"  [{tag} | N={n_toks}]")
        print(f"    OBSERVED (Line k -> k+1) : Exact = {obs_ex:5.2f}% | Edit<=1 = {obs_e1:5.2f}%")
        print(
            f"    Ctrl A (Within-Line Shuf): Exact = {mA_ex:5.2f}% (SD={sdA_ex:.2f}%, Z={zA_ex:+.2f}) | "
            f"Edit<=1 = {mA_e1:5.2f}% (SD={sdA_e1:.2f}%, Z={zA_e1:+.2f})"
        )
        print(
            f"    Ctrl B (Line-Order Shuf) : Exact = {mB_ex:5.2f}% (SD={sdB_ex:.2f}%, Z={zB_ex:+.2f}) | "
            f"Edit<=1 = {mB_e1:5.2f}% (SD={sdB_e1:.2f}%, Z={zB_e1:+.2f})"
        )
    print("  Note: Ctrl A isolates pure vertical column alignment (controlling for line-to-line topic).")
    print("        Ctrl B isolates true line-adjacency (controlling for fixed line-start/end positions).\n")


def main() -> None:
    zl_path = sys.argv[1] if len(sys.argv) > 1 else "ZL3b-n.txt"
    print("==========================================================================")
    print("VOYNICH DEEP STRUCTURAL & MECHANISM PROBES (NO L0-ISM)")
    print("==========================================================================\n")

    entries = parse_ivtff(zl_path)
    print(f"Loaded {len(entries)} lines across {len({e.folio for e in entries})} folios from {zl_path}.\n")

    deep_probe1_length_autocorr_decomp(entries)
    deep_probe2_cross_space_coupling(entries)
    deep_probe3_label_own_folio_linkage(entries)
    deep_probe4_vertical_alignment(entries)


if __name__ == "__main__":
    main()
