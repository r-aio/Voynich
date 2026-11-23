#!/usr/bin/env python3
"""
L0-ISM Voynich Manuscript (Beinecke MS 408) — MW3 Contextual-Grammar Falsification Audit (v2.3)
Empirically audits six falsifiable claims from the MW3 visual-procedural hypothesis
against independent IVTFF 2.0 corpora (ZL3b-n.txt and RF1b-e.txt):

  1. Exact Quote Verification: Searches for the exact EVA strings attributed to f86r
     ("shedy qopchedy dalin/daiin dy dy", "qokeedy shedy daiin dy dy dy",
     "chedy dalin/daiin daiin qokedy dy") and repetition n-grams across the entire manuscript.
  2. Astronomical Gallows Specialization (f67r: k, f69r: p, f70r: t, f69v: f):
     Tests whether the four gallows characters actually dominate their claimed folios
     using an exact 1,000-trial Monte Carlo chi-square & diagonal dominance test (claimed p < 0.05).
  3. Ultra-Rare Glyph 'g' Localization (f69v eclipse marker claim, ~0.1%):
     Audits the exact count and per-section density of 'g' (standalone and substring)
     across all folios vs. f69v and the Astronomical/Zodiacal section.
  4. Context Polymorphism of 'shedy' Across Sections (Herbal -> Balneo -> Astral):
     Measures exact 'shedy' counts and rates per 1,000 tokens across all sections and
     spot-checks the specific folios cited in MW3 (f8r, f69v, f67v1, f75r, f78r, f86*, fRos, f88r).
  5. Quantitative Repetition Runs (2x..5x) & Herbal Complexity Progression:
     Counts exact consecutive run lengths across the corpus and tests Spearman correlation
     of folio index vs. mean token length and type-token ratio across Herbal folios.
  6. Control Folio Audit (fRos / f85v2 / f86r):
     Checks the Layer II DFA UNKNOWN rate on fRos (which contains f85v2 and f86r) vs.
     the global baseline to test the claimed control rejection of point labels.
"""

import math
import random
import re
import statistics
import sys
from collections import Counter, defaultdict
from typing import Dict, List, Tuple

from voynich_ivtff_auditor import classify_token, normalize_ivtff_line

CLAIMED_QUOTES: List[Tuple[str, List[str]]] = [
    ("Quote 1a (daiin)",      ["shedy", "qopchedy", "daiin", "dy", "dy"]),
    ("Quote 1b (dalin)",      ["shedy", "qopchedy", "dalin", "dy", "dy"]),
    ("Quote 2  (3x dy)",      ["qokeedy", "shedy", "daiin", "dy", "dy", "dy"]),
    ("Quote 3a (daiin)",      ["chedy", "daiin", "daiin", "qokedy", "dy"]),
    ("Quote 3b (dalin)",      ["chedy", "dalin", "daiin", "qokedy", "dy"]),
    ("Sub-gram: daiin dy dy", ["daiin", "dy", "dy"]),
    ("Sub-gram: dy dy dy",    ["dy", "dy", "dy"]),
    ("Sub-gram: dy dy",       ["dy", "dy"]),
    ("Sub-gram: qokey qokey", ["qokey", "qokey"]),
    ("Sub-gram: daiin daiin", ["daiin", "daiin"]),
]


def fallback_section(folio: str) -> str:
    low = folio.lower()
    if low == "fros":
        return "C"
    m = re.match(r"f(\d+)", low)
    if not m:
        return "?"
    num = int(m.group(1))
    if 1 <= num <= 66:
        return "H"
    if 67 <= num <= 73:
        return "A"
    if 75 <= num <= 84:
        return "B"
    if 85 <= num <= 86:
        return "C"
    if 87 <= num <= 102:
        return "P"
    if 103 <= num <= 116:
        return "S"
    return "?"


def parse_corpus_by_folio(filepath: str) -> Tuple[List[str], Dict[str, List[str]], Dict[str, str]]:
    """Returns ordered folio IDs, per-folio normalized EVA tokens, and section codes."""
    header_re = re.compile(r"^#?\s*<(f[0-9]+[rv][0-9]*|fRos)>\s*<!(.*?)>", re.IGNORECASE)
    locus_re = re.compile(r"^<(f[0-9]+[rv][0-9]*|fRos)\.[^>]+>", re.IGNORECASE)

    order: List[str] = []
    tokens_by_folio: Dict[str, List[str]] = defaultdict(list)
    section_by_folio: Dict[str, str] = {}

    def ensure_folio(fid: str) -> None:
        if fid not in section_by_folio:
            order.append(fid)
            section_by_folio[fid] = fallback_section(fid)

    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        for raw_line in f:
            stripped = raw_line.strip()
            if not stripped:
                continue
            hm = header_re.match(stripped)
            if hm:
                fid = hm.group(1)
                ensure_folio(fid)
                sec_m = re.search(r"\$I=([A-Z])", hm.group(2))
                if sec_m:
                    section_by_folio[fid] = sec_m.group(1)
                continue
            lm = locus_re.match(stripped)
            if not lm:
                continue
            fid = lm.group(1)
            ensure_folio(fid)
            toks = normalize_ivtff_line(raw_line)
            if toks:
                tokens_by_folio[fid].extend(toks)

    return order, tokens_by_folio, section_by_folio


def spearman_rho(xs: List[float], ys: List[float]) -> float:
    n = len(xs)
    if n < 2:
        return 0.0

    def rank_vec(vals: List[float]) -> List[float]:
        idx = sorted(enumerate(vals), key=lambda kv: kv[1])
        ranks = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and idx[j + 1][1] == idx[i][1]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                ranks[idx[k][0]] = avg
            i = j + 1
        return ranks

    rx, ry = rank_vec(xs), rank_vec(ys)
    mx, my = statistics.mean(rx), statistics.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den > 0 else 0.0


def test1_quote_audit(order: List[str], tokens_by_folio: Dict[str, List[str]]) -> None:
    print("=== MW3 TEST 1: EXACT QUOTE VERIFICATION (CLAIMED f86r SEQUENCES) ===")
    f86_folios = [fid for fid in order if fid.lower().startswith(("f85", "f86")) or fid.lower() == "fros"]
    print(f"  Codicological Note: Folios matching f85*/f86*/fRos in corpus: {f86_folios}\n")

    for label, seq in CLAIMED_QUOTES:
        k = len(seq)
        hits: List[str] = []
        for fid in order:
            toks = tokens_by_folio[fid]
            for i in range(len(toks) - k + 1):
                if toks[i:i + k] == seq:
                    hits.append(fid)
        status = f"FOUND ({len(hits)}x in {sorted(set(hits))[:8]})" if hits else "[NOT FOUND IN CORPUS]"
        print(f"  {label:<24} : {' '.join(seq):<34} -> {status}")
    print()


def test2_astro_gallows(order: List[str], tokens_by_folio: Dict[str, List[str]], trials: int = 1000) -> None:
    print("=== MW3 TEST 2: ASTRONOMICAL GALLOWS SPECIALIZATION (f67r:k, f69r:p, f70r:t, f69v:f) ===")
    target_groups = [
        ("f67r*", "k", "Claimed: k (rising)"),
        ("f69r*", "p", "Claimed: p (setting)"),
        ("f70r*", "t", "Claimed: t (full)"),
        ("f69v*", "f", "Claimed: f (new)"),
    ]
    gallows = ("k", "p", "t", "f")

    for mode_label, count_fn in [
        ("Word-Initial Gallows", lambda toks, g: sum(1 for t in toks if t.startswith(g))),
        ("Any-Position Gallows", lambda toks, g: sum(t.count(g) for t in toks)),
    ]:
        print(f"  --- Mode: {mode_label} ---")
        print(f"  {'Folio Group':<12} | {'Claimed':<22} | {'Toks':>5} | {'k':>5} | {'p':>5} | {'t':>5} | {'f':>5} | {'Top Gallows'}")
        print("  " + "-" * 84)

        matrix: List[List[int]] = []
        diag_hits = 0
        for prefix, expected_g, claim in target_groups:
            pfx = prefix.rstrip("*").lower()
            matched_toks = [t for fid in order if fid.lower().startswith(pfx) for t in tokens_by_folio[fid]]
            row = [count_fn(matched_toks, g) for g in gallows]
            matrix.append(row)
            max_val = max(row) if row else 0
            top_g = gallows[row.index(max_val)] if max_val > 0 else "none"
            if top_g == expected_g:
                diag_hits += 1
            print(
                f"  {prefix:<12} | {claim:<22} | {len(matched_toks):>5d} | "
                f"{row[0]:>5d} | {row[1]:>5d} | {row[2]:>5d} | {row[3]:>5d} | {top_g} "
                f"({'MATCH' if top_g == expected_g else 'MISMATCH'})"
            )

        row_sums = [sum(r) for r in matrix]
        col_sums = [sum(matrix[i][j] for i in range(4)) for j in range(4)]
        grand_total = sum(row_sums)

        def chi2_stat(mat: List[List[int]]) -> float:
            val = 0.0
            for i in range(4):
                for j in range(4):
                    exp = (row_sums[i] * col_sums[j]) / grand_total if grand_total else 0.0
                    if exp > 0:
                        val += ((mat[i][j] - exp) ** 2) / exp
            return val

        obs_chi2 = chi2_stat(matrix)
        obs_diag_share = sum(matrix[i][i] for i in range(4)) / grand_total if grand_total else 0.0

        rng = random.Random(3001)
        flat_cols = [j for j, c in enumerate(col_sums) for _ in range(c)]
        exceed_chi2 = 0
        exceed_diag = 0
        for _ in range(trials):
            rng.shuffle(flat_cols)
            sim = [[0] * 4 for _ in range(4)]
            pos = 0
            for i, rs in enumerate(row_sums):
                for col_idx in flat_cols[pos:pos + rs]:
                    sim[i][col_idx] += 1
                pos += rs
            if chi2_stat(sim) >= obs_chi2:
                exceed_chi2 += 1
            sim_diag = sum(sim[i][i] for i in range(4)) / grand_total if grand_total else 0.0
            if sim_diag >= obs_diag_share:
                exceed_diag += 1

        p_chi2 = (exceed_chi2 + 1) / (trials + 1)
        p_diag = (exceed_diag + 1) / (trials + 1)
        verdict = "[SUPPORTED]" if (diag_hits >= 3 and p_diag < 0.05) else "[FALSIFIED / CONTRADICTED]"
        print(
            f"  Diagonal Dominance: {diag_hits}/4 folios match | Diagonal Share = {obs_diag_share*100:.2f}% "
            f"(p_diag = {p_diag:.4f}) | Table Chi2 = {obs_chi2:.2f} (p = {p_chi2:.4f}) -> {verdict}\n"
        )


def test3_rare_glyph_g(order: List[str], tokens_by_folio: Dict[str, List[str]], section_by_folio: Dict[str, str]) -> None:
    print("=== MW3 TEST 3: ULTRA-RARE GLYPH 'g' LOCALIZATION (CLAIMED f69v ECLIPSE MARKER) ===")
    sec_toks: Counter = Counter()
    sec_g_any: Counter = Counter()
    sec_g_solo: Counter = Counter()
    folio_g_hits: Counter = Counter()

    for fid in order:
        sec = section_by_folio[fid]
        sec_grp = sec if sec in ("H", "B", "P", "S", "T") else ("AZC" if sec in ("A", "Z", "C") else "?")
        toks = tokens_by_folio[fid]
        sec_toks[sec_grp] += len(toks)
        for t in toks:
            if "g" in t:
                sec_g_any[sec_grp] += 1
                folio_g_hits[fid] += 1
            if t == "g":
                sec_g_solo[sec_grp] += 1

    tot_toks = sum(sec_toks.values())
    tot_g_any = sum(sec_g_any.values())
    tot_g_solo = sum(sec_g_solo.values())
    f69v_g = folio_g_hits.get("f69v", 0)
    f69v_toks = len(tokens_by_folio.get("f69v", []))

    print(f"  Global tokens containing 'g' : {tot_g_any}/{tot_toks} ({tot_g_any/tot_toks*100:.3f}%) | Standalone 'g': {tot_g_solo}")
    print(f"  Folio f69v 'g' occurrences   : {f69v_g}/{f69v_toks} tokens")
    print(f"  Top 10 folios containing 'g' : {folio_g_hits.most_common(10)}\n")

    print(f"  {'Section':<8} | {'Tokens':>6} | {'Contains g':>10} | {'Rate /1k':>9} | {'Standalone g':>12}")
    print("  " + "-" * 56)
    for sec in ("H", "B", "P", "AZC", "S", "T"):
        if sec_toks[sec] > 0:
            rate = sec_g_any[sec] / sec_toks[sec] * 1000.0
            print(f"  {sec:<8} | {sec_toks[sec]:>6d} | {sec_g_any[sec]:>10d} | {rate:>9.2f} | {sec_g_solo[sec]:>12d}")
    print()


def test4_shedy_polymorphism(order: List[str], tokens_by_folio: Dict[str, List[str]], section_by_folio: Dict[str, str]) -> None:
    print("=== MW3 TEST 4: 'shedy' CROSS-SECTION POLYMORPHISM (HERBAL -> BALNEO -> ASTRAL) ===")
    sec_toks: Counter = Counter()
    sec_shedy: Counter = Counter()

    for fid in order:
        sec = section_by_folio[fid]
        sec_grp = sec if sec in ("H", "B", "P", "S", "T") else ("AZC" if sec in ("A", "Z", "C") else "?")
        toks = tokens_by_folio[fid]
        sec_toks[sec_grp] += len(toks)
        sec_shedy[sec_grp] += sum(1 for t in toks if t == "shedy")

    print(f"  {'Section':<8} | {'Tokens':>6} | {'shedy Hits':>10} | {'Rate /1k':>9}")
    print("  " + "-" * 42)
    for sec in ("H", "B", "P", "AZC", "S", "T"):
        if sec_toks[sec] > 0:
            rate = sec_shedy[sec] / sec_toks[sec] * 1000.0
            print(f"  {sec:<8} | {sec_toks[sec]:>6d} | {sec_shedy[sec]:>10d} | {rate:>9.2f}")

    spot_folios = ["f8r", "f67v1", "f69v", "f75r", "f78r", "f86v3", "f86v4", "f86v5", "f86v6", "fRos", "f88r"]
    spot_hits = {f: sum(1 for t in tokens_by_folio.get(f, []) if t == "shedy") for f in spot_folios if f in tokens_by_folio}
    print(f"\n  Spot-check 'shedy' on MW3-cited folios: {spot_hits}\n")


def test5_runs_and_herbal_progression(order: List[str], tokens_by_folio: Dict[str, List[str]], section_by_folio: Dict[str, str]) -> None:
    print("=== MW3 TEST 5: QUANTITATIVE REPETITION RUNS (2x-5x) & HERBAL PROGRESSION ===")
    run_dist_all: Counter = Counter()
    run_dist_targets: Dict[str, Counter] = {t: Counter() for t in ("dy", "daiin", "qokey", "qokaiin", "chol")}
    long_runs: List[Tuple[str, str, int]] = []

    for fid in order:
        toks = tokens_by_folio[fid]
        i = 0
        n = len(toks)
        while i < n:
            j = i + 1
            while j < n and toks[j] == toks[i]:
                j += 1
            run_len = j - i
            if run_len >= 2:
                run_dist_all[run_len] += 1
                if toks[i] in run_dist_targets:
                    run_dist_targets[toks[i]][run_len] += 1
                if run_len >= 3:
                    long_runs.append((fid, toks[i], run_len))
            i = j

    print(f"  All-Token Consecutive Run Lengths (2x+): {dict(sorted(run_dist_all.items()))}")
    for tok, c in run_dist_targets.items():
        print(f"    Token '{tok:<7}' run lengths : {dict(sorted(c.items()))}")
    print(f"  All >=3x runs in corpus (first 15) : {long_runs[:15]}\n")

    herbal_indices: List[float] = []
    mean_lengths: List[float] = []
    ttrs: List[float] = []
    for idx, fid in enumerate(order):
        if section_by_folio[fid] == "H":
            toks = tokens_by_folio[fid]
            if len(toks) >= 20:
                herbal_indices.append(float(idx))
                mean_lengths.append(statistics.mean(len(t) for t in toks))
                ttrs.append(len(set(toks)) / len(toks))

    rho_len = spearman_rho(herbal_indices, mean_lengths)
    rho_ttr = spearman_rho(herbal_indices, ttrs)
    print(f"  Herbal Progression Audit (N = {len(herbal_indices)} Herbal folios with >=20 tokens):")
    print(f"    Folio Order vs. Mean Word Length : Spearman rho = {rho_len:+.3f}")
    print(f"    Folio Order vs. Type-Token Ratio : Spearman rho = {rho_ttr:+.3f}\n")


def test6_control_folio_audit(order: List[str], tokens_by_folio: Dict[str, List[str]]) -> None:
    print("=== MW3 TEST 6: CONTROL FOLIO AUDIT (fRos / f85v2 / f67v1 / f78r UNKNOWN RATE) ===")
    all_toks = [t for fid in order for t in tokens_by_folio[fid]]
    global_unk = sum(1 for t in all_toks if classify_token(t)[0] == "UNKNOWN")
    print(f"  Global Corpus UNKNOWN Rate : {global_unk}/{len(all_toks)} ({global_unk/len(all_toks)*100:.2f}%)\n")

    targets = ["fRos", "f85v2", "f86r", "f86v3", "f86v4", "f67v1", "f78r", "f69v"]
    for fid in targets:
        if fid not in tokens_by_folio:
            print(f"  Folio {fid:<6} : [NOT PRESENT AS SEPARATE FOLIO ID IN THIS EDITION]")
            continue
        toks = tokens_by_folio[fid]
        unk = sum(1 for t in toks if classify_token(t)[0] == "UNKNOWN")
        l1 = sum(1 for t in toks if classify_token(t)[0] == "L1")
        rate_u = (unk / len(toks) * 100.0) if toks else 0.0
        rate_l1 = (l1 / len(toks) * 100.0) if toks else 0.0
        print(f"  Folio {fid:<6} : N = {len(toks):4d} | L1 = {l1:3d} ({rate_l1:5.2f}%) | UNKNOWN = {unk:3d} ({rate_u:5.2f}%)")
    print()


def main() -> None:
    zl_file = sys.argv[1] if len(sys.argv) > 1 else "ZL3b-n.txt"
    rf_file = sys.argv[2] if len(sys.argv) > 2 else "RF1b-e.txt"

    print("==========================================================================")
    print("L0-ISM v2.3 — MW3 VISUAL-PROCEDURAL CLAIMS FALSIFICATION AUDIT")
    print("==========================================================================\n")

    for label, path in [("PRIMARY CORPUS (ZL3b-n)", zl_file), ("CROSS-CHECK CORPUS (RF1b-e)", rf_file)]:
        print("##########################################################################")
        print(f"AUDIT TARGET: {label} -> {path}")
        print("##########################################################################\n")
        order, tokens_by_folio, section_by_folio = parse_corpus_by_folio(path)
        test1_quote_audit(order, tokens_by_folio)
        test2_astro_gallows(order, tokens_by_folio, trials=1000)
        test3_rare_glyph_g(order, tokens_by_folio, section_by_folio)
        test4_shedy_polymorphism(order, tokens_by_folio, section_by_folio)
        test5_runs_and_herbal_progression(order, tokens_by_folio, section_by_folio)
        test6_control_folio_audit(order, tokens_by_folio)


if __name__ == "__main__":
    main()
