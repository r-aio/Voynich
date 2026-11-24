#!/usr/bin/env python3
"""
Voynich Manuscript (MS 408) — v3.2 Head-to-Head Benchmark:
Strict Held-Out Hybrids vs. Naibbe/Workshop 6-Table Verbose Ciphers & Compact Tachygraphy
Zero external dependencies (Python 3.11 stdlib only). No L0-ISM / No semantic labels.

Addresses all open critiques from v3.0 / v3.1 peer reviews:
  1. STRICT OUT-OF-SAMPLE EVALUATION (Zero In-Sample Leakage):
     - Split-Half Folio Holdout (Even folios train -> Odd folios generated; Odd -> Even),
       reassembled into a 100% out-of-sample full corpus of identical geometry.
     - Leave-One-Quire-Out (LOQO): Every quire generated strictly from all OTHER quires.
  2. AUTHENTIC NAIBBE / WORKSHOP 6-TABLE VERBOSE CIPHERS (Greshko / Averyanov Class):
     - Topical medieval Latin-like plaintext (Zipfian function + section/quire/folio content words)
       chunked into 2-letter bigrams (L1, L2) and encoded via 6 EVA prefix+suffix tables
       (token = prefix[table, L1] + suffix[table, L2], ~2.2-2.5x glyph expansion):
       (a) Naibbe-Class Pure Verbose (6 tables, uncoupled table choice),
       (b) Workshop-Class Verbose (6 tables + section table bias + serial reuse + boundary sandhi + 2D slip).
     - Compact Tachygraphy (1:1 length-matched mapping + scribal pen-lift false spaces + 2D slip).
  3. EXTENDED DIAGNOSTIC METRICS:
     - Empty Corner: h2(str), h2(B) [Section B outlier], h3(str), Types, TTR.
     - Boundary & Length: Net MI1, Line-Break MI Reset %, Net Lag-1 len_r.
     - 2D Layout: Interior VertEx, VertE1 (Proportional Col +/-1, Line k-1 vs. LineShuf).
     - Twins & Burstiness (voynich.site metrics):
         * W5Ex (within-folio +/-5 exact match),
         * RepBurst = W5Ex - FolioShuf_W5Ex (true local exact-repeat burstiness),
         * TwinW5% (distinct Edit==1 neighbor rate in +/-5 window),
         * TwinLift = TwinW5 - FolioShuf_TwinW5 (true local homophone-twin clustering),
         * JaccSQ / JaccDQ (Same-Quire vs. Diff-Quire adjacent-folio Jaccard).
     - PART 3: Label Bottleneck Audit (True un-truncated label glyph length & H/B/S prose overlap).
"""

from __future__ import annotations

import math
import random
import re
import statistics
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple


@dataclass
class LineEntry:
    folio: str
    line_id: str
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

            entries.append(
                LineEntry(
                    folio=fid,
                    line_id=f"{fid}.{loc_id}",
                    quire=quire,
                    section=section,
                    currier=currier,
                    scribe=scribe,
                    tokens=toks,
                )
            )

    return entries


# ---------------------------------------------------------------------------
# Fast Core Metrics
# ---------------------------------------------------------------------------

def is_edit_le_1(a: str, b: str) -> bool:
    if a == b:
        return True
    la, lb = len(a), len(b)
    if la == lb:
        diffs = 0
        for ca, cb in zip(a, b):
            if ca != cb:
                diffs += 1
                if diffs > 1:
                    return False
        return True
    if la - lb == 1:
        i = 0
        while i < lb and a[i] == b[i]:
            i += 1
        return a[i + 1 :] == b[i:]
    if lb - la == 1:
        i = 0
        while i < la and a[i] == b[i]:
            i += 1
        return a[i:] == b[i + 1 :]
    return False


def has_edit_le_1_buckets(tok: str, buckets: Dict[int, Set[str]]) -> bool:
    lt = len(tok)
    for lc in (lt - 1, lt, lt + 1):
        cset = buckets.get(lc)
        if not cset:
            continue
        if lc == lt and tok in cset:
            return True
        for w in cset:
            if is_edit_le_1(tok, w):
                return True
    return False


def char_entropies(lines: List[List[str]]) -> Tuple[float, float, float]:
    """Returns (h2_stream, h3_stream, h2_word_raw) in bits."""
    c2: Counter = Counter()
    c3: Counter = Counter()
    w1: Counter = Counter()
    w2: Counter = Counter()
    n2 = n3 = wn2 = 0

    for toks in lines:
        if not toks:
            continue
        s = " ".join(toks)
        ls = len(s)
        for i in range(ls - 1):
            c2[s[i : i + 2]] += 1
        n2 += max(0, ls - 1)
        for i in range(ls - 2):
            c3[s[i : i + 3]] += 1
        n3 += max(0, ls - 2)
        for tok in toks:
            lt = len(tok)
            if lt >= 2:
                w1.update(tok[:-1])
                for i in range(lt - 1):
                    w2[tok[i : i + 2]] += 1
                wn2 += lt - 1

    def ent(cnt: Counter, tot: int) -> float:
        if tot <= 0:
            return 0.0
        inv = 1.0 / tot
        return -sum((v * inv) * math.log2(v * inv) for v in cnt.values())

    c2_pre: Counter = Counter()
    for bg, v in c2.items():
        c2_pre[bg[0]] += v
    c3_pre: Counter = Counter()
    for tg, v in c3.items():
        c3_pre[tg[:2]] += v

    h2_s = max(0.0, ent(c2, n2) - ent(c2_pre, n2))
    h3_s = max(0.0, ent(c3, n3) - ent(c3_pre, n3))
    h2_w = max(0.0, ent(w2, wn2) - ent(w1, wn2))
    return h2_s, h3_s, h2_w


def mutual_info_pairs(pairs: List[Tuple[str, str]]) -> float:
    n = len(pairs)
    if n == 0:
        return 0.0
    cx: Counter = Counter()
    cy: Counter = Counter()
    cxy: Counter = Counter()
    for a, b in pairs:
        cx[a] += 1
        cy[b] += 1
        cxy[(a, b)] += 1
    inv = 1.0 / n
    mi = 0.0
    for (a, b), v in cxy.items():
        pab = v * inv
        mi += pab * math.log2(pab / ((cx[a] * inv) * (cy[b] * inv)))
    return max(0.0, mi)


def within_and_cross_mi(folio_lines: Dict[str, List[List[str]]]) -> Tuple[float, float]:
    in_p: List[Tuple[str, str]] = []
    cr_p: List[Tuple[str, str]] = []
    for lines in folio_lines.values():
        for li, toks in enumerate(lines):
            for i in range(len(toks) - 1):
                in_p.append((toks[i][-1], toks[i + 1][0]))
            if li + 1 < len(lines) and toks and lines[li + 1]:
                cr_p.append((toks[-1][-1], lines[li + 1][0][0]))
    return mutual_info_pairs(in_p), mutual_info_pairs(cr_p)


def pearson_len_r(lines: List[List[str]]) -> float:
    sx = sy = sxx = syy = sxy = 0.0
    n = 0
    for toks in lines:
        for i in range(len(toks) - 1):
            x = len(toks[i])
            y = len(toks[i + 1])
            sx += x
            sy += y
            sxx += x * x
            syy += y * y
            sxy += x * y
            n += 1
    if n < 2:
        return 0.0
    mx = sx / n
    my = sy / n
    num = sxy - n * mx * my
    dx = sxx - n * mx * mx
    dy = syy - n * my * my
    den = math.sqrt(max(0.0, dx * dy))
    return (num / den) if den > 1e-12 else 0.0


def vertical_interior_rates(folio_lines: Dict[str, List[List[str]]], radius: int = 1) -> Tuple[float, float]:
    ex = e1 = tot = 0
    for lines in folio_lines.values():
        valid = [ln for ln in lines if len(ln) >= 3]
        for li in range(1, len(valid)):
            prev = valid[li - 1]
            curr = valid[li]
            lp, lc = len(prev), len(curr)
            scale = (lp - 1) / (lc - 1)
            for i in range(1, lc - 1):
                tok = curr[i]
                proj = round(i * scale)
                lo = 0 if proj - radius < 0 else proj - radius
                hi = lp if proj + radius + 1 > lp else proj + radius + 1
                found_ex = False
                found_e1 = False
                for j in range(lo, hi):
                    other = prev[j]
                    if other == tok:
                        found_ex = True
                        found_e1 = True
                        break
                    if not found_e1 and is_edit_le_1(tok, other):
                        found_e1 = True
                tot += 1
                if found_ex:
                    ex += 1
                if found_e1:
                    e1 += 1
    if tot == 0:
        return 0.0, 0.0
    return ex / tot * 100.0, e1 / tot * 100.0


def window5_and_twins(folio_lines: Dict[str, List[List[str]]]) -> Tuple[float, float, float]:
    """
    Returns (W5_Exact%, W5_EditLe1%, W5_StrictTwin_EditEq1_Only%) within +/-5 token window.
    StrictTwin requires at least one DISTINCT neighbor at Levenshtein distance == 1.
    """
    ex = e1 = twin = tot = 0
    for lines in folio_lines.values():
        seq = [t for ln in lines for t in ln]
        n = len(seq)
        for i in range(n):
            tok = seq[i]
            lo = 0 if i - 5 < 0 else i - 5
            hi = n if i + 6 > n else i + 6
            has_ex = False
            has_twin = False
            for j in range(lo, hi):
                if j == i:
                    continue
                other = seq[j]
                if other == tok:
                    has_ex = True
                elif not has_twin and is_edit_le_1(tok, other):
                    has_twin = True
                if has_ex and has_twin:
                    break
            tot += 1
            if has_ex:
                ex += 1
            if has_ex or has_twin:
                e1 += 1
            if has_twin:
                twin += 1
    if tot == 0:
        return 0.0, 0.0, 0.0
    return ex / tot * 100.0, e1 / tot * 100.0, twin / tot * 100.0


def adjacent_jaccard(
    folio_order: List[str], folio_lines: Dict[str, List[List[str]]], folio_quire: Dict[str, str]
) -> Tuple[float, float]:
    same_q: List[float] = []
    diff_q: List[float] = []
    vsets = {f: {t for ln in folio_lines[f] for t in ln} for f in folio_order}
    for i in range(len(folio_order) - 1):
        f1, f2 = folio_order[i], folio_order[i + 1]
        s1, s2 = vsets[f1], vsets[f2]
        u = len(s1 | s2)
        jac = (len(s1 & s2) / u) if u else 0.0
        if folio_quire[f1] == folio_quire[f2]:
            same_q.append(jac)
        else:
            diff_q.append(jac)
    return (statistics.mean(same_q) if same_q else 0.0), (statistics.mean(diff_q) if diff_q else 0.0)


def evaluate_all_metrics(
    folio_order: List[str],
    folio_lines: Dict[str, List[List[str]]],
    folio_quire: Dict[str, str],
    folio_section: Dict[str, str],
    n_line_shuf: int = 5,
    n_folio_shuf: int = 4,
    seed: int = 408,
) -> Dict[str, float]:
    rng = random.Random(seed)
    all_lines = [ln for f in folio_order for ln in folio_lines[f]]
    all_toks = [t for ln in all_lines for t in ln]
    n_toks = len(all_toks)
    n_types = len(set(all_toks))
    ttr = (n_types / n_toks) if n_toks else 0.0

    h2_s, h3_s, h2_w = char_entropies(all_lines)
    sec_b_lines = [ln for f in folio_order if folio_section[f] == "B" for ln in folio_lines[f]]
    h2_b = char_entropies(sec_b_lines)[0] if sec_b_lines else 0.0

    obs_mi1, obs_cr_mi = within_and_cross_mi(folio_lines)
    obs_lr = pearson_len_r(all_lines)
    obs_vex, obs_ve1 = vertical_interior_rates(folio_lines, radius=1)
    w5_ex, w5_e1, w5_twin = window5_and_twins(folio_lines)
    jac_sq, jac_dq = adjacent_jaccard(folio_order, folio_lines, folio_quire)

    n_mi1, n_cr, n_lr, n_vex, n_ve1 = [], [], [], [], []
    for _ in range(n_line_shuf):
        sh_map: Dict[str, List[List[str]]] = {}
        sh_all: List[List[str]] = []
        lo_map: Dict[str, List[List[str]]] = {}
        for f in folio_order:
            fl = []
            for ln in folio_lines[f]:
                cp = ln[:]
                rng.shuffle(cp)
                fl.append(cp)
                sh_all.append(cp)
            sh_map[f] = fl
            lo = folio_lines[f][:]
            rng.shuffle(lo)
            lo_map[f] = lo
        n_mi1.append(within_and_cross_mi(sh_map)[0])
        n_cr.append(within_and_cross_mi(lo_map)[1])
        n_lr.append(pearson_len_r(sh_all))
        vx, ve = vertical_interior_rates(sh_map, radius=1)
        n_vex.append(vx)
        n_ve1.append(ve)

    fs_ex, fs_twin = [], []
    for _ in range(n_folio_shuf):
        fsh_map: Dict[str, List[List[str]]] = {}
        for f in folio_order:
            flat = [t for ln in folio_lines[f] for t in ln]
            rng.shuffle(flat)
            rebuilt = []
            pos = 0
            for ln in folio_lines[f]:
                rebuilt.append(flat[pos : pos + len(ln)])
                pos += len(ln)
            fsh_map[f] = rebuilt
        ex_f, _, tw_f = window5_and_twins(fsh_map)
        fs_ex.append(ex_f)
        fs_twin.append(tw_f)

    net_mi1 = obs_mi1 - statistics.mean(n_mi1)
    net_cr = obs_cr_mi - statistics.mean(n_cr)
    reset_pct = (1.0 - max(0.0, net_cr) / net_mi1) * 100.0 if net_mi1 > 0.01 else 0.0

    return {
        "h2_s": h2_s,
        "h2_b": h2_b,
        "h3_s": h3_s,
        "h2_w": h2_w,
        "types": float(n_types),
        "ttr": ttr,
        "mi1": net_mi1,
        "reset_pct": reset_pct,
        "len_r": obs_lr - statistics.mean(n_lr),
        "vex": obs_vex - statistics.mean(n_vex),
        "ve1": obs_ve1 - statistics.mean(n_ve1),
        "w5_ex": w5_ex,
        "rep_burst": w5_ex - statistics.mean(fs_ex),
        "w5_twin": w5_twin,
        "twin_lift": w5_twin - statistics.mean(fs_twin),
        "jac_sq": jac_sq,
        "jac_dq": jac_dq,
    }


def evaluate_labels(
    folio_order: List[str],
    folio_lines: Dict[str, List[List[str]]],
    folio_section: Dict[str, str],
) -> Dict[str, float]:
    """Audits 1-2 token label lines vs. H/B/S >=5-token prose."""
    prose_set: Set[str] = set()
    label_lens: List[int] = []
    label_toks: List[str] = []

    for f in folio_order:
        sec = folio_section[f]
        for ln in folio_lines[f]:
            if 1 <= len(ln) <= 2:
                label_lens.append(sum(len(t) for t in ln))
                label_toks.extend(ln)
            elif sec in ("H", "B", "S") and len(ln) >= 5:
                prose_set.update(ln)

    if not label_toks:
        return {"n_lab": 0.0, "med_g": 0.0, "mean_g": 0.0, "in_prose": 0.0, "near_prose": 0.0}

    buckets: Dict[int, Set[str]] = defaultdict(set)
    for w in prose_set:
        buckets[len(w)].add(w)

    exact_in = 0
    near_in = 0
    for t in label_toks:
        if t in prose_set:
            exact_in += 1
            near_in += 1
        elif has_edit_le_1_buckets(t, buckets):
            near_in += 1

    return {
        "n_lab": float(len(label_lens)),
        "med_g": float(statistics.median(label_lens)),
        "mean_g": float(statistics.mean(label_lens)),
        "in_prose": exact_in / len(label_toks) * 100.0,
        "near_prose": near_in / len(label_toks) * 100.0,
    }


# ---------------------------------------------------------------------------
# MODEL FAMILY A: Strict Held-Out Character Stream + 2D Vertical Memory
# ---------------------------------------------------------------------------

class CharMarkovModel:
    def __init__(self, order: int) -> None:
        self.order = order
        self.tables: List[Dict[str, Tuple[List[str], List[int]]]] = [{} for _ in range(order + 1)]
        self.raw: List[Dict[str, Counter]] = [defaultdict(Counter) for _ in range(order + 1)]

    def fit(self, lines: List[List[str]]) -> None:
        K = self.order
        for toks in lines:
            if not toks:
                continue
            s = "^" * K + " ".join(toks) + "$"
            for i in range(K, len(s)):
                ch = s[i]
                for o in range(1, K + 1):
                    self.raw[o][s[i - o : i]][ch] += 1
                self.raw[0][""][ch] += 1

    def finalize(self) -> None:
        for o in range(self.order + 1):
            self.tables[o] = {
                ctx: (list(cnt.keys()), list(cnt.values())) for ctx, cnt in self.raw[o].items()
            }

    def sample_char(self, ctx: str, rng: random.Random) -> str:
        for o in range(min(self.order, len(ctx)), 0, -1):
            entry = self.tables[o].get(ctx[-o:])
            if entry is not None:
                return rng.choices(entry[0], weights=entry[1])[0]
        e0 = self.tables[0][""]
        return rng.choices(e0[0], weights=e0[1])[0]

    def sample_nonspace_char(self, ctx: str, rng: random.Random, avoid: str = "") -> Optional[str]:
        for o in range(min(self.order, len(ctx)), 0, -1):
            entry = self.tables[o].get(ctx[-o:])
            if entry is not None:
                ks, ws = entry
                cands = [(k, w) for k, w in zip(ks, ws) if k not in (" ", "$", "^", avoid)]
                if cands:
                    return rng.choices([k for k, _ in cands], weights=[w for _, w in cands])[0]
        return None


def contextual_mutate(tok: str, model: CharMarkovModel, rng: random.Random) -> str:
    lt = len(tok)
    r = rng.random()
    if r < 0.60 and lt >= 2:
        i = rng.randrange(lt)
        ctx = (" " + tok[:i])[-model.order :]
        ch = model.sample_nonspace_char(ctx, rng, avoid=tok[i])
        if ch is not None:
            return tok[:i] + ch + tok[i + 1 :]
    elif r < 0.82:
        i = rng.randrange(lt + 1)
        ctx = (" " + tok[:i])[-model.order :]
        ch = model.sample_nonspace_char(ctx, rng)
        if ch is not None:
            return tok[:i] + ch + tok[i:]
    elif lt >= 3:
        i = rng.randrange(lt)
        return tok[:i] + tok[i + 1 :]
    return tok


def generate_folio_from_model(
    target_lines: List[List[str]],
    model: CharMarkovModel,
    p_vert: float,
    rng: random.Random,
) -> List[List[str]]:
    order = model.order
    lag_choices = (1, 2, 3)
    lag_weights = (0.60, 0.25, 0.15)
    gen_lines: List[List[str]] = []

    for target_ln in target_lines:
        n_toks = len(target_ln)
        line: List[str] = []
        ctx = "^" * order
        li = len(gen_lines)

        for pos in range(n_toks):
            used_vert = False
            if p_vert > 0.0 and li >= 1 and n_toks >= 3 and rng.random() < p_vert:
                lag = rng.choices(lag_choices, weights=lag_weights)[0]
                if li >= lag:
                    prev_ln = gen_lines[li - lag]
                    lp = len(prev_ln)
                    if lp >= 1:
                        proj = round(pos * (lp - 1) / (n_toks - 1)) if n_toks > 1 else 0
                        cand = rng.choice(prev_ln[max(0, proj - 1) : min(lp, proj + 2)])
                        tok = cand if rng.random() < 0.42 else contextual_mutate(cand, model, rng)
                        line.append(tok)
                        ctx = (ctx + tok + " ")[-order:]
                        used_vert = True

            if not used_vert:
                buf: List[str] = []
                steps = 0
                while steps < 25:
                    ch = model.sample_char(ctx, rng)
                    steps += 1
                    if ch in (" ", "$"):
                        if buf:
                            ctx = (ctx + " ")[-order:]
                            break
                        if ch == "$":
                            ctx = "^" * order
                        continue
                    buf.append(ch)
                    ctx = (ctx + ch)[-order:]
                line.append("".join(buf) if buf else "ol")

        gen_lines.append(line)
    return gen_lines


def generate_heldout_hybrid(
    folio_order: List[str],
    folio_lines: Dict[str, List[List[str]]],
    folio_currier: Dict[str, str],
    folio_section: Dict[str, str],
    folio_quire: Dict[str, str],
    order: int,
    stratify: str,  # "currier" or "sec_cur"
    split_mode: str,  # "even_odd" or "loqo"
    p_vert: float = 0.035,
    seed: int = 11,
) -> Dict[str, List[List[str]]]:
    rng = random.Random(seed)
    out: Dict[str, List[List[str]]] = {}

    if split_mode == "even_odd":
        folds = [
            ([f for idx, f in enumerate(folio_order) if idx % 2 == 0],
             [f for idx, f in enumerate(folio_order) if idx % 2 == 1]),
            ([f for idx, f in enumerate(folio_order) if idx % 2 == 1],
             [f for idx, f in enumerate(folio_order) if idx % 2 == 0]),
        ]
    else:
        quires = sorted({folio_quire[f] for f in folio_order})
        folds = [
            ([f for f in folio_order if folio_quire[f] != q],
             [f for f in folio_order if folio_quire[f] == q])
            for q in quires
        ]

    for train_fs, test_fs in folds:
        g_mod = CharMarkovModel(order)
        g_mod.fit([ln for f in train_fs for ln in folio_lines[f]])
        g_mod.finalize()

        cur_mods: Dict[str, CharMarkovModel] = {}
        by_cur: Dict[str, List[List[str]]] = defaultdict(list)
        for f in train_fs:
            by_cur[folio_currier[f]].extend(folio_lines[f])
        for c, ls in by_cur.items():
            if len(ls) >= 20:
                cm = CharMarkovModel(order)
                cm.fit(ls)
                cm.finalize()
                cur_mods[c] = cm

        sc_mods: Dict[Tuple[str, str], CharMarkovModel] = {}
        if stratify == "sec_cur":
            by_sc: Dict[Tuple[str, str], List[List[str]]] = defaultdict(list)
            for f in train_fs:
                by_sc[(folio_section[f], folio_currier[f])].extend(folio_lines[f])
            for key, ls in by_sc.items():
                if len(ls) >= 30:
                    sm = CharMarkovModel(order)
                    sm.fit(ls)
                    sm.finalize()
                    sc_mods[key] = sm

        for f in test_fs:
            if stratify == "sec_cur" and (folio_section[f], folio_currier[f]) in sc_mods:
                mod = sc_mods[(folio_section[f], folio_currier[f])]
            elif folio_currier[f] in cur_mods:
                mod = cur_mods[folio_currier[f]]
            else:
                mod = g_mod
            out[f] = generate_folio_from_model(folio_lines[f], mod, p_vert, rng)

    return out


# ---------------------------------------------------------------------------
# MODEL FAMILY B: Realistic Topical Latin Plaintext + Naibbe/Workshop & Tachygraphy
# ---------------------------------------------------------------------------

LATIN_FUNC_WORDS = [
    "et", "in", "de", "ad", "per", "cum", "non", "est", "ut", "si", "ex", "pro",
    "vel", "aut", "sed", "hoc", "sub", "ab", "ac", "nec", "ita", "ubi", "quo",
    "nam", "tam", "iam", "dum", "seu", "post", "ante", "inter", "contra",
    "super", "sine", "enim", "igitur", "item", "quia", "quod", "sunt", "fiat",
]

LATIN_STEMS = [
    "aqu", "herb", "radic", "foli", "flor", "semin", "cortic", "succ", "ole",
    "vin", "acet", "mell", "sal", "calc", "calid", "frigid", "humid", "sicc",
    "balne", "vapor", "ign", "calor", "vas", "oll", "canal", "tub", "font",
    "stell", "lun", "sol", "cael", "sign", "grad", "hor", "temp", "mens",
    "corp", "caput", "ventr", "sanguin", "febr", "dolor", "medicin", "pulver",
    "unguent", "decoct", "infus", "mixt", "colat", "coct", "lavat", "bibat",
    "ponat", "detur", "valet", "sanat", "mund", "purg", "fort", "dulc", "amar",
    "alb", "nigr", "rubr", "virid", "flav", "magn", "parv", "long", "brev",
    "prim", "secund", "terti", "quart", "quint", "sext", "septim", "octav",
    "taur", "ariet", "gemin", "cancr", "leon", "virgin", "libr", "scorp",
    "pisc", "aquar", "capric", "sagit", "orient", "occid", "merid", "septent",
]

LATIN_ENDINGS = [
    "a", "ae", "am", "is", "us", "um", "i", "o", "os", "es", "em", "ibus",
    "orum", "arum", "at", "et", "it", "ant", "ent", "unt", "tur", "re", "io",
]


def build_latin_plaintext_per_folio(
    folio_order: List[str],
    folio_section: Dict[str, str],
    folio_quire: Dict[str, str],
    seed: int = 77,
) -> Tuple[Dict[str, List[str]], Dict[str, List[str]]]:
    rng = random.Random(seed)
    all_content: List[str] = []
    for st in LATIN_STEMS:
        for en in LATIN_ENDINGS[:8]:
            w = st + en
            if 4 <= len(w) <= 10:
                all_content.append(w)
    rng.shuffle(all_content)

    sections = sorted(set(folio_section.values()))
    sec_vocab: Dict[str, List[str]] = {}
    chunk = max(40, len(all_content) // max(1, len(sections)))
    for idx, sec in enumerate(sections):
        start = (idx * chunk) % len(all_content)
        sec_vocab[sec] = [all_content[(start + k) % len(all_content)] for k in range(140)]

    quire_topics: Dict[str, List[str]] = {
        q: rng.sample(all_content, 45) for q in sorted(set(folio_quire.values()))
    }

    folio_prose_vocab: Dict[str, List[str]] = {}
    folio_label_nouns: Dict[str, List[str]] = {}
    label_candidates = [w for w in all_content if 6 <= len(w) <= 8]

    for f in folio_order:
        sec = folio_section[f]
        q = folio_quire[f]
        f_specific = rng.sample(sec_vocab[sec], 15)
        q_slice = rng.sample(quire_topics[q], 15)
        folio_prose_vocab[f] = LATIN_FUNC_WORDS + f_specific * 3 + q_slice * 2 + sec_vocab[sec][:50]
        own_l = [w for w in (f_specific + sec_vocab[sec]) if 6 <= len(w) <= 8]
        folio_label_nouns[f] = own_l if own_l else label_candidates

    return folio_prose_vocab, folio_label_nouns


def build_boundary_log_odds(lines: List[List[str]]) -> Dict[Tuple[str, str], float]:
    cx: Counter = Counter()
    cy: Counter = Counter()
    cxy: Counter = Counter()
    n = 0
    for toks in lines:
        for i in range(len(toks) - 1):
            a, b = toks[i][-1], toks[i + 1][0]
            cx[a] += 1
            cy[b] += 1
            cxy[(a, b)] += 1
            n += 1
    odds: Dict[Tuple[str, str], float] = {}
    if n == 0:
        return odds
    for a, na in cx.items():
        for b, nb in cy.items():
            exp = (na * nb) / n
            obs = cxy.get((a, b), 0)
            odds[(a, b)] = math.log((obs + 1.0) / (exp + 1.0))
    return odds


def extract_eva_prefix_suffix_pools(
    lines: List[List[str]],
) -> Tuple[List[str], List[str]]:
    """Extracts frequency-ranked real EVA onsets (prefixes) and codas (suffixes) from training lines."""
    pre_cnt: Counter = Counter()
    suf_cnt: Counter = Counter()
    for toks in lines:
        for t in toks:
            lt = len(t)
            if lt >= 3:
                mid = lt // 2
                pre_cnt[t[:mid]] += 1
                suf_cnt[t[mid:]] += 1
            elif lt == 2:
                pre_cnt[t[0]] += 1
                suf_cnt[t[1]] += 1
    pres = [p for p, _ in pre_cnt.most_common(180)]
    sufs = [s for s, _ in suf_cnt.most_common(180)]
    return pres, sufs


def generate_naibbe_workshop_corpus(
    folio_order: List[str],
    folio_lines: Dict[str, List[List[str]]],
    folio_currier: Dict[str, str],
    folio_section: Dict[str, str],
    folio_quire: Dict[str, str],
    mode: str,  # "naibbe_pure" or "workshop_full"
    seed: int = 11,
) -> Tuple[Dict[str, List[List[str]]], Dict[str, float]]:
    """
    Authentic Naibbe / Workshop-class 6-table verbose bigram substitution:
      - Plaintext letters are paired into bigrams (L1, L2) (2 plaintext letters -> 1 EVA token
        formed by prefix[table, L1] + suffix[table, L2], ~2.2-2.5x glyph expansion).
      - Uses 6 prefix/suffix tables populated from real EVA onsets/codas (extracted strictly
        from EVEN folios, separated by Currier A/B in workshop_full to capture dialect shifts).
      - In 'workshop_full' (Averyanov-style):
          * Section table-weight bias (section dialects),
          * Serial reuse (p=0.45): recurring bigrams within a folio reuse the previous table,
          * Boundary sandhi: candidate tables weighted by exp(1.8 * log_odds(prev_last -> cand_first)),
          * Mild 2D vertical slip (p=0.035) from proportional Col +/-1 in lines k-1..k-3.
    Also records true un-truncated 6-table verbose encoding of 6-8 letter Latin labels.
    """
    rng = random.Random(seed)
    folio_prose_vocab, folio_label_nouns = build_latin_plaintext_per_folio(
        folio_order, folio_section, folio_quire, seed=seed + 100
    )

    even_fs = [f for idx, f in enumerate(folio_order) if idx % 2 == 0]
    even_lines = [ln for f in even_fs for ln in folio_lines[f]]
    sandhi_odds = build_boundary_log_odds(even_lines)

    mut_mod = CharMarkovModel(3)
    mut_mod.fit(even_lines)
    mut_mod.finalize()

    # Latin letter frequency ranking from our plaintext
    lat_cnt: Counter = Counter()
    for f in folio_order:
        for w in folio_prose_vocab[f]:
            lat_cnt.update(w)
    lat_alpha = [ch for ch, _ in lat_cnt.most_common()]
    lat_rank = {ch: idx for idx, ch in enumerate(lat_alpha)}

    def make_6_slot_tables(lines_pool: List[List[str]]) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
        pres, sufs = extract_eva_prefix_suffix_pools(lines_pool)
        if not pres:
            pres = ["qo", "ch", "sh", "ok", "ot", "d", "o", "s", "l", "y"]
        if not sufs:
            sufs = ["aiin", "edy", "ol", "or", "ar", "dy", "ey", "in", "y", "al"]
        pre_tables: List[Dict[str, str]] = [{} for _ in range(6)]
        suf_tables: List[Dict[str, str]] = [{} for _ in range(6)]
        # Assign frequency-matched EVA prefixes/suffixes across 6 tables (most frequent Latin
        # letters get the most frequent EVA prefixes/suffixes, giving natural Zipf + low h2)
        for ch, r in lat_rank.items():
            for t in range(6):
                p_idx = (r * 3 + t) % min(len(pres), 90)
                s_idx = (r * 3 + t) % min(len(sufs), 90)
                pre_tables[t][ch] = pres[p_idx]
                suf_tables[t][ch] = sufs[s_idx]
        return pre_tables, suf_tables

    glob_tables = make_6_slot_tables(even_lines)
    cur_tables: Dict[str, Tuple[List[Dict[str, str]], List[Dict[str, str]]]] = {}
    for c_val in ("A", "B", "OTHER"):
        c_lines = [ln for f in even_fs if folio_currier[f] == c_val for ln in folio_lines[f]]
        cur_tables[c_val] = make_6_slot_tables(c_lines) if len(c_lines) >= 20 else glob_tables

    sec_weights: Dict[str, List[float]] = {}
    for idx, sec in enumerate(sorted(set(folio_section.values()))):
        ws = [1.0] * 6
        ws[idx % 6] = 2.6
        ws[(idx + 1) % 6] = 1.6
        sec_weights[sec] = ws

    out: Dict[str, List[List[str]]] = {}
    raw_lab_lens: List[int] = []
    raw_lab_toks: List[str] = []

    for f in folio_order:
        sec = folio_section[f]
        cur = folio_currier[f]
        pre_t, suf_t = cur_tables[cur] if mode == "workshop_full" else glob_tables
        base_tw = sec_weights[sec] if mode == "workshop_full" else [1.0] * 6

        # Build topical Latin bigram stream for this folio
        p_vocab = folio_prose_vocab[f]
        p_bgs: List[Tuple[str, str]] = []
        needed = sum(len(ln) for ln in folio_lines[f]) + 40
        while len(p_bgs) < needed:
            w = rng.choice(p_vocab)
            s = w if len(w) % 2 == 0 else w + "e"
            for i in range(0, len(s), 2):
                p_bgs.append((s[i], s[i + 1]))

        ptr = 0
        sticky_tbl: Dict[Tuple[str, str], int] = {}
        gen_lines: List[List[str]] = []

        for target_ln in folio_lines[f]:
            n_toks = len(target_ln)
            li = len(gen_lines)

            # True un-truncated verbose encoding of a 6-8 letter Latin label noun
            if 1 <= n_toks <= 2:
                lw = rng.choice(folio_label_nouns[f])
                ls = lw if len(lw) % 2 == 0 else lw + "e"
                enc_l: List[str] = []
                for i in range(0, len(ls), 2):
                    c1, c2 = ls[i], ls[i + 1]
                    t_id = rng.choices(range(6), weights=base_tw)[0]
                    enc_l.append(pre_t[t_id].get(c1, "ch") + suf_t[t_id].get(c2, "ol"))
                raw_lab_lens.append(sum(len(x) for x in enc_l))
                raw_lab_toks.extend(enc_l)

            line: List[str] = []
            for pos in range(n_toks):
                used_vert = False
                if mode == "workshop_full" and li >= 1 and n_toks >= 3 and rng.random() < 0.035:
                    lag = rng.choices((1, 2, 3), weights=(0.60, 0.25, 0.15))[0]
                    if li >= lag:
                        prev_ln = gen_lines[li - lag]
                        lp = len(prev_ln)
                        if lp >= 1:
                            proj = round(pos * (lp - 1) / (n_toks - 1)) if n_toks > 1 else 0
                            cand = rng.choice(prev_ln[max(0, proj - 1) : min(lp, proj + 2)])
                            tok = cand if rng.random() < 0.42 else contextual_mutate(cand, mut_mod, rng)
                            line.append(tok)
                            used_vert = True

                if not used_vert:
                    c1, c2 = p_bgs[ptr]
                    ptr += 1
                    cands = [pre_t[t].get(c1, "ch") + suf_t[t].get(c2, "ol") for t in range(6)]
                    if mode == "naibbe_pure":
                        tok = rng.choice(cands)
                    else:
                        prev_last = line[-1][-1] if line else None
                        if (c1, c2) in sticky_tbl and rng.random() < 0.45:
                            tok = cands[sticky_tbl[(c1, c2)]]
                        else:
                            ws = []
                            for t in range(6):
                                wv = base_tw[t]
                                if prev_last is not None:
                                    lo = sandhi_odds.get((prev_last, cands[t][0]), 0.0)
                                    wv *= math.exp(1.8 * lo)
                                ws.append(max(1e-6, wv))
                            chosen_t = rng.choices(range(6), weights=ws)[0]
                            tok = cands[chosen_t]
                            sticky_tbl[(c1, c2)] = chosen_t
                    line.append(tok)

            gen_lines.append(line)
        out[f] = gen_lines

    prose_set: Set[str] = set()
    for f in folio_order:
        if folio_section[f] in ("H", "B", "S"):
            for ln in out[f]:
                if len(ln) >= 5:
                    prose_set.update(ln)
    buckets: Dict[int, Set[str]] = defaultdict(set)
    for w in prose_set:
        buckets[len(w)].add(w)
    ex_in = sum(1 for t in raw_lab_toks if t in prose_set)
    near_in = sum(1 for t in raw_lab_toks if t in prose_set or has_edit_le_1_buckets(t, buckets))

    lab_stats = {
        "n_lab": float(len(raw_lab_lens)),
        "med_g": float(statistics.median(raw_lab_lens)) if raw_lab_lens else 0.0,
        "mean_g": float(statistics.mean(raw_lab_lens)) if raw_lab_lens else 0.0,
        "in_prose": (ex_in / len(raw_lab_toks) * 100.0) if raw_lab_toks else 0.0,
        "near_prose": (near_in / len(raw_lab_toks) * 100.0) if raw_lab_toks else 0.0,
    }
    return out, lab_stats


def generate_compact_tachygraphy_corpus(
    folio_order: List[str],
    folio_lines: Dict[str, List[List[str]]],
    folio_currier: Dict[str, str],
    folio_section: Dict[str, str],
    folio_quire: Dict[str, str],
    seed: int = 11,
) -> Tuple[Dict[str, List[List[str]]], Dict[str, float]]:
    """
    Tests Trop 2 (Compact 1:1 Tachygraphy / Abbreviated Natural Language + False Pen-Lift Spaces):
      - Maps topical Latin words 1:1 (compact ~0.9-1.0x length, NO 2-3x expansion) into
        real EVA-phonotactic forms, with ~35% of long words split by a scribal pen-lift
        at characteristic cross-space boundaries (y|q, r|a, s|a, o|l, n|c),
      - Adds 3.5% 2D vertical visual slip from lines k-1..k-3.
    """
    rng = random.Random(seed)
    folio_prose_vocab, folio_label_nouns = build_latin_plaintext_per_folio(
        folio_order, folio_section, folio_quire, seed=seed + 200
    )

    even_fs = [f for idx, f in enumerate(folio_order) if idx % 2 == 0]
    even_lines = [ln for f in even_fs for ln in folio_lines[f]]
    mut_mod = CharMarkovModel(3)
    mut_mod.fit(even_lines)
    mut_mod.finalize()

    eva_by_len: Dict[int, List[str]] = defaultdict(list)
    cur_eva_by_len: Dict[str, Dict[int, List[str]]] = defaultdict(lambda: defaultdict(list))
    for f in even_fs:
        c = folio_currier[f]
        for ln in folio_lines[f]:
            for t in ln:
                eva_by_len[len(t)].append(t)
                cur_eva_by_len[c][len(t)].append(t)

    codebook: Dict[Tuple[str, str], List[str]] = {}
    split_triggers = {("y", "q"), ("r", "a"), ("s", "a"), ("o", "l"), ("o", "r"), ("n", "c")}

    def make_compact_form(lat_w: str, cur: str) -> List[str]:
        pool_map = cur_eva_by_len[cur] if cur_eva_by_len[cur] else eva_by_len
        L = len(lat_w)
        if L >= 6 and rng.random() < 0.35:
            l1 = max(2, L // 2)
            l2 = max(2, L - l1)
            c1 = pool_map.get(l1) or eva_by_len.get(l1) or ["ol"]
            c2 = pool_map.get(l2) or eva_by_len.get(l2) or ["ar"]
            for _ in range(14):
                t1 = rng.choice(c1)
                t2 = rng.choice(c2)
                if (t1[-1], t2[0]) in split_triggers:
                    return [t1, t2]
            return [rng.choice(c1), rng.choice(c2)]
        target_l = max(2, min(9, L - 1 if L >= 7 else L))
        cands = pool_map.get(target_l) or eva_by_len.get(target_l) or ["daiin"]
        return [rng.choice(cands)]

    out: Dict[str, List[List[str]]] = {}
    raw_lab_lens: List[int] = []
    raw_lab_toks: List[str] = []

    for f in folio_order:
        cur = folio_currier[f]
        p_vocab = folio_prose_vocab[f]

        tok_stream: List[str] = []
        needed = sum(len(ln) for ln in folio_lines[f]) + 30
        while len(tok_stream) < needed:
            lw = rng.choice(p_vocab)
            key = (cur, lw)
            if key not in codebook:
                codebook[key] = make_compact_form(lw, cur)
            tok_stream.extend(codebook[key])

        ptr = 0
        gen_lines: List[List[str]] = []
        for target_ln in folio_lines[f]:
            n_toks = len(target_ln)
            li = len(gen_lines)

            if 1 <= n_toks <= 2:
                lw = rng.choice(folio_label_nouns[f])
                key = (cur, lw)
                if key not in codebook:
                    codebook[key] = make_compact_form(lw, cur)
                enc = codebook[key]
                raw_lab_lens.append(sum(len(x) for x in enc))
                raw_lab_toks.extend(enc)

            line: List[str] = []
            for pos in range(n_toks):
                used_vert = False
                if li >= 1 and n_toks >= 3 and rng.random() < 0.035:
                    lag = rng.choices((1, 2, 3), weights=(0.60, 0.25, 0.15))[0]
                    if li >= lag:
                        prev_ln = gen_lines[li - lag]
                        lp = len(prev_ln)
                        if lp >= 1:
                            proj = round(pos * (lp - 1) / (n_toks - 1)) if n_toks > 1 else 0
                            cand = rng.choice(prev_ln[max(0, proj - 1) : min(lp, proj + 2)])
                            tok = cand if rng.random() < 0.42 else contextual_mutate(cand, mut_mod, rng)
                            line.append(tok)
                            used_vert = True
                if not used_vert:
                    line.append(tok_stream[ptr])
                    ptr += 1
            gen_lines.append(line)
        out[f] = gen_lines

    prose_set: Set[str] = set()
    for f in folio_order:
        if folio_section[f] in ("H", "B", "S"):
            for ln in out[f]:
                if len(ln) >= 5:
                    prose_set.update(ln)
    buckets: Dict[int, Set[str]] = defaultdict(set)
    for w in prose_set:
        buckets[len(w)].add(w)
    ex_in = sum(1 for t in raw_lab_toks if t in prose_set)
    near_in = sum(1 for t in raw_lab_toks if t in prose_set or has_edit_le_1_buckets(t, buckets))

    lab_stats = {
        "n_lab": float(len(raw_lab_lens)),
        "med_g": float(statistics.median(raw_lab_lens)) if raw_lab_lens else 0.0,
        "mean_g": float(statistics.mean(raw_lab_lens)) if raw_lab_lens else 0.0,
        "in_prose": (ex_in / len(raw_lab_toks) * 100.0) if raw_lab_toks else 0.0,
        "near_prose": (near_in / len(raw_lab_toks) * 100.0) if raw_lab_toks else 0.0,
    }
    return out, lab_stats


def main() -> None:
    t0 = time.time()
    zl_path = sys.argv[1] if len(sys.argv) > 1 else "ZL3b-n.txt"

    print("==========================================================================")
    print("VOYNICH v3.2 — HELD-OUT HYBRIDS VS. VERBOSE WORKSHOP & TACHYGRAPHY")
    print("==========================================================================\n")

    entries = parse_ivtff(zl_path)
    folio_order: List[str] = []
    folio_lines: Dict[str, List[List[str]]] = defaultdict(list)
    folio_currier: Dict[str, str] = {}
    folio_quire: Dict[str, str] = {}
    folio_section: Dict[str, str] = {}

    for e in entries:
        if e.folio not in folio_lines:
            folio_order.append(e.folio)
        folio_lines[e.folio].append(e.tokens)
        folio_currier[e.folio] = e.currier if e.currier in ("A", "B") else "OTHER"
        folio_quire[e.folio] = e.quire
        folio_section[e.folio] = e.section

    print(f"Loaded {len(entries)} lines across {len(folio_order)} folios from {zl_path}.\n")

    m_real = dict(folio_lines)
    m_ho_cur3 = generate_heldout_hybrid(
        folio_order, folio_lines, folio_currier, folio_section, folio_quire, 3, "currier", "even_odd", 0.035, 11
    )
    m_ho_cur4 = generate_heldout_hybrid(
        folio_order, folio_lines, folio_currier, folio_section, folio_quire, 4, "currier", "even_odd", 0.035, 11
    )
    m_ho_sc4 = generate_heldout_hybrid(
        folio_order, folio_lines, folio_currier, folio_section, folio_quire, 4, "sec_cur", "even_odd", 0.035, 11
    )
    m_loqo_c4 = generate_heldout_hybrid(
        folio_order, folio_lines, folio_currier, folio_section, folio_quire, 4, "currier", "loqo", 0.035, 11
    )
    m_naibbe, lab_naibbe = generate_naibbe_workshop_corpus(
        folio_order, folio_lines, folio_currier, folio_section, folio_quire, "naibbe_pure", 11
    )
    m_workshop, lab_workshop = generate_naibbe_workshop_corpus(
        folio_order, folio_lines, folio_currier, folio_section, folio_quire, "workshop_full", 11
    )
    m_tachy, lab_tachy = generate_compact_tachygraphy_corpus(
        folio_order, folio_lines, folio_currier, folio_section, folio_quire, 11
    )

    model_list: List[Tuple[str, Dict[str, List[List[str]]], Optional[Dict[str, float]]]] = [
        ("REAL (ZL3b-n)", m_real, None),
        ("HO-Split Cur-3 + 2D(3.5%)", m_ho_cur3, None),
        ("HO-Split Cur-4 + 2D(3.5%)", m_ho_cur4, None),
        ("HO-Split Sec+Cur-4 + 2D", m_ho_sc4, None),
        ("LOQO (Cross-Quire) Cur-4+2D", m_loqo_c4, None),
        ("Naibbe-Class Pure (6-Table)", m_naibbe, lab_naibbe),
        ("Workshop-Class (6T+Reuse+San)", m_workshop, lab_workshop),
        ("Compact Tachy (1:1+Split+2D)", m_tachy, lab_tachy),
    ]

    results: List[Tuple[str, Dict[str, float], Dict[str, float]]] = []
    for name, mdata, override_lab in model_list:
        metrics = evaluate_all_metrics(
            folio_order, mdata, folio_quire, folio_section, n_line_shuf=5, n_folio_shuf=4, seed=408
        )
        lab_m = override_lab if override_lab is not None else evaluate_labels(folio_order, mdata, folio_section)
        results.append((name, metrics, lab_m))

    # PART 1: Empty Corner, Boundary MI Reset, Length Coupling & 2D Alignment
    print("=== PART 1: EMPTY CORNER, BOUNDARY RESET, LENGTH & 2D ALIGNMENT (OUT-OF-SAMPLE) ===")
    print(
        "  Model                         | h2(s) | h2(B) | h3(s) |    TTR |   MI1  | Reset% |  len_r | VertEx | VertE1"
    )
    print(
        "  -----------------------------------------------------------------------------------------------------------"
    )
    for name, r, _ in results:
        print(
            f"  {name:<29} | {r['h2_s']:5.3f} | {r['h2_b']:5.3f} | {r['h3_s']:5.3f} | {r['ttr']:6.4f} | "
            f"{r['mi1']:+6.3f} | {r['reset_pct']:5.1f}% | {r['len_r']:+6.3f} | {r['vex']:+6.2f} | {r['ve1']:+6.2f}"
        )
    print()

    # PART 2: Homophone Twins Clustering, Local Burstiness & Quire Topicality
    print("=== PART 2: TWINS CLUSTERING (EDIT==1), EXACT BURSTINESS & QUIRE TOPICALITY ===")
    print("  RepBurst = W5Ex - FolioShuf_W5Ex | TwinLift = W5_Edit1Only - FolioShuf_Edit1Only (pp).\n")
    print(
        "  Model                         | W5Ex% | RepBurst | TwinW5% | TwinLift | JaccSQ | JaccDQ | SQ/DQ"
    )
    print(
        "  ------------------------------------------------------------------------------------------------"
    )
    for name, r, _ in results:
        sq_dq = (r["jac_sq"] / r["jac_dq"]) if r["jac_dq"] > 1e-6 else 0.0
        print(
            f"  {name:<29} | {r['w5_ex']:5.2f} |  {r['rep_burst']:+6.2f}  |  {r['w5_twin']:5.2f}  |  "
            f"{r['twin_lift']:+6.2f}  | {r['jac_sq']:6.4f} | {r['jac_dq']:6.4f} | {sq_dq:4.2f}x"
        )
    print()

    # PART 3: Label Bottleneck Audit
    print("=== PART 3: LABEL BOTTLENECK AUDIT (1-2 TOKEN LABELS VS. H/B/S PROSE) ===")
    print("  Verbose ciphers encode 6-8L Latin nouns with the SAME 6-table cipher (no ad-hoc truncation).\n")
    print(
        "  Model                         | Labels | MedGlyphs | MeanGlyphs | MaxVerb(6-8L) | InProse% | Ex+Ed1%"
    )
    print(
        "  ------------------------------------------------------------------------------------------------------"
    )
    for name, _, lm in results:
        mv_lo = lm["med_g"] / 8.0
        mv_hi = lm["med_g"] / 6.0
        print(
            f"  {name:<29} | {int(lm['n_lab']):6d} |   {lm['med_g']:5.1f}   |    {lm['mean_g']:5.2f}   | "
            f"{mv_hi:4.2f}-{mv_lo:4.2f}x   |  {lm['in_prose']:5.1f}%  |  {lm['near_prose']:5.1f}%"
        )

    print(f"\nCompleted in {time.time() - t0:.1f}s.")


if __name__ == "__main__":
    main()
