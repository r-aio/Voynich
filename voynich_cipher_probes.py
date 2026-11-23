#!/usr/bin/env python3
"""
Voynich Manuscript (MS 408) — Pure Cryptographic & Verbose-Cipher Probes (ZL3b-n.txt)
Zero external dependencies (Python 3.11 stdlib only). No L0-ISM / No semantic labels.

Implements 3 falsification probes:
  PROBE 1: Homophone Reduction (Edit<=1 clustering) & Adjacent Length Autocorrelation
           (Tests verbose/homophonic cipher signatures like Naibbe vs. folio-shuffle null).
  PROBE 2: Label Bottleneck Audit (1-2 token lines in A/Z/P vs. prose H/B/S)
           (Bounds maximum feasible verbosity ratio in glyphs per plaintext character).
  PROBE 3: Currier A vs. Currier B Transition-Matrix Isomorphism
           (2-opt permutation alignment of top-25 token transition matrices vs. shuffled null).
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


def shannon_h1_h2(streams: List[List[str]]) -> Tuple[float, float]:
    uni: Counter = Counter()
    bi: Counter = Counter()
    tot_u = 0
    tot_b = 0
    for seq in streams:
        for t in seq:
            uni[t] += 1
            tot_u += 1
        for i in range(len(seq) - 1):
            bi[(seq[i], seq[i + 1])] += 1
            tot_b += 1

    h1 = -sum((c / tot_u) * math.log2(c / tot_u) for c in uni.values()) if tot_u else 0.0
    h_joint = -sum((c / tot_b) * math.log2(c / tot_b) for c in bi.values()) if tot_b else 0.0
    h2_cond = h_joint - h1
    return h1, max(0.0, h2_cond)


def adj_length_autocorr(streams: List[List[str]]) -> float:
    xs: List[float] = []
    ys: List[float] = []
    for seq in streams:
        for i in range(len(seq) - 1):
            xs.append(float(len(seq[i])))
            ys.append(float(len(seq[i + 1])))
    return pearson_corr(xs, ys)


def probe1_homophone_and_autocorr(entries: List[LineEntry]) -> None:
    print("=== PROBE 1: HOMOPHONE REDUCTION (EDIT<=1) & LENGTH AUTOCORRELATION ===")
    by_folio: Dict[str, List[str]] = defaultdict(list)
    line_streams: List[List[str]] = []
    for e in entries:
        by_folio[e.folio].extend(e.tokens)
        line_streams.append(e.tokens)

    folio_streams = [toks for toks in by_folio.values() if toks]
    flat = [t for seq in folio_streams for t in seq]
    counts = Counter(flat)

    # 1A. Adjacent token-length autocorrelation (Real vs. Folio-Shuffle Null)
    r_line = adj_length_autocorr(line_streams)
    r_folio = adj_length_autocorr(folio_streams)

    rng = random.Random(408)
    null_r: List[float] = []
    for _ in range(10):
        shuf_f = []
        for seq in folio_streams:
            cp = seq[:]
            rng.shuffle(cp)
            shuf_f.append(cp)
        null_r.append(adj_length_autocorr(shuf_f))

    print(f"  Adjacent Token-Length Autocorrelation (within lines)  : r = {r_line:+.4f}")
    print(f"  Adjacent Token-Length Autocorrelation (within folios) : r = {r_folio:+.4f}")
    print(
        f"  Folio-Shuffle Null Autocorrelation (10 trials)        : r = {statistics.mean(null_r):+.4f} "
        f"(SD={statistics.stdev(null_r):.4f})"
    )

    # 1B. Greedy Edit<=1 homophone clustering into top-35 classes
    top_types = [w for w, _ in counts.most_common()]
    centers: List[str] = []
    word_to_class: Dict[str, str] = {}
    max_classes = 35

    for w in top_types:
        assigned = None
        for c in centers:
            if is_edit_le_1(w, c):
                assigned = f"C_{c}"
                break
        if assigned is None:
            if len(centers) < max_classes:
                centers.append(w)
                assigned = f"C_{w}"
            else:
                assigned = "C_OTHER"
        word_to_class[w] = assigned

    mapped_streams = [[word_to_class[t] for t in seq] for seq in folio_streams]
    covered_toks = sum(1 for t in flat if word_to_class[t] != "C_OTHER")
    cov_pct = (covered_toks / len(flat) * 100.0) if flat else 0.0

    raw_h1, raw_h2 = shannon_h1_h2(folio_streams)
    cls_h1, cls_h2 = shannon_h1_h2(mapped_streams)

    null_cls_h2: List[float] = []
    for _ in range(5):
        shuf_m = []
        for seq in mapped_streams:
            cp = seq[:]
            rng.shuffle(cp)
            shuf_m.append(cp)
        _, nh2 = shannon_h1_h2(shuf_m)
        null_cls_h2.append(nh2)

    print(f"\n  Greedy Edit<=1 Homophone Reduction (Top {max_classes} classes):")
    print(f"    Corpus coverage by {max_classes} Edit<=1 balls      : {cov_pct:5.2f}% ({covered_toks}/{len(flat)} tokens)")
    print(f"    Raw Token Entropy    -> H1 = {raw_h1:.3f} bits | Cond H2 = {raw_h2:.3f} bits")
    print(f"    Class-Reduced Stream -> H1 = {cls_h1:.3f} bits | Cond H2 = {cls_h2:.3f} bits")
    print(
        f"    Class Folio-Shuffle  -> Cond H2 = {statistics.mean(null_cls_h2):.3f} bits "
        f"(Delta H2 = {statistics.mean(null_cls_h2) - cls_h2:+.3f} bits)"
    )
    print()


def probe2_label_bottleneck(entries: List[LineEntry]) -> None:
    print("=== PROBE 2: LABEL BOTTLENECK AUDIT (1-2 TOKEN LINES VS. PROSE) ===")
    prose_vocab: Counter = Counter()
    for e in entries:
        if e.section in ("H", "B", "S") and len(e.tokens) >= 5:
            prose_vocab.update(e.tokens)

    by_sec_labels: Dict[str, List[LineEntry]] = defaultdict(list)
    all_labels: List[LineEntry] = []
    for e in entries:
        if 1 <= len(e.tokens) <= 2:
            by_sec_labels[e.section].append(e)
            all_labels.append(e)

    def report_group(name: str, items: List[LineEntry]) -> None:
        if not items:
            return
        glyph_lens = [sum(len(t) for t in e.tokens) for e in items]
        toks = [t for e in items for t in e.tokens]
        in_prose = sum(1 for t in toks if t in prose_vocab)
        prose_pct = (in_prose / len(toks) * 100.0) if toks else 0.0
        sorted_gl = sorted(glyph_lens)
        p90 = sorted_gl[int(0.9 * (len(sorted_gl) - 1))]
        med = statistics.median(glyph_lens)
        mean_gl = statistics.mean(glyph_lens)
        max_verb_6 = med / 6.0
        max_verb_8 = med / 8.0
        print(
            f"  {name:<5} | Labels={len(items):4d} | MeanGlyphs={mean_gl:5.2f} | Med={med:4.1f} | "
            f"P90={p90:2d} | InProseVocab={prose_pct:5.1f}% | MaxVerb(6-8L)={max_verb_6:.2f}-{max_verb_8:.2f}x"
        )

    print("  Sec   | Labels | MeanGlyphs |  Med | P90 | InProseVocab | MaxVerb(6-8L)")
    print("  -------------------------------------------------------------------------")
    for sec in ("A", "Z", "P", "C", "H", "B", "S", "T"):
        report_group(sec, by_sec_labels.get(sec, []))
    report_group("ALL", all_labels)
    print("  Note: MaxVerb(6-8L) = Median label glyph count / 6..8 plaintext letters.")
    print("        Verbose ciphers expanding 1 letter -> 2-3 glyphs struggle when MaxVerb < 1.5x.\n")


def build_transition_matrix(streams: List[List[str]], vocab: List[str]) -> List[List[float]]:
    k = len(vocab)
    idx = {w: i for i, w in enumerate(vocab)}
    mat = [[0.0] * k for _ in range(k)]
    tot = 0.0
    for seq in streams:
        for i in range(len(seq) - 1):
            a = idx.get(seq[i])
            b = idx.get(seq[i + 1])
            if a is not None and b is not None:
                mat[a][b] += 1.0
                tot += 1.0
    if tot > 0:
        for i in range(k):
            for j in range(k):
                mat[i][j] /= tot
    return mat


def mat_corr(m1: List[List[float]], m2: List[List[float]], perm: List[int]) -> float:
    k = len(perm)
    xs: List[float] = []
    ys: List[float] = []
    for i in range(k):
        pi = perm[i]
        row1 = m1[i]
        row2 = m2[pi]
        for j in range(k):
            xs.append(row1[j])
            ys.append(row2[perm[j]])
    return pearson_corr(xs, ys)


def optimize_permutation(
    m1: List[List[float]], m2: List[List[float]], restarts: int = 12, seed: int = 408
) -> Tuple[float, List[int]]:
    k = len(m1)
    rng = random.Random(seed)
    best_global_score = -2.0
    best_global_perm = list(range(k))

    for r in range(restarts):
        perm = list(range(k))
        if r > 0:
            rng.shuffle(perm)
        cur_score = mat_corr(m1, m2, perm)

        improved = True
        while improved:
            improved = False
            for i in range(k):
                for j in range(i + 1, k):
                    perm[i], perm[j] = perm[j], perm[i]
                    sc = mat_corr(m1, m2, perm)
                    if sc > cur_score + 1e-6:
                        cur_score = sc
                        improved = True
                    else:
                        perm[i], perm[j] = perm[j], perm[i]

        if cur_score > best_global_score:
            best_global_score = cur_score
            best_global_perm = perm[:]

    return best_global_score, best_global_perm


def probe3_currier_isomorphism(entries: List[LineEntry]) -> None:
    print("=== PROBE 3: CURRIER A VS. CURRIER B TRANSITION-MATRIX ISOMORPHISM ===")
    a_folios: Dict[str, List[str]] = defaultdict(list)
    b_folios: Dict[str, List[str]] = defaultdict(list)
    for e in entries:
        if e.currier == "A":
            a_folios[e.folio].extend(e.tokens)
        elif e.currier == "B":
            b_folios[e.folio].extend(e.tokens)

    a_streams = [v for v in a_folios.values() if v]
    b_streams = [v for v in b_folios.values() if v]

    k = 25
    a_counts = Counter(t for s in a_streams for t in s)
    b_counts = Counter(t for s in b_streams for t in s)
    vocab_a = [w for w, _ in a_counts.most_common(k)]
    vocab_b = [w for w, _ in b_counts.most_common(k)]

    m_a = build_transition_matrix(a_streams, vocab_a)
    m_b = build_transition_matrix(b_streams, vocab_b)

    id_corr = mat_corr(m_a, m_b, list(range(k)))
    opt_corr, opt_perm = optimize_permutation(m_a, m_b, restarts=12, seed=408)

    # Null control: shuffle Currier B within folios and run the exact same 2-opt optimizer
    rng = random.Random(2026)
    null_opt_corrs: List[float] = []
    for t in range(5):
        shuf_b = []
        for s in b_streams:
            cp = s[:]
            rng.shuffle(cp)
            shuf_b.append(cp)
        m_b_null = build_transition_matrix(shuf_b, vocab_b)
        nc, _ = optimize_permutation(m_a, m_b_null, restarts=8, seed=100 + t)
        null_opt_corrs.append(nc)

    mean_null = statistics.mean(null_opt_corrs)
    sd_null = statistics.stdev(null_opt_corrs) if len(null_opt_corrs) > 1 else 0.0

    print(f"  Top-{k} Vocab Overlap (A & B)                   : {len(set(vocab_a) & set(vocab_b))}/{k} shared tokens")
    print(f"  Rank-Aligned Correlation (Identity)            : r = {id_corr:+.4f}")
    print(f"  2-Opt Permuted Correlation (Real A vs Real B)  : r = {opt_corr:+.4f}")
    print(f"  2-Opt Null Control (Real A vs Shuffled B, n=5) : r = {mean_null:+.4f} (SD={sd_null:.4f})")
    print(f"  Net Structural Isomorphism Lift over Null      : {opt_corr - mean_null:+.4f}")

    top_pairs = [f"{vocab_a[i]}<->{vocab_b[opt_perm[i]]}" for i in range(min(8, k))]
    print(f"  Sample Best-Aligned Pairs (Top 8 A)            : {', '.join(top_pairs)}")
    print()


def main() -> None:
    zl_path = sys.argv[1] if len(sys.argv) > 1 else "ZL3b-n.txt"
    print("==========================================================================")
    print("VOYNICH CRYPTOGRAPHIC & VERBOSE-CIPHER PROBES (NO L0-ISM)")
    print("==========================================================================\n")

    entries = parse_ivtff(zl_path)
    print(f"Loaded {len(entries)} lines across {len({e.folio for e in entries})} folios from {zl_path}.\n")

    probe1_homophone_and_autocorr(entries)
    probe2_label_bottleneck(entries)
    probe3_currier_isomorphism(entries)


if __name__ == "__main__":
    main()
