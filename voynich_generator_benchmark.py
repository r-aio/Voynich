#!/usr/bin/env python3
"""
L0-ISM v2.7 — Generative & Structural Benchmark Suite (ZL3b-n.txt vs. Controls)
Compares real ZL3b-n.txt folio/line streams against neutral synthetic generators
matched on folio line counts and line lengths (no semantic assumptions):
  1. real_zl3b             : actual normalized EVA token streams from ZL3b-n.txt
  2. gen_markov1_char      : character bigram Markov token generator (length-matched)
  3. gen_slot_template     : prefix + middle + suffix EVA slot generator
  4. gen_local_drift_table : folio-local pool with mild local reuse / drift in +/-5 window
  5. gen_folio_shuffle     : within-folio permutation control
"""

import random
import re
import statistics
import sys
from collections import Counter, defaultdict
from typing import Dict, List, Tuple

from voynich_ivtff_auditor import normalize_ivtff_line

PREFIXES: Tuple[str, ...] = ("qo", "ok", "ot", "yk", "yt", "ch", "sh", "ol", "or", "al", "ar", "")
MIDDLES: Tuple[str, ...] = ("k", "t", "p", "f", "ck", "ct", "ep", "e", "o", "a", "y", "")
SUFFIXES: Tuple[str, ...] = ("edy", "eedy", "aiin", "iin", "in", "dy", "ey", "ol", "or", "al", "ar", "y", "s", "")


def extract_folio_from_line(raw_line: str) -> str:
    m = re.match(r"^\s*#?\s*<(f[0-9]+[rv][0-9]*|fRos)(?:[.\s>])", raw_line, re.IGNORECASE)
    return m.group(1).lower() if m else ""


def load_lines_by_folio(filepath: str) -> Dict[str, List[List[str]]]:
    by_folio: Dict[str, List[List[str]]] = defaultdict(list)
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        for raw in f:
            fid = extract_folio_from_line(raw)
            if not fid:
                continue
            toks = normalize_ivtff_line(raw)
            if toks:
                by_folio[fid].append(toks)
    return by_folio


def build_char_bigram_model(tokens: List[str]) -> Tuple[Counter, Dict[str, Counter], List[int]]:
    starts: Counter = Counter()
    trans: Dict[str, Counter] = defaultdict(Counter)
    lengths: List[int] = []

    for tok in tokens:
        if not tok:
            continue
        lengths.append(len(tok))
        starts[tok[0]] += 1
        for i in range(len(tok) - 1):
            trans[tok[i]][tok[i + 1]] += 1
    return starts, trans, lengths


def sample_weighted(rng: random.Random, counter: Counter) -> str:
    items = list(counter.items())
    total = sum(w for _, w in items)
    if total <= 0:
        return "a"
    pick = rng.uniform(0, total)
    acc = 0.0
    for sym, w in items:
        acc += w
        if acc >= pick:
            return sym
    return items[-1][0]


def gen_markov1_token(
    rng: random.Random,
    starts: Counter,
    trans: Dict[str, Counter],
    target_len: int,
) -> str:
    if target_len <= 1:
        return sample_weighted(rng, starts)
    cur = sample_weighted(rng, starts)
    out = [cur]
    for _ in range(target_len - 1):
        nxt_pool = trans.get(cur)
        if nxt_pool:
            cur = sample_weighted(rng, nxt_pool)
        else:
            cur = sample_weighted(rng, starts)
        out.append(cur)
    return "".join(out)


def gen_slot_token(rng: random.Random, target_len: int) -> str:
    best = ""
    for _ in range(6):
        p = rng.choice(PREFIXES)
        m = rng.choice(MIDDLES)
        s = rng.choice(SUFFIXES)
        cand = p + m + s
        if not cand:
            cand = "ol"
        if not best or abs(len(cand) - target_len) < abs(len(best) - target_len):
            best = cand
    return best


def is_edit_le_1(a: str, b: str) -> bool:
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if la == lb:
        diffs = sum(1 for x, y in zip(a, b) if x != y)
        return diffs <= 1
    # Ensure a is shorter
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


def window_metrics(streams: List[List[str]], win_half: int = 5) -> Tuple[float, float]:
    exact_hits = 0
    edit1_hits = 0
    total = 0

    for seq in streams:
        n = len(seq)
        if n < 2:
            continue
        for i in range(n):
            lo = max(0, i - win_half)
            hi = min(n, i + win_half + 1)
            tok = seq[i]
            has_exact = False
            has_edit1 = False
            for j in range(lo, hi):
                if j == i:
                    continue
                other = seq[j]
                if other == tok:
                    has_exact = True
                    has_edit1 = True
                    break
                if not has_edit1 and is_edit_le_1(tok, other):
                    has_edit1 = True
            total += 1
            if has_exact:
                exact_hits += 1
            if has_edit1:
                edit1_hits += 1

    exact_pct = (exact_hits / total) * 100.0 if total else 0.0
    edit1_pct = (edit1_hits / total) * 100.0 if total else 0.0
    return exact_pct, edit1_pct


def evaluate_stream(name: str, folio_streams: List[List[str]]) -> None:
    flat = [t for seq in folio_streams for t in seq]
    n_tok = len(flat)
    counts = Counter(flat)
    n_types = len(counts)
    ttr = (n_types / n_tok) if n_tok else 0.0
    mean_len = statistics.mean(len(t) for t in flat) if flat else 0.0
    top20_share = (sum(c for _, c in counts.most_common(20)) / n_tok * 100.0) if n_tok else 0.0
    ex_pct, e1_pct = window_metrics(folio_streams, win_half=5)

    print(f"[{name}]")
    print(
        f"  Tokens={n_tok:6d} | Unique Types={n_types:5d} | TTR={ttr:.4f} | "
        f"MeanLen={mean_len:.2f} | Top20Share={top20_share:5.2f}%"
    )
    print(
        f"  +/-5 Win Rates: Exact={ex_pct:6.2f}% | Edit<=1={e1_pct:6.2f}% | "
        f"Exact/Edit1 Ratio={(ex_pct / e1_pct):.3f}\n" if e1_pct > 0 else
        f"  +/-5 Win Rates: Exact={ex_pct:6.2f}% | Edit<=1={e1_pct:6.2f}% | Exact/Edit1 Ratio=0.000\n"
    )


def main() -> None:
    zl_path = sys.argv[1] if len(sys.argv) > 1 else "ZL3b-n.txt"
    by_folio = load_lines_by_folio(zl_path)

    real_streams: List[List[str]] = []
    for flines in by_folio.values():
        seq: List[str] = []
        for ltoks in flines:
            seq.extend(ltoks)
        if seq:
            real_streams.append(seq)

    real_flat = [t for seq in real_streams for t in seq]
    starts, trans, lengths = build_char_bigram_model(real_flat)
    vocab_list = list(Counter(real_flat).keys())

    rng = random.Random(2026)

    markov_streams: List[List[str]] = []
    slot_streams: List[List[str]] = []
    drift_streams: List[List[str]] = []
    shuf_streams: List[List[str]] = []

    for seq in real_streams:
        n = len(seq)
        m_seq: List[str] = []
        s_seq: List[str] = []
        d_seq: List[str] = []
        sh_seq = seq[:]
        rng.shuffle(sh_seq)

        # Folio-local candidate pool for drift generator
        local_pool = [rng.choice(vocab_list) for _ in range(max(12, min(80, n // 3 + 12)))]

        for idx, orig_tok in enumerate(seq):
            tlen = rng.choice(lengths) if lengths else len(orig_tok)
            m_seq.append(gen_markov1_token(rng, starts, trans, tlen))
            s_seq.append(gen_slot_token(rng, tlen))

            # Mild local reuse / neighbor drift within folio
            if idx > 0 and rng.random() < 0.08:
                d_seq.append(d_seq[idx - 1])
            elif idx > 0 and rng.random() < 0.12:
                prev = d_seq[idx - 1]
                if len(prev) >= 2:
                    d_seq.append(prev[:-1] + rng.choice("ynlsr"))
                else:
                    d_seq.append(rng.choice(local_pool))
            else:
                d_seq.append(rng.choice(local_pool))

        markov_streams.append(m_seq)
        slot_streams.append(s_seq)
        drift_streams.append(d_seq)
        shuf_streams.append(sh_seq)

    print("==========================================================================")
    print("L0-ISM v2.7 — GENERATIVE & STRUCTURAL BENCHMARK SUITE (ZL3b-n.txt)")
    print("==========================================================================\n")

    evaluate_stream("1. REAL CORPUS (ZL3b-n.txt baseline)", real_streams)
    evaluate_stream("2. GEN_MARKOV1_CHAR (char-bigram + length matched)", markov_streams)
    evaluate_stream("3. GEN_SLOT_TEMPLATE (prefix + middle + suffix)", slot_streams)
    evaluate_stream("4. GEN_LOCAL_DRIFT_TABLE (folio pool + local reuse/drift)", drift_streams)
    evaluate_stream("5. GEN_FOLIO_SHUFFLE (within-folio bag-of-tokens null)", shuf_streams)


if __name__ == "__main__":
    main()
