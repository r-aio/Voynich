#!/usr/bin/env python3
"""
Voynich Manuscript (MS 408) — Conditional Character Entropy (h2) & "Empty Corner" Audit (v3.1)
Zero external dependencies (Python 3.11 stdlib only). No L0-ISM / No semantic labels.

Audits the classic "Voynich Empty Corner" — the combination of unusually low conditional
character entropy (h2 ~ 2.0-2.3 bits/char), rich word-level vocabulary (TTR ~ 0.20),
section/folio lexical specialization, cross-space MI, length coupling, and 2D vertical excess.

Parts:
  PART 1: Exact Character Entropy Profile (h1, h2, h3) on ZL3b-n.txt
          - Stream mode (including space as a symbol, standard Voynich literature definition)
          - Within-word mode (with explicit ^/$ word boundaries)
          - Stratified by Currier ($L) and Codicological Section ($I)
          - Independent parity check on RF1b-e.txt (if present)
  PART 2: "Empty Corner" Generative Benchmark (Zero Folio Leakage)
          Compares REAL (ZL3b-n) against 5 synthetic generators matched to exact folio/line geometry:
            1. Char-3 Global (1D)
            2. Hybrid Currier Char-3 + 2D (3.5%)
            3. Hybrid Sec+Currier Char-3 + 2D (3.5%)
            4. Hybrid Sec+Currier Char-4 + 2D (3.5%)
            5. Hybrid Sec+Currier Char-4 + 2D (3.5%) + Synthetic Folio-Topic Cache (no real folio leakage)
          Evaluates: h1, h2, h3, TTR, MI1, len_r, VertEx, VertE1, W5_Ex, W5_E1, AdjJaccard.
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


def char_entropies_stream(lines: List[List[str]]) -> Tuple[float, float, float, int]:
    """
    Computes exact character entropies (h1, h2, h3) in bits/char on line streams
    with spaces included as explicit characters (' '), matching standard Voynich h2 literature.
      h1 = H(X_t)
      h2 = H(X_t | X_{t-1}) = H(X_{t-1}, X_t) - H(X_{t-1})
      h3 = H(X_t | X_{t-2}, X_{t-1}) = H(X_{t-2}, X_{t-1}, X_t) - H(X_{t-2}, X_{t-1})
    """
    c1: Counter = Counter()
    c2: Counter = Counter()
    c3: Counter = Counter()
    n1 = n2 = n3 = 0

    for toks in lines:
        if not toks:
            continue
        s = " ".join(toks) + " "
        L = len(s)
        for i in range(L):
            c1[s[i]] += 1
        n1 += L
        if L >= 2:
            for i in range(L - 1):
                c2[s[i : i + 2]] += 1
            n2 += L - 1
        if L >= 3:
            for i in range(L - 2):
                c3[s[i : i + 3]] += 1
            n3 += L - 2

    def H(cnt: Counter, tot: int) -> float:
        if tot == 0:
            return 0.0
        return -sum((v / tot) * math.log2(v / tot) for v in cnt.values())

    H1 = H(c1, n1)
    H2_joint = H(c2, n2)
    H3_joint = H(c3, n3)
    h2 = max(0.0, H2_joint - H1)
    h3 = max(0.0, H3_joint - H2_joint)
    return H1, h2, h3, n1


def char_entropies_within_word(lines: List[List[str]]) -> Tuple[float, float, float, int]:
    """
    Computes character entropies (h1, h2, h3) strictly within words (using '^' start and '$' end),
    excluding inter-word space frequency dilution.
    """
    c1: Counter = Counter()
    c2_ctx: Counter = Counter()
    c2_full: Counter = Counter()
    c3_ctx: Counter = Counter()
    c3_full: Counter = Counter()
    n1 = n2 = n3 = 0

    for toks in lines:
        for t in toks:
            for ch in t:
                c1[ch] += 1
            n1 += len(t)

            w2 = "^" + t + "$"
            for i in range(len(w2) - 1):
                c2_ctx[w2[i]] += 1
                c2_full[w2[i : i + 2]] += 1
                n2 += 1

            w3 = "^^" + t + "$"
            for i in range(len(w3) - 2):
                c3_ctx[w3[i : i + 2]] += 1
                c3_full[w3[i : i + 3]] += 1
                n3 += 1

    def H(cnt: Counter, tot: int) -> float:
        if tot == 0:
            return 0.0
        return -sum((v / tot) * math.log2(v / tot) for v in cnt.values())

    h1 = H(c1, n1)
    h2 = max(0.0, H(c2_full, n2) - H(c2_ctx, n2))
    h3 = max(0.0, H(c3_full, n3) - H(c3_ctx, n3))
    return h1, h2, h3, n1


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
    num = dx2 = dy2 = 0.0
    for x, y in zip(xs, ys):
        dx = x - mx
        dy = y - my
        num += dx * dy
        dx2 += dx * dx
        dy2 += dy * dy
    den = math.sqrt(dx2 * dy2)
    return (num / den) if den > 1e-12 else 0.0


def boundary_mi(lines: List[List[str]], lag: int) -> float:
    cx: Counter = Counter()
    cy: Counter = Counter()
    cxy: Counter = Counter()
    n = 0
    for toks in lines:
        L = len(toks)
        for i in range(L - lag):
            a = toks[i][-1]
            b = toks[i + lag][0]
            cx[a] += 1
            cy[b] += 1
            cxy[(a, b)] += 1
            n += 1
    if n == 0:
        return 0.0
    mi = 0.0
    for (a, b), v in cxy.items():
        mi += (v / n) * math.log2((v * n) / (cx[a] * cy[b]))
    return max(0.0, mi)


def len_autocorr(lines: List[List[str]]) -> float:
    xs: List[float] = []
    ys: List[float] = []
    for toks in lines:
        for i in range(len(toks) - 1):
            xs.append(float(len(toks[i])))
            ys.append(float(len(toks[i + 1])))
    return pearson_corr(xs, ys)


def vertical_interior_rates(folio_lines: Dict[str, List[List[str]]]) -> Tuple[float, float]:
    ex = e1 = tot = 0
    for lines in folio_lines.values():
        fl = [ln for ln in lines if len(ln) >= 3]
        for li in range(1, len(fl)):
            prev = fl[li - 1]
            curr = fl[li]
            lp, lc = len(prev), len(curr)
            for i in range(1, lc - 1):
                tok = curr[i]
                proj = round(i * (lp - 1) / (lc - 1))
                lo = max(0, proj - 1)
                hi = min(lp, proj + 2)
                has_ex = False
                has_e1 = False
                for j in range(lo, hi):
                    o = prev[j]
                    if o == tok:
                        has_ex = True
                        has_e1 = True
                        break
                    if not has_e1 and is_edit_le_1(tok, o):
                        has_e1 = True
                tot += 1
                if has_ex:
                    ex += 1
                if has_e1:
                    e1 += 1
    if tot == 0:
        return 0.0, 0.0
    return ex / tot * 100.0, e1 / tot * 100.0


def win5_rates(folio_lines: Dict[str, List[List[str]]]) -> Tuple[float, float]:
    ex = e1 = tot = 0
    for lines in folio_lines.values():
        seq = [t for ln in lines for t in ln]
        n = len(seq)
        for i, tok in enumerate(seq):
            lo = max(0, i - 5)
            hi = min(n, i + 6)
            has_ex = False
            has_e1 = False
            for j in range(lo, hi):
                if j == i:
                    continue
                o = seq[j]
                if o == tok:
                    has_ex = True
                    has_e1 = True
                    break
                if not has_e1 and is_edit_le_1(tok, o):
                    has_e1 = True
            tot += 1
            if has_ex:
                ex += 1
            if has_e1:
                e1 += 1
    if tot == 0:
        return 0.0, 0.0
    return ex / tot * 100.0, e1 / tot * 100.0


def adjacent_folio_jaccard(folio_order: List[str], folio_lines: Dict[str, List[List[str]]]) -> float:
    sets = [set(t for ln in folio_lines[f] for t in ln) for f in folio_order if folio_lines.get(f)]
    if len(sets) < 2:
        return 0.0
    vals = []
    for i in range(len(sets) - 1):
        u = len(sets[i] | sets[i + 1])
        if u > 0:
            vals.append(len(sets[i] & sets[i + 1]) / u)
    return statistics.mean(vals) if vals else 0.0


def evaluate_corpus(
    folio_order: List[str],
    folio_lines: Dict[str, List[List[str]]],
    rng: random.Random,
    shuffles: int = 6,
) -> Dict[str, float]:
    all_lines = [ln for f in folio_order for ln in folio_lines[f]]
    all_toks = [t for ln in all_lines for t in ln]
    ttr = len(set(all_toks)) / len(all_toks) if all_toks else 0.0

    h1_s, h2_s, h3_s, _ = char_entropies_stream(all_lines)
    _, h2_w, _, _ = char_entropies_within_word(all_lines)

    mi1_obs = boundary_mi(all_lines, 1)
    mi2_obs = boundary_mi(all_lines, 2)
    lr_obs = len_autocorr(all_lines)
    vx_obs, ve1_obs = vertical_interior_rates(folio_lines)
    w5_ex, w5_e1 = win5_rates(folio_lines)
    adj_jac = adjacent_folio_jaccard(folio_order, folio_lines)

    null_mi1, null_mi2, null_lr, null_vx, null_ve1 = [], [], [], [], []
    for _ in range(shuffles):
        sh_map: Dict[str, List[List[str]]] = {}
        sh_lines: List[List[str]] = []
        for f in folio_order:
            fl = []
            for ln in folio_lines[f]:
                cp = ln[:]
                rng.shuffle(cp)
                fl.append(cp)
                sh_lines.append(cp)
            sh_map[f] = fl
        null_mi1.append(boundary_mi(sh_lines, 1))
        null_mi2.append(boundary_mi(sh_lines, 2))
        null_lr.append(len_autocorr(sh_lines))
        nvx, nve1 = vertical_interior_rates(sh_map)
        null_vx.append(nvx)
        null_ve1.append(nve1)

    return {
        "h1": h1_s,
        "h2": h2_s,
        "h3": h3_s,
        "h2_word": h2_w,
        "TTR": ttr,
        "MI1": mi1_obs - statistics.mean(null_mi1),
        "MI2": mi2_obs - statistics.mean(null_mi2),
        "len_r": lr_obs - statistics.mean(null_lr),
        "VertEx": vx_obs - statistics.mean(null_vx),
        "VertE1": ve1_obs - statistics.mean(null_ve1),
        "W5_Ex": w5_ex,
        "W5_E1": w5_e1,
        "AdjJac": adj_jac,
    }


class CharNGramModel:
    """Order-K character language model with backoff to K-1 .. 1 (space included)."""

    def __init__(self, order: int) -> None:
        self.order = order
        self.tables: Dict[int, Dict[str, Tuple[List[str], List[int]]]] = {}

    def fit(self, lines: List[List[str]]) -> None:
        raw: Dict[int, Dict[str, Counter]] = {k: defaultdict(Counter) for k in range(1, self.order + 1)}
        for toks in lines:
            if not toks:
                continue
            s = "^" * self.order + " ".join(toks) + "$"
            for i in range(self.order, len(s)):
                ch = s[i]
                for k in range(1, self.order + 1):
                    raw[k][s[i - k : i]][ch] += 1
        for k in range(1, self.order + 1):
            self.tables[k] = {ctx: (list(cnt.keys()), list(cnt.values())) for ctx, cnt in raw[k].items()}

    def sample_next(self, ctx: str, rng: random.Random) -> str:
        for k in range(self.order, 0, -1):
            sub = ctx[-k:]
            entry = self.tables[k].get(sub)
            if entry is not None:
                ks, ws = entry
                return rng.choices(ks, weights=ws, k=1)[0]
        return "$"

    def generate_line(self, n_toks: int, rng: random.Random) -> List[str]:
        if n_toks <= 0:
            return []
        for _ in range(40):
            s = "^" * self.order
            while len(s) < self.order + 600:
                c = self.sample_next(s, rng)
                if c == "$":
                    break
                s += c
            toks = s[self.order :].split()
            if len(toks) >= n_toks:
                return toks[:n_toks]
        out: List[str] = []
        while len(out) < n_toks:
            s = "^" * self.order
            while len(s) < self.order + 200:
                c = self.sample_next(s, rng)
                if c == "$":
                    break
                s += c
            out.extend(s[self.order :].split())
        return out[:n_toks]


def mutate_edit1_weighted(word: str, chars: List[str], weights: List[int], rng: random.Random) -> str:
    r = rng.random()
    if r < 0.55 and len(word) >= 2:
        i = rng.randrange(len(word))
        return word[:i] + rng.choices(chars, weights=weights, k=1)[0] + word[i + 1 :]
    if r < 0.80:
        i = rng.randrange(len(word) + 1)
        return word[:i] + rng.choices(chars, weights=weights, k=1)[0] + word[i:]
    if len(word) >= 3:
        i = rng.randrange(len(word))
        return word[:i] + word[i + 1 :]
    return word


def generate_hybrid_corpus(
    folio_order: List[str],
    folio_shape: Dict[str, List[int]],
    folio_group: Dict[str, str],
    models: Dict[str, CharNGramModel],
    fallback_model: CharNGramModel,
    chars: List[str],
    char_weights: List[int],
    p_vert: float,
    p_topic: float,
    topic_pool_size: int,
    rng: random.Random,
) -> Dict[str, List[List[str]]]:
    """
    Generates a synthetic corpus with exact folio/line-length geometry:
      - Base lines from order-K character stream (space included) trained per group.
      - Optional synthetic folio-topic cache (drawn purely from the group's own generator,
        zero leakage from real folio tokens) injected as exact topical repeats with prob p_topic.
      - Optional 2D vertical column memory (1-3 lines above, proportional Col +/-1)
        with probability p_vert (40% exact copy, 60% weighted Edit<=1 mutation).
    """
    out: Dict[str, List[List[str]]] = {}
    for f in folio_order:
        grp = folio_group[f]
        mdl = models.get(grp, fallback_model)
        lens = folio_shape[f]

        # Build purely synthetic folio topic cache (no real folio vocabulary used)
        topic_cache: List[str] = []
        if p_topic > 0.0 and topic_pool_size > 0:
            while len(topic_cache) < topic_pool_size:
                topic_cache.extend(mdl.generate_line(8, rng))
            topic_cache = topic_cache[:topic_pool_size]

        folio_out: List[List[str]] = []
        for n_toks in lens:
            line = mdl.generate_line(n_toks, rng)

            # Inject synthetic folio-topic words (clean exact topical reuse)
            if topic_cache and p_topic > 0.0:
                for i in range(len(line)):
                    if rng.random() < p_topic:
                        line[i] = rng.choice(topic_cache)

            # Apply 2D vertical column memory from 1..3 lines above
            if p_vert > 0.0 and folio_out and len(line) >= 3:
                lc = len(line)
                for i in range(1, lc - 1):
                    if rng.random() < p_vert:
                        r_lag = rng.random()
                        lag = 1 if r_lag < 0.60 else (2 if r_lag < 0.85 else 3)
                        if len(folio_out) >= lag and len(folio_out[-lag]) >= 2:
                            prev = folio_out[-lag]
                            lp = len(prev)
                            proj = round(i * (lp - 1) / (lc - 1))
                            lo = max(0, proj - 1)
                            hi = min(lp - 1, proj + 1)
                            src = prev[rng.randint(lo, hi)]
                            if rng.random() < 0.40:
                                line[i] = src
                            else:
                                line[i] = mutate_edit1_weighted(src, chars, char_weights, rng)

            folio_out.append(line)
        out[f] = folio_out
    return out


def part1_entropy_profile(zl_entries: List[LineEntry], rf_entries: List[LineEntry]) -> None:
    print("=== PART 1: CONDITIONAL CHARACTER ENTROPY PROFILE (h1, h2, h3 — EMPTY CORNER) ===")
    print("  Stream mode includes space (' ') as an explicit character (standard Voynich h2 benchmark).")
    print("  Word mode uses explicit ^word$ boundaries without inter-word space dilution.\n")
    print("  Subset          |  Lines |  Tokens |  Chars | h1_str | h2_str | h3_str | h2_word |    TTR")
    print("  ------------------------------------------------------------------------------------------")

    def report(label: str, subset: List[LineEntry]) -> None:
        lines = [e.tokens for e in subset]
        toks = [t for ln in lines for t in ln]
        if not toks:
            return
        h1_s, h2_s, h3_s, n_ch = char_entropies_stream(lines)
        _, h2_w, _, _ = char_entropies_within_word(lines)
        ttr = len(set(toks)) / len(toks)
        print(
            f"  {label:<15} | {len(lines):6d} | {len(toks):7d} | {n_ch:6d} | "
            f"{h1_s:6.3f} | {h2_s:6.3f} | {h3_s:6.3f} | {h2_w:7.3f} | {ttr:6.4f}"
        )

    report("ALL (ZL3b-n)", zl_entries)
    for cur in ("A", "B"):
        report(f"Currier {cur}", [e for e in zl_entries if e.currier == cur])
    report("Currier OTHER", [e for e in zl_entries if e.currier not in ("A", "B")])
    print("  ------------------------------------------------------------------------------------------")
    for sec in ("H", "B", "P", "S", "T", "A", "Z", "C"):
        sub = [e for e in zl_entries if e.section == sec]
        if sub:
            report(f"Section {sec}", sub)
    if rf_entries:
        print("  ------------------------------------------------------------------------------------------")
        report("ALL (RF1b-e)", rf_entries)
    print()


def part2_empty_corner_benchmark(zl_entries: List[LineEntry]) -> None:
    print("=== PART 2: EMPTY CORNER GENERATIVE BENCHMARK (ZERO FOLIO LEAKAGE) ===")
    print("  All models match exact folio & line-length geometry; MI/len_r/Vert net over 6 line shuffles.\n")

    folio_order: List[str] = []
    folio_lines: Dict[str, List[List[str]]] = defaultdict(list)
    folio_cur: Dict[str, str] = {}
    folio_sec_cur: Dict[str, str] = {}

    for e in zl_entries:
        if e.folio not in folio_lines:
            folio_order.append(e.folio)
            cur = e.currier if e.currier in ("A", "B") else "OTHER"
            folio_cur[e.folio] = cur
            folio_sec_cur[e.folio] = f"{e.section}:{cur}"
        folio_lines[e.folio].append(e.tokens)

    folio_shape = {f: [len(ln) for ln in folio_lines[f]] for f in folio_order}
    all_lines = [ln for f in folio_order for ln in folio_lines[f]]
    ch_counts = Counter(ch for ln in all_lines for t in ln for ch in t)
    chars = list(ch_counts.keys())
    char_weights = list(ch_counts.values())

    m3_global = CharNGramModel(3)
    m3_global.fit(all_lines)

    by_cur: Dict[str, List[List[str]]] = defaultdict(list)
    by_sc: Dict[str, List[List[str]]] = defaultdict(list)
    for f in folio_order:
        by_cur[folio_cur[f]].extend(folio_lines[f])
        by_sc[folio_sec_cur[f]].extend(folio_lines[f])

    m3_cur: Dict[str, CharNGramModel] = {}
    for k, ls in by_cur.items():
        m = CharNGramModel(3)
        m.fit(ls)
        m3_cur[k] = m

    m3_sc: Dict[str, CharNGramModel] = {}
    m4_sc: Dict[str, CharNGramModel] = {}
    for k, ls in by_sc.items():
        if len(ls) >= 20:
            m3 = CharNGramModel(3)
            m3.fit(ls)
            m3_sc[k] = m3
            m4 = CharNGramModel(4)
            m4.fit(ls)
            m4_sc[k] = m4

    m4_global = CharNGramModel(4)
    m4_global.fit(all_lines)

    rng = random.Random(2026)

    candidates = [
        ("REAL (ZL3b-n)", folio_lines),
        (
            "Char-3 Global (1D)",
            generate_hybrid_corpus(
                folio_order, folio_shape, {f: "G" for f in folio_order},
                {"G": m3_global}, m3_global, chars, char_weights,
                p_vert=0.0, p_topic=0.0, topic_pool_size=0, rng=rng
            ),
        ),
        (
            "Hyb Currier Char-3 + 2D(3.5%)",
            generate_hybrid_corpus(
                folio_order, folio_shape, folio_cur,
                m3_cur, m3_global, chars, char_weights,
                p_vert=0.035, p_topic=0.0, topic_pool_size=0, rng=rng
            ),
        ),
        (
            "Hyb Sec+Cur Char-3 + 2D(3.5%)",
            generate_hybrid_corpus(
                folio_order, folio_shape, folio_sec_cur,
                m3_sc, m3_global, chars, char_weights,
                p_vert=0.035, p_topic=0.0, topic_pool_size=0, rng=rng
            ),
        ),
        (
            "Hyb Sec+Cur Char-4 + 2D(3.5%)",
            generate_hybrid_corpus(
                folio_order, folio_shape, folio_sec_cur,
                m4_sc, m4_global, chars, char_weights,
                p_vert=0.035, p_topic=0.0, topic_pool_size=0, rng=rng
            ),
        ),
        (
            "Hyb SC Char-4 + 2D + Topic(20%)",
            generate_hybrid_corpus(
                folio_order, folio_shape, folio_sec_cur,
                m4_sc, m4_global, chars, char_weights,
                p_vert=0.035, p_topic=0.20, topic_pool_size=30, rng=rng
            ),
        ),
    ]

    print(
        "  Model                            |   h1  |   h2  |   h3  |   TTR  |   MI1  |  len_r | VertEx | VertE1 | W5_Ex | W5_E1 | AdjJac"
    )
    print("  " + "-" * 127)
    for name, cmap in candidates:
        m = evaluate_corpus(folio_order, cmap, rng=rng, shuffles=6)
        print(
            f"  {name:<32} | {m['h1']:5.3f} | {m['h2']:5.3f} | {m['h3']:5.3f} | {m['TTR']:6.4f} | "
            f"{m['MI1']:+6.3f} | {m['len_r']:+6.3f} | {m['VertEx']:+6.2f} | {m['VertE1']:+6.2f} | "
            f"{m['W5_Ex']:5.1f} | {m['W5_E1']:5.1f} | {m['AdjJac']:6.4f}"
        )
    print("\n  Note: Topic(20%) builds a purely synthetic 30-word page cache sampled from the generator itself")
    print("        (zero memorization of real folio vocabulary) to test whether topicality closes W5 & TTR.\n")


def main() -> None:
    zl_path = sys.argv[1] if len(sys.argv) > 1 else "ZL3b-n.txt"
    rf_path = sys.argv[2] if len(sys.argv) > 2 else "RF1b-e.txt"

    print("==========================================================================")
    print("VOYNICH h2 ENTROPY & EMPTY CORNER BENCHMARK (v3.1 — NO SEMANTIC LABELS)")
    print("==========================================================================\n")

    zl_entries = parse_ivtff(zl_path)
    print(f"Loaded {len(zl_entries)} lines across {len({e.folio for e in zl_entries})} folios from {zl_path}.")

    rf_entries: List[LineEntry] = []
    try:
        rf_entries = parse_ivtff(rf_path)
        print(f"Loaded {len(rf_entries)} lines across {len({e.folio for e in rf_entries})} folios from {rf_path}.\n")
    except FileNotFoundError:
        print(f"[INFO] Secondary corpus {rf_path} not found; skipping RF1b-e parity row.\n")

    part1_entropy_profile(zl_entries, rf_entries)
    part2_empty_corner_benchmark(zl_entries)


if __name__ == "__main__":
    main()
