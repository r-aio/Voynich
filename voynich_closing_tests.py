#!/usr/bin/env python3
"""
Voynich Manuscript (MS 408) — Closing Falsification & Hybrid-Generator Suite (ZL3b-n.txt)
Zero external dependencies (Python 3.11 stdlib only). No L0-ISM / No semantic labels.

Executes all 3 remaining structural tests in one unified pass:
  TEST 1: Hybrid Generator Benchmark (Order-3 Char Stream + 2D Vertical Column Memory)
          - Compares REAL (ZL3b-n) against:
              (a) Global Order-3 Char Stream (1D, with space)
              (b) Per-Currier Order-3 Char Stream (1D, with space)
              (c) Hybrid Global Char-3 + 2D Col-Copy (p_vert = 1.5%, 3.0%)
              (d) Hybrid Per-Currier Char-3 + 2D Col-Copy (p_vert = 2.0%, 3.5%)
          - Evaluates MI lag-1, MI lag-2, Length r, Vertical Exact/Edit<=1 (interior,
            proportional col +/-1), +/-5 Window Exact/Edit<=1, and TTR (8 shuffle nulls).

  TEST 2: Length-Autocorrelation Conditioning Audit (DISSECT 3 conditioned on DISSECT 1)
          - Tests whether Lag-1 length autocorrelation is purely a byproduct of
            cross-space boundary pairs (last_char(i) -> first_char(i+1)) or survives
            after leave-one-out conditioning on 1-char / 2-char boundaries (with exact
            matched within-line shuffle nulls at every conditioning level) and inside
            fixed top boundary strata (y->q, r->a, n->c, n->o, l->c).

  TEST 3: Gallows Steganography Falsifier (Trop 3: k, p, t, f Stream Audit)
          - Measures entropy (H1, H2, H3), lag-1 MI, and repeat bias of gallows streams
            (all gallows, word-initial gallows, body-only gallows excluding top line).
          - Bounds per-folio information capacity in bits and plaintext-letter equivalents.
          - Tests the "non-gallows = random null filler" premise by stripping all gallows
            tokens and re-measuring cross-space MI, length r, and 2D alignment on residue.
"""

from __future__ import annotations

import bisect
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
    is_para_top: bool
    is_para_body: bool
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

            is_para_top = ("@P" in loc_id) or ("<%>" in body)
            is_para_body = ("+P" in loc_id or "*P" in loc_id or "=P" in loc_id) and not is_para_top

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
                    is_para_top=is_para_top,
                    is_para_body=is_para_body,
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
        diffs = 0
        for x, y in zip(a, b):
            if x != y:
                diffs += 1
                if diffs > 1:
                    return False
        return True
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


def mutual_info_bits(pairs: List[Tuple[str, str]]) -> float:
    n = len(pairs)
    if n == 0:
        return 0.0
    cx: Counter = Counter()
    cy: Counter = Counter()
    cxy: Counter = Counter()
    for x, y in pairs:
        cx[x] += 1
        cy[y] += 1
        cxy[(x, y)] += 1
    mi = 0.0
    for (x, y), obs in cxy.items():
        pxy = obs / n
        px = cx[x] / n
        py = cy[y] / n
        mi += pxy * math.log2(pxy / (px * py))
    return max(0.0, mi)


# ==============================================================================
# TEST 1: HYBRID GENERATOR BENCHMARK (CHAR ORDER-3 STREAM + 2D VERTICAL MEMORY)
# ==============================================================================

class FastCharMarkov:
    """Order-K character Markov model with cumulative weights for fast sampling."""

    def __init__(self, k: int = 3) -> None:
        self.k = k
        self.tables: Dict[str, Tuple[List[str], List[int], int]] = {}
        self.fallback_chars: List[str] = []
        self.fallback_cum: List[int] = []
        self.fallback_tot: int = 0

    def fit(self, lines: List[List[str]]) -> None:
        tr: Dict[str, Counter] = defaultdict(Counter)
        uni: Counter = Counter()
        k = self.k
        for toks in lines:
            if not toks:
                continue
            s = "^" * k + " ".join(toks) + "$"
            for i in range(k, len(s)):
                ctx = s[i - k : i]
                ch = s[i]
                tr[ctx][ch] += 1
                if ch != "$":
                    uni[ch] += 1

        for ctx, cnt in tr.items():
            chars = list(cnt.keys())
            cum: List[int] = []
            tot = 0
            for c in chars:
                tot += cnt[c]
                cum.append(tot)
            self.tables[ctx] = (chars, cum, tot)

        self.fallback_chars = list(uni.keys()) or ["a", "o", "y", " "]
        cum_u: List[int] = []
        tot_u = 0
        for c in self.fallback_chars:
            tot_u += uni.get(c, 1)
            cum_u.append(tot_u)
        self.fallback_cum = cum_u
        self.fallback_tot = tot_u

    def sample_next(self, ctx: str, rng: random.Random) -> str:
        tab = self.tables.get(ctx)
        if tab is not None:
            chars, cum, tot = tab
            r = rng.randrange(tot)
            return chars[bisect.bisect_right(cum, r)]
        r = rng.randrange(self.fallback_tot)
        return self.fallback_chars[bisect.bisect_right(self.fallback_cum, r)]

    def sample_next_token(self, prev_stream: str, rng: random.Random, max_len: int = 16) -> str:
        """Generates one non-empty token conditioned on the trailing K chars of prev_stream."""
        k = self.k
        for _ in range(12):
            buf = prev_stream[-k:]
            chars_out: List[str] = []
            for _step in range(max_len + 6):
                c = self.sample_next(buf, rng)
                if c in (" ", "$"):
                    if chars_out:
                        return "".join(chars_out)
                    buf = (buf + " ")[-k:]
                    continue
                chars_out.append(c)
                buf = (buf + c)[-k:]
                if len(chars_out) >= max_len:
                    return "".join(chars_out)
            if chars_out:
                return "".join(chars_out)
        return "daiin"


def mutate_edit1(word: str, alpha: List[str], rng: random.Random) -> str:
    """Applies a single character edit (sub/ins/del) mimicking scribal drift."""
    r = rng.random()
    lw = len(word)
    if r < 0.55 and lw >= 1:
        idx = rng.randrange(lw)
        ch = rng.choice(alpha)
        return word[:idx] + ch + word[idx + 1 :]
    if r < 0.80 and lw <= 10:
        idx = rng.randrange(lw + 1)
        ch = rng.choice(alpha)
        return word[:idx] + ch + word[idx:]
    if lw >= 3:
        idx = rng.randrange(lw)
        return word[:idx] + word[idx + 1 :]
    return word


def generate_hybrid_corpus(
    real_by_folio: Dict[str, List[List[str]]],
    folio_currier: Dict[str, str],
    models: Dict[str, FastCharMarkov],
    alpha: List[str],
    p_vert: float,
    p_exact_given_vert: float,
    use_currier: bool,
    seed: int,
) -> Dict[str, List[List[str]]]:
    """
    Generates a synthetic corpus matching exact folio & line-length geometry:
      - Generates token-by-token using order-3 char Markov stream (including space).
      - With probability p_vert (for line_idx >= 1), glances vertically 1-3 lines above
        at proportional column +/-1 (lag weights: 55% k-1, 30% k-2, 15% k-3), copying
        either exact token (p_exact_given_vert) or an Edit=1 variant, then feeds the
        copied token back into the char-stream context so right-side boundaries stay coupled.
    """
    rng = random.Random(seed)
    out: Dict[str, List[List[str]]] = {}

    for fid, real_lines in real_by_folio.items():
        cur_key = folio_currier.get(fid, "OTHER") if use_currier else "GLOBAL"
        model = models.get(cur_key, models["GLOBAL"])
        gen_lines: List[List[str]] = []

        for li, rline in enumerate(real_lines):
            n_toks = len(rline)
            line_out: List[str] = []
            stream = "^^^"

            for j in range(n_toks):
                copied = None
                if p_vert > 0.0 and li >= 1 and rng.random() < p_vert:
                    max_lag = min(3, li)
                    if max_lag == 1:
                        lag = 1
                    elif max_lag == 2:
                        lag = 1 if rng.random() < 0.65 else 2
                    else:
                        u = rng.random()
                        lag = 1 if u < 0.55 else (2 if u < 0.85 else 3)

                    prev_line = gen_lines[li - lag]
                    lp = len(prev_line)
                    if lp > 0:
                        proj = round(j * (lp - 1) / (n_toks - 1)) if n_toks > 1 else 0
                        lo = max(0, proj - 1)
                        hi = min(lp - 1, proj + 1)
                        src = prev_line[rng.randint(lo, hi)]
                        if rng.random() < p_exact_given_vert:
                            copied = src
                        else:
                            copied = mutate_edit1(src, alpha, rng)

                if copied is not None:
                    tok = copied
                else:
                    tok = model.sample_next_token(stream, rng)

                line_out.append(tok)
                stream = (stream + tok + " ")[-6:]

            gen_lines.append(line_out)
        out[fid] = gen_lines

    return out


def eval_corpus_suite(
    flines: Dict[str, List[List[str]]], trials: int = 8, seed: int = 408
) -> Dict[str, float]:
    """Computes MI1/MI2 net, len_r net, interior vertical Exact/Edit<=1 net, Win5, and TTR."""
    rng = random.Random(seed)
    all_lines = [ln for ls in flines.values() for ln in ls]
    all_toks = [t for ln in all_lines for t in ln]
    ttr = len(set(all_toks)) / len(all_toks) if all_toks else 0.0

    def lag_mi(lines_list: List[List[str]], lag: int) -> float:
        ps = [(ln[i][-1], ln[i + lag][0]) for ln in lines_list for i in range(len(ln) - lag)]
        return mutual_info_bits(ps)

    def line_len_r(lines_list: List[List[str]]) -> float:
        xs: List[float] = []
        ys: List[float] = []
        for ln in lines_list:
            for i in range(len(ln) - 1):
                xs.append(float(len(ln[i])))
                ys.append(float(len(ln[i + 1])))
        return pearson_corr(xs, ys)

    def vert_interior(fmap: Dict[str, List[List[str]]]) -> Tuple[float, float]:
        ex = e1 = tot = 0
        for ls in fmap.values():
            valid = [ln for ln in ls if len(ln) >= 3]
            for li in range(1, len(valid)):
                prev = valid[li - 1]
                curr = valid[li]
                lp, lc = len(prev), len(curr)
                for i in range(1, lc - 1):
                    tok = curr[i]
                    proj = round(i * (lp - 1) / (lc - 1))
                    lo = max(0, proj - 1)
                    hi = min(lp, proj + 2)
                    got_ex = False
                    got_e1 = False
                    for j in range(lo, hi):
                        other = prev[j]
                        if other == tok:
                            got_ex = True
                            got_e1 = True
                            break
                        if not got_e1 and is_edit_le_1(tok, other):
                            got_e1 = True
                    tot += 1
                    if got_ex:
                        ex += 1
                    if got_e1:
                        e1 += 1
        return (ex / tot * 100.0 if tot else 0.0), (e1 / tot * 100.0 if tot else 0.0)

    def win5_rates(fmap: Dict[str, List[List[str]]]) -> Tuple[float, float]:
        ex = e1 = tot = 0
        for ls in fmap.values():
            seq = [t for ln in ls for t in ln]
            n = len(seq)
            for i, tok in enumerate(seq):
                lo = max(0, i - 5)
                hi = min(n, i + 6)
                got_ex = False
                got_e1 = False
                for j in range(lo, hi):
                    if j == i:
                        continue
                    other = seq[j]
                    if other == tok:
                        got_ex = True
                        got_e1 = True
                        break
                    if not got_e1 and is_edit_le_1(tok, other):
                        got_e1 = True
                tot += 1
                if got_ex:
                    ex += 1
                if got_e1:
                    e1 += 1
        return (ex / tot * 100.0 if tot else 0.0), (e1 / tot * 100.0 if tot else 0.0)

    obs_mi1 = lag_mi(all_lines, 1)
    obs_mi2 = lag_mi(all_lines, 2)
    obs_lenr = line_len_r(all_lines)
    obs_vex, obs_ve1 = vert_interior(flines)
    w5_ex, w5_e1 = win5_rates(flines)

    n_mi1: List[float] = []
    n_mi2: List[float] = []
    n_lenr: List[float] = []
    n_vex: List[float] = []
    n_ve1: List[float] = []

    for _ in range(trials):
        shuf_fmap: Dict[str, List[List[str]]] = {}
        shuf_lines: List[List[str]] = []
        for fid, ls in flines.items():
            new_ls = []
            for ln in ls:
                cp = ln[:]
                rng.shuffle(cp)
                new_ls.append(cp)
                shuf_lines.append(cp)
            shuf_fmap[fid] = new_ls
        n_mi1.append(lag_mi(shuf_lines, 1))
        n_mi2.append(lag_mi(shuf_lines, 2))
        n_lenr.append(line_len_r(shuf_lines))
        ve, v1 = vert_interior(shuf_fmap)
        n_vex.append(ve)
        n_ve1.append(v1)

    return {
        "MI1": obs_mi1 - statistics.mean(n_mi1),
        "MI2": obs_mi2 - statistics.mean(n_mi2),
        "len_r": obs_lenr - statistics.mean(n_lenr),
        "vert_ex_pp": obs_vex - statistics.mean(n_vex),
        "vert_e1_pp": obs_ve1 - statistics.mean(n_ve1),
        "win5_ex": w5_ex,
        "win5_e1": w5_e1,
        "ttr": ttr,
    }


def run_test1_hybrid_generators(entries: List[LineEntry]) -> None:
    print("=== TEST 1: HYBRID GENERATOR BENCHMARK (CHAR ORDER-3 + 2D VERTICAL MEMORY) ===")
    print("All models match exact folio/line-length geometry; net metrics over 8 within-line shuffles.\n")

    real_by_folio: Dict[str, List[List[str]]] = defaultdict(list)
    folio_currier: Dict[str, str] = {}
    lines_by_cur: Dict[str, List[List[str]]] = defaultdict(list)

    for e in entries:
        cur = e.currier if e.currier in ("A", "B") else "OTHER"
        real_by_folio[e.folio].append(e.tokens)
        folio_currier[e.folio] = cur
        lines_by_cur[cur].append(e.tokens)
        lines_by_cur["GLOBAL"].append(e.tokens)

    all_chars = sorted({c for e in entries for t in e.tokens for c in t})

    models: Dict[str, FastCharMarkov] = {}
    for key, ls in lines_by_cur.items():
        m = FastCharMarkov(k=3)
        m.fit(ls)
        models[key] = m

    configs = [
        ("REAL (ZL3b-n)", None),
        ("Char-3 Global (1D, p_vert=0.0%)", (0.000, 0.40, False, 101)),
        ("Char-3 Per-Currier (1D, p_vert=0.0%)", (0.000, 0.40, True, 102)),
        ("Hybrid Global Char-3 + 2D (p=1.5%)", (0.015, 0.40, False, 103)),
        ("Hybrid Global Char-3 + 2D (p=3.0%)", (0.030, 0.40, False, 104)),
        ("Hybrid Currier Char-3 + 2D (p=2.0%)", (0.020, 0.35, True, 105)),
        ("Hybrid Currier Char-3 + 2D (p=3.5%)", (0.035, 0.35, True, 106)),
    ]

    print(
        f"  {'Model':<38} | {'MI1':>6} | {'MI2':>6} | {'len_r':>6} | "
        f"{'VertEx':>7} | {'VertE1':>7} | {'W5_Ex':>5} | {'W5_E1':>5} | {'TTR':>6}"
    )
    print("  " + "-" * 107)

    for name, cfg in configs:
        if cfg is None:
            flines = real_by_folio
        else:
            p_v, p_ex, use_c, sd = cfg
            flines = generate_hybrid_corpus(
                real_by_folio, folio_currier, models, all_chars, p_v, p_ex, use_c, sd
            )
        res = eval_corpus_suite(flines, trials=8, seed=408)
        print(
            f"  {name:<38} | {res['MI1']:+6.3f} | {res['MI2']:+6.3f} | {res['len_r']:+6.3f} | "
            f"{res['vert_ex_pp']:+6.2f} | {res['vert_e1_pp']:+6.2f} | "
            f"{res['win5_ex']:5.1f} | {res['win5_e1']:5.1f} | {res['ttr']:6.4f}"
        )
    print("  Note: VertEx / VertE1 are net pp excess on interior tokens (Proportional Col +/-1 vs LineShuf).\n")


# ==============================================================================
# TEST 2: LENGTH-AUTOCORRELATION CONDITIONING AUDIT (DISSECT 3 vs. DISSECT 1)
# ==============================================================================

def loo_residuals(vals: List[float], keys: List[object], min_group: int = 3) -> List[float]:
    """Leave-one-out group mean centering to prevent finite-sample overfitting."""
    sums: Dict[object, float] = defaultdict(float)
    cnts: Dict[object, int] = defaultdict(int)
    for v, k in zip(vals, keys):
        sums[k] += v
        cnts[k] += 1
    gmean = statistics.mean(vals) if vals else 0.0
    out: List[float] = []
    for v, k in zip(vals, keys):
        c = cnts[k]
        if c >= min_group:
            mu = (sums[k] - v) / (c - 1)
        else:
            mu = gmean
        out.append(v - mu)
    return out


def run_test2_length_conditioning(entries: List[LineEntry]) -> None:
    print("=== TEST 2: LENGTH-AUTOCORRELATION CONDITIONING ON BOUNDARY PAIRS ===")
    print("Tests if Lag-1 length correlation is purely a byproduct of End(i)->Start(i+1) rules.\n")

    def pos_bucket(idx: int, length: int) -> str:
        if length <= 1:
            return "SINGLE"
        if idx == 0:
            return "INIT"
        if idx == length - 1:
            return "FINAL"
        rel = idx / (length - 1)
        return f"MID_{min(4, int(rel * 5))}"

    def compute_conditioning_vector(
        line_tuples: List[Tuple[str, str, List[str]]]
    ) -> Tuple[Dict[str, float], List[Tuple[str, str]], List[float], List[float], List[float], List[float]]:
        """
        Computes all 6 Lag-1 length correlation levels on a list of (folio, currier, tokens):
          - raw: raw lengths (L1, L2)
          - pf:  properly centered Pos + Folio detrended (zero folio mean + zero currier-pos offset)
          - m1:  pf conditioned on marginal 1-char boundary (L1|end1, L2|start2)
          - j1:  pf conditioned on joint 1-char boundary pair (end1, start2)
          - m2:  pf conditioned on marginal 2-char affixes (L1|suf2, L2|pre2)
          - j2:  pf conditioned on joint 2-char boundary pair (suf2, pre2)
        """
        bucket_lens: Dict[Tuple[str, str], List[int]] = defaultdict(list)
        cur_lens: Dict[str, List[int]] = defaultdict(list)
        folio_lens: Dict[str, List[int]] = defaultdict(list)
        for fid, cur, toks in line_tuples:
            n = len(toks)
            for i, t in enumerate(toks):
                lt = len(t)
                bucket_lens[(cur, pos_bucket(i, n))].append(lt)
                cur_lens[cur].append(lt)
                folio_lens[fid].append(lt)

        cur_mean = {k: statistics.mean(v) for k, v in cur_lens.items()}
        # Pure within-Currier positional offset (zero-mean within each Currier style)
        pos_offset = {
            (c, b): statistics.mean(v) - cur_mean[c] for (c, b), v in bucket_lens.items()
        }
        folio_mean = {k: statistics.mean(v) for k, v in folio_lens.items()}

        l1_raw: List[float] = []
        l2_raw: List[float] = []
        r1_pf: List[float] = []
        r2_pf: List[float] = []
        c1_end: List[object] = []
        c2_start: List[object] = []
        pair_1c: List[object] = []
        pair_1c_typed: List[Tuple[str, str]] = []
        s1_suf2: List[object] = []
        s2_pre2: List[object] = []
        pair_2c: List[object] = []

        for fid, cur, toks in line_tuples:
            n = len(toks)
            if n < 2:
                continue
            fm = folio_mean[fid]
            res = [len(t) - fm - pos_offset[(cur, pos_bucket(i, n))] for i, t in enumerate(toks)]
            for i in range(n - 1):
                w1, w2 = toks[i], toks[i + 1]
                l1_raw.append(float(len(w1)))
                l2_raw.append(float(len(w2)))
                r1_pf.append(res[i])
                r2_pf.append(res[i + 1])
                c1_end.append((cur, w1[-1]))
                c2_start.append((cur, w2[0]))
                p1 = (w1[-1], w2[0])
                pair_1c.append((cur, w1[-1], w2[0]))
                pair_1c_typed.append(p1)
                s1_suf2.append((cur, w1[-2:]))
                s2_pre2.append((cur, w2[:2]))
                pair_2c.append((cur, w1[-2:], w2[:2]))

        r1_m1 = loo_residuals(r1_pf, c1_end, min_group=3)
        r2_m1 = loo_residuals(r2_pf, c2_start, min_group=3)

        r1_j1 = loo_residuals(r1_pf, pair_1c, min_group=5)
        r2_j1 = loo_residuals(r2_pf, pair_1c, min_group=5)

        r1_m2 = loo_residuals(r1_pf, s1_suf2, min_group=5)
        r2_m2 = loo_residuals(r2_pf, s2_pre2, min_group=5)

        r1_j2 = loo_residuals(r1_pf, pair_2c, min_group=5)
        r2_j2 = loo_residuals(r2_pf, pair_2c, min_group=5)

        stats_out = {
            "raw": pearson_corr(l1_raw, l2_raw),
            "pf": pearson_corr(r1_pf, r2_pf),
            "m1": pearson_corr(r1_m1, r2_m1),
            "j1": pearson_corr(r1_j1, r2_j1),
            "m2": pearson_corr(r1_m2, r2_m2),
            "j2": pearson_corr(r1_j2, r2_j2),
        }
        return stats_out, pair_1c_typed, l1_raw, l2_raw, r1_pf, r2_pf

    real_tuples = [
        (e.folio, (e.currier if e.currier in ("A", "B") else "OTHER"), e.tokens)
        for e in entries
    ]
    obs_vec, pair_1c_list, l1_raw, l2_raw, r1_pf, r2_pf = compute_conditioning_vector(real_tuples)

    # Exact matched within-line shuffle null across ALL conditioning levels (10 trials)
    rng = random.Random(408)
    null_vecs: Dict[str, List[float]] = defaultdict(list)
    for _ in range(10):
        shuf_tuples = []
        for fid, cur, toks in real_tuples:
            cp = toks[:]
            rng.shuffle(cp)
            shuf_tuples.append((fid, cur, cp))
        nv, _, _, _, _, _ = compute_conditioning_vector(shuf_tuples)
        for k, v in nv.items():
            null_vecs[k].append(v)

    base_net = obs_vec["pf"] - statistics.mean(null_vecs["pf"])

    print(f"  [2A. Progressive Conditioning of Lag-1 Length Autocorrelation (N = {len(l1_raw)} pairs)]")
    print("    Conditioning Level                           |  Obs r  | LineShuf |  Net r  |    Z   | Explained")
    print("    ------------------------------------------------------------------------------------------------")
    rows = [
        ("raw", "Raw Within-Line Lengths (L1, L2)"),
        ("pf", "Pos + Folio Detrended (baseline)"),
        ("m1", "+ Cond. Marginal 1-Char (L1|end1, L2|start2)"),
        ("j1", "+ Cond. Joint 1-Char Pair (end1, start2)"),
        ("m2", "+ Cond. Marginal 2-Char Affixes (suf2, pre2)"),
        ("j2", "+ Cond. Joint 2-Char Pair (suf2, pre2)"),
    ]
    for key, label in rows:
        obs_r = obs_vec[key]
        m_n, _, z_n = z_score(obs_r, null_vecs[key])
        net_r = obs_r - m_n
        if key in ("raw", "pf"):
            exp_s = "  (base)"
        else:
            exp_pct = ((base_net - net_r) / base_net * 100.0) if abs(base_net) > 1e-6 else 0.0
            exp_s = f"{exp_pct:6.1f}%"
        print(
            f"    {label:<44} | {obs_r:+7.4f} | {m_n:+8.4f} | {net_r:+7.4f} | {z_n:+6.2f} | {exp_s}"
        )

    # 2B. Direct within-stratum check inside the top 10 cross-space boundary pairs
    print("\n  [2B. Residual Length Correlation INSIDE Fixed Top Boundary Pairs (Pos+Folio Detrended)]")
    pair_counts = Counter(pair_1c_list)
    by_pair_xy: Dict[Tuple[str, str], Tuple[List[float], List[float], List[float], List[float]]] = defaultdict(
        lambda: ([], [], [], [])
    )
    for p, l1, l2, d1, d2 in zip(pair_1c_list, l1_raw, l2_raw, r1_pf, r2_pf):
        by_pair_xy[p][0].append(l1)
        by_pair_xy[p][1].append(l2)
        by_pair_xy[p][2].append(d1)
        by_pair_xy[p][3].append(d2)

    print("    Pair   |     N | MeanL1 -> MeanL2 |  Raw r | Detrended r")
    print("    --------------------------------------------------------")
    for p, cnt in pair_counts.most_common(10):
        lx, ly, dx, dy = by_pair_xy[p]
        print(
            f"    {p[0]} -> {p[1]} | {cnt:5d} |  {statistics.mean(lx):5.2f} -> {statistics.mean(ly):5.2f}  | "
            f"{pearson_corr(lx, ly):+6.4f} |    {pearson_corr(dx, dy):+6.4f}"
        )
    print()


# ==============================================================================
# TEST 3: GALLOWS STEGANOGRAPHY FALSIFIER (TROP 3: k, p, t, f STREAM AUDIT)
# ==============================================================================

def symbol_stream_stats(
    streams_by_folio: Dict[str, List[str]], trials: int = 15, seed: int = 2026
) -> Dict[str, float]:
    """Computes H1, cond H2, cond H3, lag-1 MI, repeat rate, and shuffle controls."""
    rng = random.Random(seed)
    all_syms = [s for seq in streams_by_folio.values() for s in seq]
    n_tot = len(all_syms)
    if n_tot < 20:
        return {
            "n": float(n_tot), "h1": 0.0, "h2": 0.0, "h3": 0.0,
            "mi1": 0.0, "mi1_null": 0.0, "mi1_z": 0.0,
            "rep": 0.0, "rep_null": 0.0, "rep_z": 0.0,
        }

    def entropies_and_mi(smap: Dict[str, List[str]]) -> Tuple[float, float, float, float, float]:
        u: Counter = Counter()
        bi: Counter = Counter()
        tri: Counter = Counter()
        pairs: List[Tuple[str, str]] = []
        tot_u = tot_b = tot_t = rep_c = 0
        for seq in smap.values():
            for s in seq:
                u[s] += 1
                tot_u += 1
            for i in range(len(seq) - 1):
                a, b = seq[i], seq[i + 1]
                bi[(a, b)] += 1
                pairs.append((a, b))
                tot_b += 1
                if a == b:
                    rep_c += 1
            for i in range(len(seq) - 2):
                tri[(seq[i], seq[i + 1], seq[i + 2])] += 1
                tot_t += 1
        h1 = -sum((c / tot_u) * math.log2(c / tot_u) for c in u.values()) if tot_u else 0.0
        hb = -sum((c / tot_b) * math.log2(c / tot_b) for c in bi.values()) if tot_b else 0.0
        ht = -sum((c / tot_t) * math.log2(c / tot_t) for c in tri.values()) if tot_t else 0.0
        h2 = max(0.0, hb - h1)
        h3 = max(0.0, ht - hb)
        mi1 = mutual_info_bits(pairs)
        rep = (rep_c / tot_b * 100.0) if tot_b else 0.0
        return h1, h2, h3, mi1, rep

    h1, h2, h3, mi1, rep = entropies_and_mi(streams_by_folio)
    null_mi: List[float] = []
    null_rep: List[float] = []
    for _ in range(trials):
        sh_map = {f: rng.sample(seq, len(seq)) for f, seq in streams_by_folio.items()}
        _, _, _, nmi, nrep = entropies_and_mi(sh_map)
        null_mi.append(nmi)
        null_rep.append(nrep)

    m_mi, _, z_mi = z_score(mi1, null_mi)
    m_rep, _, z_rep = z_score(rep, null_rep)
    return {
        "n": float(n_tot),
        "h1": h1,
        "h2": h2,
        "h3": h3,
        "mi1": mi1,
        "mi1_null": m_mi,
        "mi1_z": z_mi,
        "rep": rep,
        "rep_null": m_rep,
        "rep_z": z_rep,
    }


def run_test3_gallows_steganography(entries: List[LineEntry]) -> None:
    print("=== TEST 3: GALLOWS STEGANOGRAPHY FALSIFIER (TROP 3: k, p, t, f AUDIT) ===")
    GALLOWS = ("k", "p", "t", "f")
    GSET = set(GALLOWS)

    stream_all: Dict[str, List[str]] = defaultdict(list)
    stream_init: Dict[str, List[str]] = defaultdict(list)
    stream_body_all: Dict[str, List[str]] = defaultdict(list)
    stream_body_init: Dict[str, List[str]] = defaultdict(list)

    top_counts: Counter = Counter()
    body_counts: Counter = Counter()
    top_init_counts: Counter = Counter()
    body_init_counts: Counter = Counter()

    all_folios = sorted({e.folio for e in entries})

    for e in entries:
        for tok in e.tokens:
            gs = [ch for ch in tok if ch in GSET]
            if gs:
                stream_all[e.folio].extend(gs)
                if e.is_para_top:
                    top_counts.update(gs)
                elif e.is_para_body:
                    body_counts.update(gs)
                    stream_body_all[e.folio].extend(gs)
            if tok[0] in GSET:
                stream_init[e.folio].append(tok[0])
                if e.is_para_top:
                    top_init_counts[tok[0]] += 1
                elif e.is_para_body:
                    body_init_counts[tok[0]] += 1
                    stream_body_init[e.folio].append(tok[0])

    # 3A. Symbol composition collapse (Top-Line vs. Body)
    print("  [3A. Gallows Alphabet Share: Paragraph Top-Line vs. Body Lines]")
    for label, c_top, c_body in [
        ("Any-Position Gallows", top_counts, body_counts),
        ("Word-Initial Gallows", top_init_counts, body_init_counts),
    ]:
        tt = sum(c_top.values()) or 1
        tb = sum(c_body.values()) or 1
        s_top = "  ".join(f"{g}:{c_top[g]/tt*100:4.1f}%" for g in GALLOWS)
        s_bod = "  ".join(f"{g}:{c_body[g]/tb*100:4.1f}%" for g in GALLOWS)
        print(f"    {label:<22} Top-Line (N={sum(c_top.values()):4d}) : {s_top}")
        print(f"    {label:<22} Body     (N={sum(c_body.values()):4d}) : {s_bod}")

    # 3B. Entropy, sequential structure & per-folio bandwidth
    print("\n  [3B. Gallows Stream Entropy, Sequential MI & Per-Folio Information Capacity]")
    print(
        "    Stream                   |     N |   H1  |   H2  |   H3  |  MI1 (Null,   Z  ) | "
        "Rep% (Null,  Z  ) | MedBits/Fol | EqChars(2b)"
    )
    print("    " + "-" * 124)

    for label, smap in [
        ("All Gallows (any pos)", stream_all),
        ("Body-Only Gallows", stream_body_all),
        ("Word-Initial Gallows", stream_init),
        ("Body Word-Init Gallows", stream_body_init),
    ]:
        st = symbol_stream_stats(smap, trials=15, seed=2026)
        per_folio_counts = [len(smap.get(f, [])) for f in all_folios]
        med_cnt = statistics.median(per_folio_counts) if per_folio_counts else 0.0
        med_bits = med_cnt * st["h2"]
        eq_chars = med_bits / 2.0
        print(
            f"    {label:<24} | {int(st['n']):5d} | {st['h1']:5.3f} | {st['h2']:5.3f} | {st['h3']:5.3f} | "
            f"{st['mi1']:.4f} ({st['mi1_null']:.4f},{st['mi1_z']:+5.1f}) | "
            f"{st['rep']:4.1f} ({st['rep_null']:4.1f},{st['rep_z']:+5.1f}) | "
            f"{med_bits:11.1f} | {eq_chars:11.1f}"
        )

    # 3C. Null-Filler Falsification Check: Strip ALL gallows-containing tokens and audit residue
    print("\n  [3C. Null-Filler Falsification: Strip ALL Tokens Containing k/p/t/f & Audit Residue]")
    nongal_lines_by_folio: Dict[str, List[List[str]]] = defaultdict(list)
    nongal_lines_flat: List[List[str]] = []
    tot_toks = 0
    kept_toks = 0
    for e in entries:
        tot_toks += len(e.tokens)
        kept = [t for t in e.tokens if not any(ch in GSET for ch in t)]
        kept_toks += len(kept)
        if kept:
            nongal_lines_by_folio[e.folio].append(kept)
            nongal_lines_flat.append(kept)

    res_pairs = [(ln[i][-1], ln[i + 1][0]) for ln in nongal_lines_flat for i in range(len(ln) - 1)]
    res_mi = mutual_info_bits(res_pairs)
    res_lx = [float(len(ln[i])) for ln in nongal_lines_flat for i in range(len(ln) - 1)]
    res_ly = [float(len(ln[i + 1])) for ln in nongal_lines_flat for i in range(len(ln) - 1)]
    res_lenr = pearson_corr(res_lx, res_ly)

    def vert_e1(fmap: Dict[str, List[List[str]]]) -> float:
        e1 = tot = 0
        for ls in fmap.values():
            valid = [ln for ln in ls if len(ln) >= 3]
            for li in range(1, len(valid)):
                prev, curr = valid[li - 1], valid[li]
                lp, lc = len(prev), len(curr)
                for i in range(1, lc - 1):
                    tok = curr[i]
                    proj = round(i * (lp - 1) / (lc - 1))
                    lo, hi = max(0, proj - 1), min(lp, proj + 2)
                    tot += 1
                    if any(is_edit_le_1(tok, prev[j]) for j in range(lo, hi)):
                        e1 += 1
        return (e1 / tot * 100.0) if tot else 0.0

    obs_ve1 = vert_e1(nongal_lines_by_folio)

    rng = random.Random(303)
    null_rmi: List[float] = []
    null_rlen: List[float] = []
    null_rve1: List[float] = []
    for _ in range(12):
        sh_flat: List[List[str]] = []
        sh_map: Dict[str, List[List[str]]] = {}
        for fid, ls in nongal_lines_by_folio.items():
            nls = []
            for ln in ls:
                cp = ln[:]
                rng.shuffle(cp)
                nls.append(cp)
                sh_flat.append(cp)
            sh_map[fid] = nls
        sp = [(ln[i][-1], ln[i + 1][0]) for ln in sh_flat for i in range(len(ln) - 1)]
        null_rmi.append(mutual_info_bits(sp))
        sx = [float(len(ln[i])) for ln in sh_flat for i in range(len(ln) - 1)]
        sy = [float(len(ln[i + 1])) for ln in sh_flat for i in range(len(ln) - 1)]
        null_rlen.append(pearson_corr(sx, sy))
        null_rve1.append(vert_e1(sh_map))

    m_rmi, _, z_rmi = z_score(res_mi, null_rmi)
    m_rlen, _, z_rlen = z_score(res_lenr, null_rlen)
    m_rve1, _, z_rve1 = z_score(obs_ve1, null_rve1)

    print(f"    Gallows-Free Residue Tokens     : {kept_toks}/{tot_toks} ({kept_toks/tot_toks*100:.1f}% of corpus)")
    print(f"    Residue Cross-Space MI (Lag 1)  : {res_mi:.4f} bits | LineShuf={m_rmi:.4f} | Lift={res_mi-m_rmi:+.4f} | Z={z_rmi:+.2f}")
    print(f"    Residue Length Autocorr (Lag 1) : r = {res_lenr:+.4f} | LineShuf={m_rlen:+.4f} | Z={z_rlen:+.2f}")
    print(f"    Residue Vertical 2D Edit<=1     : {obs_ve1:5.2f}% | LineShuf={m_rve1:5.2f}% | Lift={obs_ve1-m_rve1:+.2f} pp | Z={z_rve1:+.2f}")
    print("    Note: If non-gallows residue retains strong MI, length coupling & 2D alignment,")
    print("          it cannot be dismissed as random syntactic null filler.\n")


def main() -> None:
    zl_path = sys.argv[1] if len(sys.argv) > 1 else "ZL3b-n.txt"
    print("==========================================================================")
    print("VOYNICH CLOSING TESTS: HYBRID 2D GENERATOR, LENGTH CONDITIONING & GALLOWS")
    print("==========================================================================\n")

    entries = parse_ivtff(zl_path)
    print(f"Loaded {len(entries)} lines across {len({e.folio for e in entries})} folios from {zl_path}.\n")

    run_test1_hybrid_generators(entries)
    run_test2_length_conditioning(entries)
    run_test3_gallows_steganography(entries)


if __name__ == "__main__":
    main()
