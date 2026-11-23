#!/usr/bin/env python3
"""
Exploratory laboratory script for ZL3b-n.txt:
Measures vocabulary size, Type-Token Ratio (TTR), top-20 token share, and
within-folio +/-5 local repetition lift across five pure string/segmentation
transforms (no semantic labels):
  1. baseline             : raw normalized EVA tokens per line
  2. merge_short_1_2      : merges adjacent short tokens (len <= 2) within a line
  3. split_fixed_chunks   : segments line tokens using a fixed list of common EVA chunks
  4. strip_common_affixes : strips common prefixes and suffixes to inspect remaining stems
  5. synth_ko_interfix    : synthetic syllable-insertion benchmark ("ko" / fixed tag)
                            applied to real corpus tokens to compare structural footprint
"""

import random
import re
import statistics
import sys
from collections import Counter, defaultdict
from typing import Dict, List, Tuple

from voynich_ivtff_auditor import normalize_ivtff_line

PREFIXES: Tuple[str, ...] = (
    "qok", "qot", "qo", "ok", "ot", "yk", "yt", "ch", "sh", "ol", "or", "al", "ar"
)
SUFFIXES: Tuple[str, ...] = (
    "eedy", "edy", "aiin", "iin", "in", "dy", "ey", "ol", "or", "al", "ar", "am",
    "y", "s", "r", "l", "d", "n"
)
CHUNKS: Tuple[str, ...] = (
    "qok", "qot", "qo", "ok", "ot", "yk", "yt", "sh", "ch",
    "eedy", "edy", "aiin", "iin", "in", "dy", "ey", "ol", "or", "al", "ar", "am"
)
CHUNKS_SORTED: List[str] = sorted(set(CHUNKS), key=len, reverse=True)


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


def merge_short_tokens(line_toks: List[str], max_len: int = 2) -> List[str]:
    """Merges consecutive short tokens (len <= max_len) within the same line."""
    out: List[str] = []
    buf = ""
    for t in line_toks:
        if len(t) <= max_len:
            buf += t
        else:
            if buf:
                out.append(buf)
                buf = ""
            out.append(t)
    if buf:
        out.append(buf)
    return out


def split_fixed_chunks_token(tok: str) -> List[str]:
    """Splits a token into fixed EVA chunks (greedy longest match) plus single-char leftovers."""
    parts: List[str] = []
    i = 0
    n = len(tok)
    while i < n:
        matched = None
        for ch in CHUNKS_SORTED:
            if tok.startswith(ch, i):
                matched = ch
                break
        if matched:
            parts.append(matched)
            i += len(matched)
        else:
            parts.append(tok[i])
            i += 1
    return parts


def strip_affixes_token(tok: str) -> str:
    """Strips longest matching prefix and suffix once each; returns original if stem becomes empty."""
    cur = tok
    for p in sorted(PREFIXES, key=len, reverse=True):
        if cur.startswith(p) and len(cur) > len(p):
            cur = cur[len(p):]
            break
    for s in sorted(SUFFIXES, key=len, reverse=True):
        if cur.endswith(s) and len(cur) > len(s):
            cur = cur[:-len(s)]
            break
    return cur if cur else tok


def inject_syllable_tag(tok: str, tag: str = "ko") -> str:
    """
    Playground syllable-game transform (like adding 'ko' before chunks/segments):
    splits into 2-char pseudo-syllables and prefixes each segment with `tag`.
    """
    if len(tok) <= 2:
        return tag + tok
    segs = [tok[i:i + 2] for i in range(0, len(tok), 2)]
    return "".join(tag + seg for seg in segs)


def exact_window_rate(streams: List[List[str]], win_half: int = 5) -> float:
    hits = 0
    total = 0
    for seq in streams:
        n = len(seq)
        if n < 2:
            continue
        for i in range(n):
            lo = max(0, i - win_half)
            hi = min(n, i + win_half + 1)
            tok = seq[i]
            found = False
            for j in range(lo, hi):
                if j != i and seq[j] == tok:
                    found = True
                    break
            total += 1
            if found:
                hits += 1
    return (hits / total) * 100.0 if total else 0.0


def evaluate_variant(
    name: str,
    folio_streams: List[List[str]],
    mc_trials: int = 30,
    seed: int = 707,
) -> None:
    flat = [t for seq in folio_streams for t in seq]
    n_tok = len(flat)
    counts = Counter(flat)
    n_types = len(counts)
    ttr = (n_types / n_tok) if n_tok else 0.0
    top20_share = (sum(c for _, c in counts.most_common(20)) / n_tok * 100.0) if n_tok else 0.0
    mean_len = statistics.mean(len(t) for t in flat) if flat else 0.0

    obs_win = exact_window_rate(folio_streams, win_half=5)
    rng = random.Random(seed)
    null_vals: List[float] = []
    for _ in range(mc_trials):
        shuf_streams: List[List[str]] = []
        for seq in folio_streams:
            cp = seq[:]
            rng.shuffle(cp)
            shuf_streams.append(cp)
        null_vals.append(exact_window_rate(shuf_streams, win_half=5))

    null_mu = statistics.mean(null_vals)
    null_sd = statistics.stdev(null_vals) if len(null_vals) > 1 else 0.0
    z_score = (obs_win - null_mu) / null_sd if null_sd > 0 else 0.0

    print(f"[{name}]")
    print(
        f"  Tokens={n_tok:6d} | Unique Types={n_types:5d} | TTR={ttr:.4f} | "
        f"MeanLen={mean_len:.2f} | Top20Share={top20_share:5.2f}%"
    )
    print(
        f"  +/-5 Win Exact Repeat: Obs={obs_win:6.2f}% | Folio-Null={null_mu:6.2f}% "
        f"(SD={null_sd:.2f}%) | Lift={obs_win - null_mu:+6.2f} pp | Z={z_score:+6.2f}\n"
    )


def main() -> None:
    zl_path = sys.argv[1] if len(sys.argv) > 1 else "ZL3b-n.txt"
    by_folio = load_lines_by_folio(zl_path)

    base_streams: List[List[str]] = []
    merged_streams: List[List[str]] = []
    split_streams: List[List[str]] = []
    stripped_streams: List[List[str]] = []
    ko_streams: List[List[str]] = []

    for flines in by_folio.values():
        b_seq: List[str] = []
        m_seq: List[str] = []
        sp_seq: List[str] = []
        st_seq: List[str] = []
        ko_seq: List[str] = []

        for ltoks in flines:
            b_seq.extend(ltoks)
            m_seq.extend(merge_short_tokens(ltoks, max_len=2))
            for t in ltoks:
                sp_seq.extend(split_fixed_chunks_token(t))
                st_seq.append(strip_affixes_token(t))
                ko_seq.append(inject_syllable_tag(t, tag="ko"))

        base_streams.append(b_seq)
        merged_streams.append(m_seq)
        split_streams.append(sp_seq)
        stripped_streams.append(st_seq)
        ko_streams.append(ko_seq)

    print("==========================================================================")
    print("VOYNICH SEGMENTATION & SYLLABLE-INTERFIX LAB (ZL3b-n.txt)")
    print("==========================================================================\n")

    evaluate_variant("1. BASELINE (raw EVA tokens)", base_streams)
    evaluate_variant("2. MERGE SHORT TOKENS (len <= 2 within line)", merged_streams)
    evaluate_variant("3. SPLIT FIXED CHUNKS (EVA prefixes/suffixes)", split_streams)
    evaluate_variant("4. STRIP COMMON AFFIXES (remaining stem audit)", stripped_streams)
    evaluate_variant("5. SYNTHETIC 'ko-' SYLLABLE INTERFIX (playground test)", ko_streams)


if __name__ == "__main__":
    main()
