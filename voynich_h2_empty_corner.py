#!/usr/bin/env python3
"""
Voynich Manuscript (MS 408) — Conditional Entropy (h2) & "Empty Corner" Benchmark (v3.1)
Zero external dependencies (Python 3.11 stdlib only). No L0-ISM / No semantic labels.

Directly tests the "Empty Corner" critique of v3.0:
  Can a constrained local character-stream + 2D vertical memory model simultaneously
  reproduce:
    1. Ultra-low conditional character entropy h2 = H(c_i | c_{i-1}) (~2.0-2.3 bits in EVA),
    2. High lexical diversity (Types ~ 7,800, TTR ~ 0.197),
    3. Cross-space boundary coupling (MI1 ~ +0.185 bits, MI2 ~ 0.003),
    4. Lag-1 length autocorrelation (len_r ~ +0.114),
    5. 2D vertical interior alignment (VertEx ~ +0.57 pp, VertE1 ~ +1.58 pp),
    6. Local +/-5 window clustering (W5Ex ~ 7.6%, W5E1 ~ 28.9%) and same- vs. diff-quire Jaccard.

Outputs:
  SECTION 1: Exact Character Entropy Profile (h1, h2, h3) on ZL3b-n.txt
             (full-stream with spaces AND strictly within-word, stratified by Currier & Section).
  SECTION 2: 9-Model Benchmark Matrix (matched exact folio & line-length geometry).
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
from typing import Dict, List, Optional, Tuple


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


def char_entropies(lines: List[List[str]]) -> Dict[str, float]:
    """
    Computes exact character-level entropies (in bits):
      - h1_stream   : H(c) over space-separated line stream (" ".join(tokens))
      - h2_stream   : H(c_i | c_{i-1}) over space-separated line stream (classic Voynich h2)
      - h3_stream   : H(c_i | c_{i-2}, c_{i-1}) over space-separated line stream
      - h2_word_raw : H(c_i | c_{i-1}) strictly on internal character pairs (no spaces)
      - h2_word_bnd : H(c_i | c_{i-1}) within words including start/end delimiters (^/$)
    """
    c1: Counter = Counter()
    c2: Counter = Counter()
    c3: Counter = Counter()
    n1 = n2 = n3 = 0

    w1: Counter = Counter()
    w2: Counter = Counter()
    wn2 = 0

    wb1: Counter = Counter()
    wb2: Counter = Counter()
    wbn2 = 0

    for toks in lines:
        if not toks:
            continue
        s = " ".join(toks)
        ls = len(s)
        c1.update(s)
        n1 += ls
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
            wt = "^" + tok + "$"
            for i in range(len(wt) - 1):
                wb1[wt[i]] += 1
                wb2[wt[i : i + 2]] += 1
                wbn2 += 1

    def entropy(cnt: Counter, tot: int) -> float:
        if tot <= 0:
            return 0.0
        inv = 1.0 / tot
        return -sum((v * inv) * math.log2(v * inv) for v in cnt.values())

    H1 = entropy(c1, n1)
    H2_joint = entropy(c2, n2)
    H3_joint = entropy(c3, n3)

    c2_pre: Counter = Counter()
    for bg, v in c2.items():
        c2_pre[bg[0]] += v
    H_c2_pre = entropy(c2_pre, n2)

    c3_pre: Counter = Counter()
    for tg, v in c3.items():
        c3_pre[tg[:2]] += v
    H_c3_pre = entropy(c3_pre, n3)

    return {
        "h1_stream": H1,
        "h2_stream": max(0.0, H2_joint - H_c2_pre),
        "h3_stream": max(0.0, H3_joint - H_c3_pre),
        "h2_word_raw": max(0.0, entropy(w2, wn2) - entropy(w1, wn2)),
        "h2_word_bnd": max(0.0, entropy(wb2, wbn2) - entropy(wb1, wbn2)),
    }


def mutual_info_1char(lines: List[List[str]], lag: int) -> float:
    cx: Counter = Counter()
    cy: Counter = Counter()
    cxy: Counter = Counter()
    n = 0
    for toks in lines:
        lt = len(toks)
        for i in range(lt - lag):
            a = toks[i][-1]
            b = toks[i + lag][0]
            cx[a] += 1
            cy[b] += 1
            cxy[(a, b)] += 1
            n += 1
    if n == 0:
        return 0.0
    inv = 1.0 / n
    mi = 0.0
    for (a, b), v in cxy.items():
        pab = v * inv
        pa = cx[a] * inv
        pb = cy[b] * inv
        mi += pab * math.log2(pab / (pa * pb))
    return max(0.0, mi)


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


def window5_rates(folio_lines: Dict[str, List[List[str]]]) -> Tuple[float, float]:
    ex = e1 = tot = 0
    for lines in folio_lines.values():
        seq = [t for ln in lines for t in ln]
        n = len(seq)
        for i in range(n):
            tok = seq[i]
            lo = 0 if i - 5 < 0 else i - 5
            hi = n if i + 6 > n else i + 6
            found_ex = False
            found_e1 = False
            for j in range(lo, hi):
                if j == i:
                    continue
                other = seq[j]
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


def evaluate_corpus(
    folio_order: List[str],
    folio_lines: Dict[str, List[List[str]]],
    folio_quire: Dict[str, str],
    n_shuffles: int = 6,
    seed: int = 408,
) -> Dict[str, float]:
    rng = random.Random(seed)
    all_lines = [ln for f in folio_order for ln in folio_lines[f]]
    all_toks = [t for ln in all_lines for t in ln]
    n_toks = len(all_toks)
    n_types = len(set(all_toks))
    ttr = (n_types / n_toks) if n_toks else 0.0

    ent = char_entropies(all_lines)
    obs_mi1 = mutual_info_1char(all_lines, 1)
    obs_mi2 = mutual_info_1char(all_lines, 2)
    obs_lr = pearson_len_r(all_lines)
    obs_vex, obs_ve1 = vertical_interior_rates(folio_lines, radius=1)
    w5_ex, w5_e1 = window5_rates(folio_lines)
    jac_same, jac_diff = adjacent_jaccard(folio_order, folio_lines, folio_quire)

    n_mi1, n_mi2, n_lr, n_vex, n_ve1 = [], [], [], [], []
    for _ in range(n_shuffles):
        sh_map: Dict[str, List[List[str]]] = {}
        sh_all: List[List[str]] = []
        for f in folio_order:
            fl = []
            for ln in folio_lines[f]:
                cp = ln[:]
                rng.shuffle(cp)
                fl.append(cp)
                sh_all.append(cp)
            sh_map[f] = fl
        n_mi1.append(mutual_info_1char(sh_all, 1))
        n_mi2.append(mutual_info_1char(sh_all, 2))
        n_lr.append(pearson_len_r(sh_all))
        vx, ve = vertical_interior_rates(sh_map, radius=1)
        n_vex.append(vx)
        n_ve1.append(ve)

    return {
        "h1": ent["h1_stream"],
        "h2_s": ent["h2_stream"],
        "h2_w": ent["h2_word_raw"],
        "h3_s": ent["h3_stream"],
        "types": float(n_types),
        "ttr": ttr,
        "mi1": obs_mi1 - statistics.mean(n_mi1),
        "mi2": obs_mi2 - statistics.mean(n_mi2),
        "len_r": obs_lr - statistics.mean(n_lr),
        "vex": obs_vex - statistics.mean(n_vex),
        "ve1": obs_ve1 - statistics.mean(n_ve1),
        "w5_ex": w5_ex,
        "w5_e1": w5_e1,
        "jac_sq": jac_same,
        "jac_dq": jac_diff,
    }


class CharMarkovModel:
    """Order-K character Markov table with automatic lower-order backoff."""

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
                    ctx = s[i - o : i]
                    self.raw[o][ctx][ch] += 1
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
        entry0 = self.tables[0][""]
        return rng.choices(entry0[0], weights=entry0[1])[0]

    def sample_nonspace_char(self, ctx: str, rng: random.Random, avoid: str = "") -> Optional[str]:
        for o in range(min(self.order, len(ctx)), 0, -1):
            entry = self.tables[o].get(ctx[-o:])
            if entry is not None:
                ks, ws = entry
                cands = [(k, w) for k, w in zip(ks, ws) if k not in (" ", "$", "^", avoid)]
                if cands:
                    return rng.choices([k for k, _ in cands], weights=[w for _, w in cands])[0]
        return None


def contextual_mutate_eva(tok: str, model: CharMarkovModel, rng: random.Random) -> str:
    """
    Applies a 1-edit EVA-phonotactic mutation using the trained character Markov model
    so mutated copies do not inject illegal bigrams into h2.
    """
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


def generate_hybrid_corpus(
    folio_order: List[str],
    folio_lines: Dict[str, List[List[str]]],
    folio_currier: Dict[str, str],
    folio_section: Dict[str, str],
    order: int,
    scope: str,  # "global", "currier", "section", "folio_interp"
    p_vert: float,
    folio_alpha: float = 0.0,
    seed: int = 11,
) -> Dict[str, List[List[str]]]:
    """
    Generates a synthetic corpus matching exact folio & line-length geometry:
      - Order-K character Markov stream (with space as a character),
      - Optional scope conditioning (global / Currier / Section / Folio-Interpolated),
      - Optional 2D vertical column memory (probability p_vert of copying or
        phonotactically mutating a token from proportional Col +/-1 in lines k-1..k-3
        with decaying lag weights 0.60 / 0.25 / 0.15).
    """
    rng = random.Random(seed)
    all_lines = [ln for f in folio_order for ln in folio_lines[f]]

    global_model = CharMarkovModel(order)
    global_model.fit(all_lines)
    global_model.finalize()

    cur_models: Dict[str, CharMarkovModel] = {}
    if scope in ("currier", "folio_interp"):
        by_cur: Dict[str, List[List[str]]] = defaultdict(list)
        for f in folio_order:
            by_cur[folio_currier[f]].extend(folio_lines[f])
        for c, ls in by_cur.items():
            cm = CharMarkovModel(order)
            cm.fit(ls)
            cm.finalize()
            cur_models[c] = cm

    sec_models: Dict[str, CharMarkovModel] = {}
    if scope == "section":
        by_sec: Dict[str, List[List[str]]] = defaultdict(list)
        for f in folio_order:
            by_sec[folio_section[f]].extend(folio_lines[f])
        for sec, ls in by_sec.items():
            sm = CharMarkovModel(order)
            sm.fit(ls)
            sm.finalize()
            sec_models[sec] = sm

    folio_models: Dict[str, CharMarkovModel] = {}
    if scope == "folio_interp":
        for f in folio_order:
            fm = CharMarkovModel(order)
            fm.fit(folio_lines[f])
            fm.finalize()
            folio_models[f] = fm

    def draw_next_char(ctx: str, base_m: CharMarkovModel, f_m: Optional[CharMarkovModel]) -> str:
        if f_m is not None and folio_alpha > 0.0 and rng.random() < folio_alpha:
            for o in range(min(order, len(ctx)), 1, -1):
                entry = f_m.tables[o].get(ctx[-o:])
                if entry is not None:
                    return rng.choices(entry[0], weights=entry[1])[0]
        return base_m.sample_char(ctx, rng)

    def gen_one_token(
        ctx: str, base_m: CharMarkovModel, f_m: Optional[CharMarkovModel]
    ) -> Tuple[str, str]:
        buf: List[str] = []
        steps = 0
        while steps < 25:
            ch = draw_next_char(ctx, base_m, f_m)
            steps += 1
            if ch in (" ", "$"):
                if buf:
                    ctx = (ctx + " ")[-order:]
                    return "".join(buf), ctx
                if ch == "$":
                    ctx = "^" * order
                continue
            buf.append(ch)
            ctx = (ctx + ch)[-order:]
        tok = "".join(buf) if buf else "ol"
        return tok, (ctx + " ")[-order:]

    out: Dict[str, List[List[str]]] = {}
    lag_choices = (1, 2, 3)
    lag_weights = (0.60, 0.25, 0.15)

    for f in folio_order:
        if scope == "currier" or scope == "folio_interp":
            base_m = cur_models[folio_currier[f]]
        elif scope == "section":
            base_m = sec_models[folio_section[f]]
        else:
            base_m = global_model
        f_m = folio_models[f] if scope == "folio_interp" else None

        gen_lines: List[List[str]] = []
        for target_ln in folio_lines[f]:
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
                            lo = max(0, proj - 1)
                            hi = min(lp, proj + 2)
                            cand = rng.choice(prev_ln[lo:hi])
                            if rng.random() < 0.42:
                                tok = cand
                            else:
                                tok = contextual_mutate_eva(cand, base_m, rng)
                            line.append(tok)
                            ctx = (ctx + tok + " ")[-order:]
                            used_vert = True

                if not used_vert:
                    tok, ctx = gen_one_token(ctx, base_m, f_m)
                    line.append(tok)

            gen_lines.append(line)
        out[f] = gen_lines

    return out


def make_folio_shuffle(
    folio_order: List[str], folio_lines: Dict[str, List[List[str]]], seed: int = 11
) -> Dict[str, List[List[str]]]:
    rng = random.Random(seed)
    out: Dict[str, List[List[str]]] = {}
    for f in folio_order:
        flat = [t for ln in folio_lines[f] for t in ln]
        rng.shuffle(flat)
        rebuilt = []
        pos = 0
        for ln in folio_lines[f]:
            rebuilt.append(flat[pos : pos + len(ln)])
            pos += len(ln)
        out[f] = rebuilt
    return out


def main() -> None:
    t0 = time.time()
    zl_path = sys.argv[1] if len(sys.argv) > 1 else "ZL3b-n.txt"

    print("==========================================================================")
    print("VOYNICH v3.1 — CONDITIONAL ENTROPY (h2) & EMPTY-CORNER BENCHMARK")
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

    # ------------------------------------------------------------------
    # SECTION 1: Exact Character Entropy Profile (h1, h2, h3) on ZL3b-n
    # ------------------------------------------------------------------
    print("=== SECTION 1: CHARACTER ENTROPY PROFILE (h1, h2, h3) ON ZL3b-n ===")
    print("  Convention: h2(str) = H(c_i | c_{i-1}) with space as a character (classic Voynich h2).")
    print("              h2(wrd) = H(c_i | c_{i-1}) strictly on internal word bigrams (no spaces).")
    print("              h2(w^$) = H(c_i | c_{i-1}) within words with ^/$ start/end markers.\n")
    print("  Slice          |  Tokens | Types |    TTR |    h1 | h2(str) | h3(str) | h2(wrd) | h2(w^$)")
    print("  -----------------------------------------------------------------------------------------")

    slices: List[Tuple[str, List[List[str]]]] = [
        ("ALL CORPUS", [e.tokens for e in entries]),
        ("Currier A", [e.tokens for e in entries if e.currier == "A"]),
        ("Currier B", [e.tokens for e in entries if e.currier == "B"]),
        ("Currier OTHER", [e.tokens for e in entries if e.currier not in ("A", "B")]),
    ]
    for sec in ("H", "B", "P", "S", "T", "A", "Z", "C"):
        sec_ls = [e.tokens for e in entries if e.section == sec]
        if sec_ls:
            slices.append((f"Section {sec}", sec_ls))

    for name, ls in slices:
        if not ls:
            continue
        toks = [t for ln in ls for t in ln]
        nt = len(toks)
        nty = len(set(toks))
        ttr = nty / nt if nt else 0.0
        en = char_entropies(ls)
        print(
            f"  {name:<14} | {nt:7d} | {nty:5d} | {ttr:6.4f} | "
            f"{en['h1_stream']:5.3f} |   {en['h2_stream']:5.3f} |   {en['h3_stream']:5.3f} | "
            f"  {en['h2_word_raw']:5.3f} |   {en['h2_word_bnd']:5.3f}"
        )
    print()

    # ------------------------------------------------------------------
    # SECTION 2: Empty-Corner & Hybrid 2D Generator Matrix (9 Models)
    # ------------------------------------------------------------------
    print("=== SECTION 2: EMPTY-CORNER & HYBRID 2D GENERATOR BENCHMARK ===")
    print("  All models match exact folio/line-length geometry; net MI/len_r/Vert over 6 line-shuffles.\n")

    models: List[Tuple[str, Dict[str, List[List[str]]]]] = [
        ("REAL (ZL3b-n)", dict(folio_lines)),
        ("Within-Folio Shuffle Null", make_folio_shuffle(folio_order, folio_lines, seed=11)),
        ("Char-3 Global (1D)", generate_hybrid_corpus(folio_order, folio_lines, folio_currier, folio_section, 3, "global", 0.0, 0.0, 11)),
        ("Char-3 Per-Currier (1D)", generate_hybrid_corpus(folio_order, folio_lines, folio_currier, folio_section, 3, "currier", 0.0, 0.0, 11)),
        ("Hybrid Cur-3 + 2D (3.5%) [v3.0]", generate_hybrid_corpus(folio_order, folio_lines, folio_currier, folio_section, 3, "currier", 0.035, 0.0, 11)),
        ("Hybrid Cur-4 + 2D (3.5%)", generate_hybrid_corpus(folio_order, folio_lines, folio_currier, folio_section, 4, "currier", 0.035, 0.0, 11)),
        ("Hybrid Sec-3 + 2D (3.5%)", generate_hybrid_corpus(folio_order, folio_lines, folio_currier, folio_section, 3, "section", 0.035, 0.0, 11)),
        ("Hybrid Folio-3 + 2D (a=0.55)", generate_hybrid_corpus(folio_order, folio_lines, folio_currier, folio_section, 3, "folio_interp", 0.035, 0.55, 11)),
        ("Hybrid Folio-4 + 2D (a=0.55)", generate_hybrid_corpus(folio_order, folio_lines, folio_currier, folio_section, 4, "folio_interp", 0.035, 0.55, 11)),
    ]

    print(
        "  Model                           | h2(s) | h3(s) | Types |    TTR |   MI1  |  len_r | VertEx | VertE1 | W5Ex | W5E1 | JaccSQ | JaccDQ"
    )
    print(
        "  --------------------------------------------------------------------------------------------------------------------------------------"
    )

    for mname, mdata in models:
        r = evaluate_corpus(folio_order, mdata, folio_quire, n_shuffles=6, seed=408)
        print(
            f"  {mname:<31} | {r['h2_s']:5.3f} | {r['h3_s']:5.3f} | {int(r['types']):5d} | {r['ttr']:6.4f} | "
            f"{r['mi1']:+6.3f} | {r['len_r']:+6.3f} | {r['vex']:+6.2f} | {r['ve1']:+6.2f} | "
            f"{r['w5_ex']:4.1f} | {r['w5_e1']:4.1f} | {r['jac_sq']:6.4f} | {r['jac_dq']:6.4f}"
        )

    print("\n  Legend:")
    print("    h2(s), h3(s)   : 2nd/3rd-order conditional char entropy with space (bits).")
    print("    MI1, len_r     : Net within-line Lag-1 cross-space MI (bits) and length correlation r.")
    print("    VertEx / E1    : Net pp excess on interior tokens (Col +/-1, Line k-1 vs. LineShuf).")
    print("    W5Ex / W5E1    : +/-5 token window Exact / Edit<=1 match rate (%) within folio.")
    print("    JaccSQ / DQ    : Mean adjacent-folio Jaccard within Same Quire vs. Different Quire.")
    print(f"\nCompleted in {time.time() - t0:.1f}s.")


if __name__ == "__main__":
    main()
