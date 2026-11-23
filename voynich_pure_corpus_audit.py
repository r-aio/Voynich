#!/usr/bin/env python3
"""
Pure Corpus Audit for MS 408 (IVTFF) — Without L0-ISM or Semantic Labels.

Checks:
  1. Basic & +/-5 window metrics (exact repeat and edit-distance <= 1) vs.
     within-folio and within-quire shuffle controls.
  2. Positional distributions (line start / middle / end; line 0 vs. body lines)
     stratified by Currier style ($L) where present.
  3. Codex continuity ($Q, $I, $L, $H) and adjacent-folio vocabulary Jaccard.
  4. Dual-transcription alignment comparison (ZL3b-n.txt vs. RF1b-e.txt) on
     matched lines/folios (resilient to token split/shift).
  5. Simple generative controls matched to folio token counts.
  6. Within-line shuffle control (isolating local line-order vs. folio-bag)
     & section boundary (first vs. last line of each section $I) word lengths.
  7. Word bigram/trigram repeats & near (<=5) vs. far (>5) same-folio
     word recurrence vs. within-folio shuffle control.
"""

from __future__ import annotations

import difflib
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


def window_rates(streams: List[List[str]], win_half: int = 5) -> Tuple[float, float]:
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

    ex = (exact_hits / total) * 100.0 if total else 0.0
    e1 = (edit1_hits / total) * 100.0 if total else 0.0
    return ex, e1


def summarize_stream(label: str, folio_streams: List[List[str]]) -> None:
    flat = [t for seq in folio_streams for t in seq]
    n_tok = len(flat)
    counts = Counter(flat)
    n_types = len(counts)
    ttr = (n_types / n_tok) if n_tok else 0.0
    mean_len = statistics.mean(len(t) for t in flat) if flat else 0.0
    top20_pct = (sum(c for _, c in counts.most_common(20)) / n_tok * 100.0) if n_tok else 0.0
    ex, e1 = window_rates(folio_streams, win_half=5)
    print(
        f"  {label:<32} | Toks={n_tok:6d} | Types={n_types:5d} | TTR={ttr:.4f} | "
        f"Len={mean_len:4.2f} | Top20={top20_pct:5.2f}% | Win5 Exact={ex:5.2f}% | Edit1={e1:5.2f}%"
    )


def test1_window_and_shuffles(entries: List[LineEntry]) -> None:
    print("=== TEST 1: +/-5 WINDOW NEIGHBORHOOD VS. FOLIO & QUIRE SHUFFLES ===")
    by_folio: Dict[str, List[str]] = defaultdict(list)
    by_quire: Dict[str, List[str]] = defaultdict(list)
    for e in entries:
        by_folio[e.folio].extend(e.tokens)
        by_quire[e.quire].extend(e.tokens)

    real_folios = [toks for toks in by_folio.values() if toks]
    summarize_stream("REAL (within-folio order)", real_folios)

    rng = random.Random(408)
    folio_shuf_ex: List[float] = []
    folio_shuf_e1: List[float] = []
    quire_shuf_ex: List[float] = []
    quire_shuf_e1: List[float] = []

    for _ in range(10):
        f_streams: List[List[str]] = []
        for toks in real_folios:
            copy_t = toks[:]
            rng.shuffle(copy_t)
            f_streams.append(copy_t)
        f_ex, f_e1 = window_rates(f_streams, win_half=5)
        folio_shuf_ex.append(f_ex)
        folio_shuf_e1.append(f_e1)

        q_streams: List[List[str]] = []
        for qtoks in by_quire.values():
            if not qtoks:
                continue
            copy_q = qtoks[:]
            rng.shuffle(copy_q)
            q_streams.append(copy_q)
        q_ex, q_e1 = window_rates(q_streams, win_half=5)
        quire_shuf_ex.append(q_ex)
        quire_shuf_e1.append(q_e1)

    print(
        f"  SHUFFLE WITHIN FOLIO (10 trials) : Win5 Exact={statistics.mean(folio_shuf_ex):5.2f}% "
        f"(SD={statistics.stdev(folio_shuf_ex):.2f}%) | Edit1={statistics.mean(folio_shuf_e1):5.2f}% "
        f"(SD={statistics.stdev(folio_shuf_e1):.2f}%)"
    )
    print(
        f"  SHUFFLE WITHIN QUIRE (10 trials) : Win5 Exact={statistics.mean(quire_shuf_ex):5.2f}% "
        f"(SD={statistics.stdev(quire_shuf_ex):.2f}%) | Edit1={statistics.mean(quire_shuf_e1):5.2f}% "
        f"(SD={statistics.stdev(quire_shuf_e1):.2f}%)"
    )
    print()


def test2_line_and_paragraph_positions(entries: List[LineEntry]) -> None:
    print("=== TEST 2: LINE POSITION & FIRST-LINE VS. BODY LINES (BY CURRIER $L) ===")
    by_currier: Dict[str, Dict[str, List[int]]] = defaultdict(lambda: defaultdict(list))

    for e in entries:
        toks = e.tokens
        if not toks:
            continue
        cur = e.currier if e.currier in ("A", "B") else "OTHER"
        role = "LINE_0" if e.line_idx_in_folio == 0 else "LINE_GT0"
        by_currier[cur][role].append(len(toks))

        for idx, t in enumerate(toks):
            if idx == 0:
                pos = "INIT"
            elif idx == len(toks) - 1:
                pos = "FINAL"
            else:
                pos = "MID"
            by_currier[cur][f"POS_{pos}"].append(len(t))

    for cur in sorted(by_currier.keys()):
        d = by_currier[cur]
        l0 = d.get("LINE_0", [])
        lg = d.get("LINE_GT0", [])
        pi = d.get("POS_INIT", [])
        pm = d.get("POS_MID", [])
        pf = d.get("POS_FINAL", [])
        print(
            f"  Currier={cur:<5} | Line0 MeanToks={statistics.mean(l0) if l0 else 0:5.2f} (n={len(l0):3d}) | "
            f"Body Line MeanToks={statistics.mean(lg) if lg else 0:5.2f} (n={len(lg):4d})"
        )
        print(
            f"    Token len by pos -> INIT: {statistics.mean(pi) if pi else 0:4.2f} | "
            f"MID: {statistics.mean(pm) if pm else 0:4.2f} | FINAL: {statistics.mean(pf) if pf else 0:4.2f}"
        )
    print()


def test3_codex_continuity(entries: List[LineEntry]) -> None:
    print("=== TEST 3: FOLIO SEQUENCE CONTINUITY & ADJACENT JACCARD ===")
    ordered_folios: List[str] = []
    meta_by_folio: Dict[str, LineEntry] = {}
    toks_by_folio: Dict[str, List[str]] = defaultdict(list)

    for e in entries:
        if e.folio not in meta_by_folio:
            ordered_folios.append(e.folio)
            meta_by_folio[e.folio] = e
        toks_by_folio[e.folio].extend(e.tokens)

    same_q_j: List[float] = []
    diff_q_j: List[float] = []
    q_jumps = 0
    l_jumps = 0
    h_jumps = 0

    for i in range(1, len(ordered_folios)):
        f1, f2 = ordered_folios[i - 1], ordered_folios[i]
        e1, e2 = meta_by_folio[f1], meta_by_folio[f2]
        if e1.quire != e2.quire:
            q_jumps += 1
        if e1.currier != e2.currier:
            l_jumps += 1
        if e1.scribe != e2.scribe:
            h_jumps += 1

        s1, s2 = set(toks_by_folio[f1]), set(toks_by_folio[f2])
        if s1 and s2:
            j = len(s1 & s2) / len(s1 | s2)
            if e1.quire == e2.quire:
                same_q_j.append(j)
            else:
                diff_q_j.append(j)

    print(f"  Folios={len(ordered_folios)} | Quire jumps={q_jumps} | Currier jumps={l_jumps} | Scribe jumps={h_jumps}")
    if same_q_j:
        print(f"  Adjacent Jaccard (Same Quire, n={len(same_q_j):3d}) : mean={statistics.mean(same_q_j):.4f}")
    if diff_q_j:
        print(f"  Adjacent Jaccard (Diff Quire, n={len(diff_q_j):3d}) : mean={statistics.mean(diff_q_j):.4f}")
    print()


def test4_dual_transcription_alignment(zl_entries: List[LineEntry], rf_entries: List[LineEntry]) -> None:
    print("=== TEST 4: ALIGNED LINE SIMILARITY (ZL3b-n VS. RF1b-e) ===")
    zl_by_line: Dict[str, List[str]] = {}
    rf_by_line: Dict[str, List[str]] = {}
    for e in zl_entries:
        zl_by_line[e.line_id] = e.tokens
    for e in rf_entries:
        rf_by_line[e.line_id] = e.tokens

    common_lines = sorted(set(zl_by_line.keys()) & set(rf_by_line.keys()))
    if not common_lines:
        print("  No matching line IDs between corpora.\n")
        return

    line_ratios: List[float] = []
    by_folio_ratios: Dict[str, List[float]] = defaultdict(list)

    for lid in common_lines:
        a = zl_by_line[lid]
        b = rf_by_line[lid]
        ratio = difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()
        line_ratios.append(ratio)
        fid = lid.split(".", 1)[0]
        by_folio_ratios[fid].append(ratio)

    print(f"  Matched Lines                         : {len(common_lines)}")
    print(
        f"  Aligned Sequence Similarity Ratio     : mean={statistics.mean(line_ratios):.4f}, "
        f"median={statistics.median(line_ratios):.4f}"
    )

    folio_means: List[Tuple[float, int, str]] = []
    for fid, vals in by_folio_ratios.items():
        folio_means.append((statistics.mean(vals), len(vals), fid))

    print("  Lowest-Similarity Folios (most divergent aligned lines):")
    for m_val, n_l, fid in sorted(folio_means)[:10]:
        print(f"    {fid:<8} | lines={n_l:3d} | mean_sim={m_val:.4f}")
    print()


def test5_simple_generators(entries: List[LineEntry]) -> None:
    print("=== TEST 5: SIMPLE GENERATORS MATCHED TO FOLIO TOKEN COUNTS ===")
    by_folio: Dict[str, List[str]] = defaultdict(list)
    for e in entries:
        by_folio[e.folio].extend(e.tokens)
    real_folios = [toks for toks in by_folio.values() if toks]
    flat = [t for seq in real_folios for t in seq]

    starts: Counter = Counter()
    trans: Dict[str, Counter] = defaultdict(Counter)
    lengths: List[int] = []
    for t in flat:
        lengths.append(len(t))
        starts[t[0]] += 1
        for i in range(len(t) - 1):
            trans[t[i]][t[i + 1]] += 1

    def pick_weighted(rng: random.Random, c: Counter) -> str:
        tot = sum(c.values())
        r = rng.uniform(0, tot)
        acc = 0.0
        for k, v in c.items():
            acc += v
            if acc >= r:
                return k
        return next(iter(c.keys()))

    def make_bigram_word(rng: random.Random, length: int) -> str:
        cur = pick_weighted(rng, starts)
        chars = [cur]
        for _ in range(max(0, length - 1)):
            nxt = trans.get(cur)
            cur = pick_weighted(rng, nxt) if nxt else pick_weighted(rng, starts)
            chars.append(cur)
        return "".join(chars)

    prefixes = ("qo", "ok", "ot", "ch", "sh", "ol", "or", "al", "ar", "")
    middles = ("k", "t", "p", "f", "e", "o", "a", "y", "")
    suffixes = ("edy", "eedy", "aiin", "iin", "in", "dy", "ey", "ol", "or", "y", "s", "")

    def make_slot_word(rng: random.Random, target_len: int) -> str:
        best = ""
        for _ in range(5):
            cand = rng.choice(prefixes) + rng.choice(middles) + rng.choice(suffixes)
            if not cand:
                cand = "ol"
            if not best or abs(len(cand) - target_len) < abs(len(best) - target_len):
                best = cand
        return best

    rng = random.Random(2026)
    bigram_streams: List[List[str]] = []
    slot_streams: List[List[str]] = []

    for seq in real_folios:
        b_seq: List[str] = []
        s_seq: List[str] = []
        for orig in seq:
            tlen = rng.choice(lengths) if lengths else len(orig)
            b_seq.append(make_bigram_word(rng, tlen))
            s_seq.append(make_slot_word(rng, tlen))
        bigram_streams.append(b_seq)
        slot_streams.append(s_seq)

    summarize_stream("1. REAL CORPUS (ZL3b-n)", real_folios)
    summarize_stream("2. GEN_CHAR_BIGRAM", bigram_streams)
    summarize_stream("3. GEN_SLOT_TEMPLATE", slot_streams)
    print()


def test6_line_shuffle_and_section_bounds(entries: List[LineEntry]) -> None:
    print("=== TEST 6: WITHIN-LINE SHUFFLE & SECTION BOUNDARY WORD LENGTHS ===")
    by_folio_lines: Dict[str, List[List[str]]] = defaultdict(list)
    for e in entries:
        if e.tokens:
            by_folio_lines[e.folio].append(e.tokens)

    real_folio_streams = [[t for line in lines for t in line] for lines in by_folio_lines.values()]
    obs_ex, obs_e1 = window_rates(real_folio_streams, win_half=5)

    rng = random.Random(2026)
    line_shuf_ex: List[float] = []
    line_shuf_e1: List[float] = []

    for _ in range(10):
        shuf_streams: List[List[str]] = []
        for lines in by_folio_lines.values():
            f_toks: List[str] = []
            for line in lines:
                cp = line[:]
                rng.shuffle(cp)
                f_toks.extend(cp)
            shuf_streams.append(f_toks)
        ex, e1 = window_rates(shuf_streams, win_half=5)
        line_shuf_ex.append(ex)
        line_shuf_e1.append(e1)

    print(
        f"  REAL +/-5 Window                 : Exact={obs_ex:5.2f}% | Edit1={obs_e1:5.2f}%"
    )
    print(
        f"  SHUFFLE WITHIN LINE (10 trials)  : Exact={statistics.mean(line_shuf_ex):5.2f}% "
        f"(SD={statistics.stdev(line_shuf_ex):.2f}%) | Edit1={statistics.mean(line_shuf_e1):5.2f}% "
        f"(SD={statistics.stdev(line_shuf_e1):.2f}%)"
    )

    sec_first_lens: Dict[str, List[int]] = defaultdict(list)
    sec_last_lens: Dict[str, List[int]] = defaultdict(list)
    sec_all_lens: Dict[str, List[int]] = defaultdict(list)

    for e in entries:
        if not e.tokens:
            continue
        sec_all_lens[e.section].extend(len(t) for t in e.tokens)

    first_seen_line: Dict[str, LineEntry] = {}
    last_seen_line: Dict[str, LineEntry] = {}
    for e in entries:
        if not e.tokens:
            continue
        if e.section not in first_seen_line:
            first_seen_line[e.section] = e
        last_seen_line[e.section] = e

    for sec, le in first_seen_line.items():
        sec_first_lens[sec].extend(len(t) for t in le.tokens)
    for sec, le in last_seen_line.items():
        sec_last_lens[sec].extend(len(t) for t in le.tokens)

    print("\n  Section Word Length Comparison (First Line vs. Last Line vs. Section Mean):")
    print("  Sec | FirstLineLen | LastLineLen | SecMeanLen")
    print("  -----------------------------------------------")
    for sec in sorted(sec_all_lens.keys()):
        f_m = statistics.mean(sec_first_lens[sec]) if sec_first_lens[sec] else 0.0
        l_m = statistics.mean(sec_last_lens[sec]) if sec_last_lens[sec] else 0.0
        a_m = statistics.mean(sec_all_lens[sec]) if sec_all_lens[sec] else 0.0
        print(f"  {sec:<3} | {f_m:12.2f} | {l_m:11.2f} | {a_m:10.2f}")
    print()


def test7_word_ngrams_and_lag_profile(entries: List[LineEntry]) -> None:
    print("=== TEST 7: WORD N-GRAM REPEATS & NEAR VS. FAR SAME-FOLIO RECURRENCE ===")
    by_folio: Dict[str, List[str]] = defaultdict(list)
    for e in entries:
        by_folio[e.folio].extend(e.tokens)
    real_folios = [toks for toks in by_folio.values() if toks]

    def ngram_repeat_stats(streams: List[List[str]]) -> Tuple[float, float, float, float]:
        big_tot = big_rep = 0
        tri_tot = tri_rep = 0
        near_hits = near_tot = 0
        far_hits = far_tot = 0

        for seq in streams:
            n = len(seq)
            if n >= 2:
                seen_bi = set()
                for i in range(n - 1):
                    bg = (seq[i], seq[i + 1])
                    big_tot += 1
                    if bg in seen_bi:
                        big_rep += 1
                    seen_bi.add(bg)
            if n >= 3:
                seen_tri = set()
                for i in range(n - 2):
                    tg = (seq[i], seq[i + 1], seq[i + 2])
                    tri_tot += 1
                    if tg in seen_tri:
                        tri_rep += 1
                    seen_tri.add(tg)

            for i in range(n):
                tok = seq[i]
                lo_n = max(0, i - 5)
                hi_n = min(n, i + 6)
                has_near = any(seq[j] == tok for j in range(lo_n, hi_n) if j != i)
                near_tot += 1
                if has_near:
                    near_hits += 1

                has_far = any(
                    seq[j] == tok for j in range(n) if j != i and abs(j - i) > 5
                )
                far_tot += 1
                if has_far:
                    far_hits += 1

        bi_pct = (big_rep / big_tot * 100.0) if big_tot else 0.0
        tri_pct = (tri_rep / tri_tot * 100.0) if tri_tot else 0.0
        near_pct = (near_hits / near_tot * 100.0) if near_tot else 0.0
        far_pct = (far_hits / far_tot * 100.0) if far_tot else 0.0
        return bi_pct, tri_pct, near_pct, far_pct

    r_bi, r_tri, r_near, r_far = ngram_repeat_stats(real_folios)
    rng = random.Random(2026)
    s_bi, s_tri, s_near, s_far = [], [], [], []
    for _ in range(10):
        sh_streams = []
        for toks in real_folios:
            cp = toks[:]
            rng.shuffle(cp)
            sh_streams.append(cp)
        b, t, nr, fr = ngram_repeat_stats(sh_streams)
        s_bi.append(b)
        s_tri.append(t)
        s_near.append(nr)
        s_far.append(fr)

    print(
        f"  REAL               | BiRep={r_bi:5.2f}% | TriRep={r_tri:5.2f}% | "
        f"Near(<=5)={r_near:5.2f}% | Far(>5)={r_far:5.2f}%"
    )
    print(
        f"  SHUFFLE FOLIO (10) | BiRep={statistics.mean(s_bi):5.2f}% | TriRep={statistics.mean(s_tri):5.2f}% | "
        f"Near(<=5)={statistics.mean(s_near):5.2f}% | Far(>5)={statistics.mean(s_far):5.2f}%"
    )
    print()


def main() -> None:
    zl_path = sys.argv[1] if len(sys.argv) > 1 else "ZL3b-n.txt"
    rf_path = sys.argv[2] if len(sys.argv) > 2 else "RF1b-e.txt"

    print("==========================================================================")
    print("PURE CORPUS AUDIT (NO L0-ISM / NO SEMANTIC LABELS)")
    print("==========================================================================\n")

    zl_entries = parse_ivtff(zl_path)
    print(f"Loaded {len(zl_entries)} lines across {len({e.folio for e in zl_entries})} folios from {zl_path}.\n")

    test1_window_and_shuffles(zl_entries)
    test2_line_and_paragraph_positions(zl_entries)
    test3_codex_continuity(zl_entries)
    test5_simple_generators(zl_entries)
    test6_line_shuffle_and_section_bounds(zl_entries)
    test7_word_ngrams_and_lag_profile(zl_entries)

    try:
        rf_entries = parse_ivtff(rf_path)
        if rf_entries:
            print(f"Loaded {len(rf_entries)} lines across {len({e.folio for e in rf_entries})} folios from {rf_path}.\n")
            test4_dual_transcription_alignment(zl_entries, rf_entries)
    except FileNotFoundError:
        print(f"[INFO] Secondary corpus {rf_path} not found; skipping aligned comparison.\n")


if __name__ == "__main__":
    main()
