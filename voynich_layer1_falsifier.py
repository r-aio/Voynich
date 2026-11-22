#!/usr/bin/env python3
"""
L0-ISM Voynich Manuscript (Beinecke MS 408) — Layer I Falsification Suite (v2.1)
Direct empirical stress-test of Layer I (15th-century hydro-thermal operational mapping)
using strict within-page / within-paragraph null models (1,000 Monte Carlo trials).

Tests executed:
  1. Thermodynamic Causality (qok- Liquid Priming -> qot- Steam Diversion):
     Checks whether liquid-loop commands precede steam/hypocaustum switching more often
     than expected under 1,000 within-folio and within-paragraph position permutations.
     Explicitly counts physical contradictions (qot- firing before first qok-).
  2. 7-Phase Cold-Start Positional Monotonicity & End-of-Paragraph Flush ('am') Audit:
     Measures normalized paragraph position (0.0 = start, 1.0 = end) for Phases 1-7
     and computes Spearman rank correlation against the claimed cold-start order.
  3. Section x Subsystem Enrichment Matrix (Stratified by Currier Language A vs. B):
     Tests whether claimed hardware subsystems concentrate in their assigned codicological
     sections (Herbal, Balneological, Pharmaceutical, Astro/Zodiac, Stars/Text).
  4. Residual 13-15% UNKNOWN Contradiction & Boundary Audit:
     Inspects whether unmapped tokens cluster inside critical switching windows (around qot-)
     or interrupt steady-state siphon repeats (X . UNKNOWN . X).

Verdicts are strictly data-driven: [SUPPORTED], [INCONCLUSIVE / NULL], or [FALSIFIED / CONTRADICTED].
"""

import math
import random
import re
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple

from voynich_ivtff_auditor import VOYNICH_FULL_LUT, classify_token, normalize_ivtff_line

# Strictly L1 frames vs. broad core families for Test 1
QOK_STRICT = {"qokain", "qokaiin", "qokaiiin"}
QOT_STRICT = {"qotain", "qotaiin", "qotaiiin"}

# 7-Phase Cold-Start mapping (Layer I sequence from manuscript operational model)
COLD_START_PHASES: List[Tuple[int, str, Set[str]]] = [
    (1, "Phase 1: Furnace Damper (daim/dair)",          {"daim", "dair"}),
    (2, "Phase 3: Anti-Scale Buffer (chey/qochey)",     {"chey", "qochey"}),
    (3, "Phase 4: Air Vent & Header (al/sol/otain*)",   {"al", "sol", "ckhaiin", "otain", "otaiin"}),
    (4, "Phase 6a: Liquid Manifold (qokain/ii/iii)",    {"qokain", "qokaiin", "qokaiiin"}),
    (5, "Phase 6b: Steam 3-Way Switch (qotain/ii/iii)", {"qotain", "qotaiin", "qotaiiin"}),
    (6, "Phase 7: Thermal Equilibrium (oteedy/ol)",     {"oteedy", "qoteedy", "ol"}),
    (7, "Shutdown: System Flush Outlet (am)",           {"am"}),
]

# Subsystem groups for Section x Subsystem Enrichment Matrix (Test 3)
SUBSYSTEM_GROUPS: List[Tuple[str, str, Set[str]]] = [
    ("Check Valves (shol/shor)",         "Claimed: Herbal (H)",       {"shol", "shor"}),
    ("Steam Traps (ar/or)",              "Claimed: Herbal/Astro",     {"ar", "or"}),
    ("Liquid Loop (qokain/ii/edy)",      "Claimed: Balneo (B)",       {"qokain", "qokaiin", "qokaiiin", "qokedy", "qokeedy"}),
    ("Steam 3-Way (qotain/ii/iii)",      "Claimed: Balneo (B)",       {"qotain", "qotaiin", "qotaiiin"}),
    ("Accumulator (kedy/shedy)",         "Claimed: Balneo (B)",       {"kedy", "shedy"}),
    ("Chem Dosing (chey/qochey)",        "Claimed: Pharma (P)",       {"chey", "qochey"}),
    ("Bain-Marie (chol/qochol)",         "Claimed: Herbal/Pharma",    {"chol", "qochol"}),
    ("Sight Glass (dain/daiin)",         "Claimed: Balneo/Global",    {"dain", "daiin"}),
    ("Header Tank (otain/otaiin)",       "Claimed: Astro/Balneo",     {"otain", "otaiin"}),
    ("System Flush (am)",                "Claimed: Pharma/Endings",   {"am"}),
]


@dataclass
class FolioRecord:
    folio: str
    section: str = "?"
    currier: str = "?"
    tokens: List[str] = field(default_factory=list)
    paragraphs: List[List[str]] = field(default_factory=list)


def fallback_section_from_folio(folio: str) -> str:
    """Fallback codicological section assignment if IVTFF $I= header tags are absent."""
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


def parse_ivtff_structured(filepath: str) -> List[FolioRecord]:
    """Parses IVTFF 2.0 into per-folio and per-paragraph token streams with $I= and$L= metadata."""
    folios: Dict[str, FolioRecord] = {}
    order: List[str] = []

    header_re = re.compile(r"^#?\s*<(f[0-9]+[rv][0-9]*|fRos)>\s*<!(.*?)>", re.IGNORECASE)
    locus_re = re.compile(r"^<(f[0-9]+[rv][0-9]*|fRos)\.[^>]+>", re.IGNORECASE)

    current_folio = ""
    current_para: List[str] = []

    def get_or_create(fid: str) -> FolioRecord:
        if fid not in folios:
            folios[fid] = FolioRecord(folio=fid, section=fallback_section_from_folio(fid))
            order.append(fid)
        return folios[fid]

    def flush_para(fid: str) -> None:
        nonlocal current_para
        if fid and current_para:
            folios[fid].paragraphs.append(current_para)
            current_para = []

    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        for raw_line in f:
            stripped = raw_line.strip()
            if not stripped:
                continue

            hm = header_re.match(stripped)
            if hm:
                fid = hm.group(1)
                meta = hm.group(2)
                if current_folio and current_folio != fid:
                    flush_para(current_folio)
                rec = get_or_create(fid)
                sec_m = re.search(r"\$I=([A-Z])", meta)
                cur_m = re.search(r"\$L=([A-Z])", meta)
                if sec_m:
                    rec.section = sec_m.group(1)
                if cur_m:
                    rec.currier = cur_m.group(1)
                current_folio = fid
                continue

            lm = locus_re.match(stripped)
            if not lm:
                continue

            fid = lm.group(1)
            if current_folio and current_folio != fid:
                flush_para(current_folio)
            current_folio = fid
            rec = get_or_create(fid)

            has_start = "<%>" in stripped
            has_end = "<$>" in stripped
            is_para_locus = ",@P" in stripped or ",+P" in stripped or ",*P" in stripped or ",=P" in stripped

            tokens = normalize_ivtff_line(raw_line)
            if not tokens:
                continue

            rec.tokens.extend(tokens)

            if has_start:
                flush_para(fid)
                current_para.extend(tokens)
            elif current_para or is_para_locus:
                current_para.extend(tokens)

            if has_end:
                flush_para(fid)

    if current_folio:
        flush_para(current_folio)

    return [folios[fid] for fid in order]


def eval_causality_units(
    units: List[Tuple[str, List[str]]],
    is_qok,
    is_qot,
    trials: int = 1000,
    seed: int = 2026,
) -> Dict[str, object]:
    """
    Exact within-unit Monte Carlo causality test.
    For every unit (folio or paragraph) containing >=1 qok and >=1 qot:
      - Checks if first(qok) < first(qot) (liquid priming before steam diversion).
      - Computes normalized mean position shift: mean_pos(qot) - mean_pos(qok).
      - Compares against 1,000 exact uniform random within-unit position permutations.
    """
    rng = random.Random(seed)
    qualifying: List[Tuple[str, int, int, int, bool, float]] = []

    for unit_id, toks in units:
        n = len(toks)
        if n < 2:
            continue
        qok_pos = [i for i, t in enumerate(toks) if is_qok(t)]
        qot_pos = [i for i, t in enumerate(toks) if is_qot(t)]
        if not qok_pos or not qot_pos:
            continue

        qok_first = qok_pos[0] < qot_pos[0]
        norm = float(n - 1)
        mean_qok = sum(qok_pos) / (len(qok_pos) * norm)
        mean_qot = sum(qot_pos) / (len(qot_pos) * norm)
        delta_pos = mean_qot - mean_qok
        qualifying.append((unit_id, n, len(qok_pos), len(qot_pos), qok_first, delta_pos))

    m = len(qualifying)
    if m == 0:
        return {"n_units": 0}

    obs_first_hits = sum(1 for item in qualifying if item[4])
    obs_contradictions = m - obs_first_hits
    obs_first_rate = (obs_first_hits / m) * 100.0
    obs_mean_delta = statistics.mean(item[5] for item in qualifying)

    null_first_rates: List[float] = []
    null_deltas: List[float] = []

    for _ in range(trials):
        hits = 0
        delta_sum = 0.0
        for _, n, k_qok, k_qot, _, _ in qualifying:
            sample = rng.sample(range(n), k_qok + k_qot)
            p_qok = sample[:k_qok]
            p_qot = sample[k_qok:]
            if min(p_qok) < min(p_qot):
                hits += 1
            norm = float(n - 1)
            delta_sum += (sum(p_qot) / (k_qot * norm)) - (sum(p_qok) / (k_qok * norm))
        null_first_rates.append((hits / m) * 100.0)
        null_deltas.append(delta_sum / m)

    null_first_mean = statistics.mean(null_first_rates)
    null_first_sd = statistics.stdev(null_first_rates) if trials > 1 else 0.0
    z_first = (obs_first_rate - null_first_mean) / null_first_sd if null_first_sd > 0 else 0.0
    p_first = (sum(1 for r in null_first_rates if r >= obs_first_rate) + 1) / (trials + 1)

    null_delta_mean = statistics.mean(null_deltas)
    null_delta_sd = statistics.stdev(null_deltas) if trials > 1 else 0.0
    z_delta = (obs_mean_delta - null_delta_mean) / null_delta_sd if null_delta_sd > 0 else 0.0
    p_delta = (sum(1 for d in null_deltas if d >= obs_mean_delta) + 1) / (trials + 1)

    if (z_first >= 2.0 and p_first < 0.05) or (z_delta >= 2.0 and p_delta < 0.05):
        verdict = "[SUPPORTED]"
    elif z_first <= -2.0 or z_delta <= -2.0:
        verdict = "[FALSIFIED / CONTRADICTED]"
    else:
        verdict = "[INCONCLUSIVE / NULL]"

    return {
        "n_units": m,
        "obs_first_hits": obs_first_hits,
        "obs_contradictions": obs_contradictions,
        "obs_first_rate": obs_first_rate,
        "null_first_mean": null_first_mean,
        "null_first_sd": null_first_sd,
        "z_first": z_first,
        "p_first": p_first,
        "obs_mean_delta": obs_mean_delta,
        "null_delta_mean": null_delta_mean,
        "null_delta_sd": null_delta_sd,
        "z_delta": z_delta,
        "p_delta": p_delta,
        "verdict": verdict,
    }


def spearman_rho(xs: List[float], ys: List[float]) -> float:
    """Computes Spearman's rank correlation coefficient for two equal-length lists."""
    n = len(xs)
    if n < 2:
        return 0.0

    def rank_vector(vals: List[float]) -> List[float]:
        indexed = sorted(enumerate(vals), key=lambda kv: kv[1])
        ranks = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and indexed[j + 1][1] == indexed[i][1]:
                j += 1
            avg_rank = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                ranks[indexed[k][0]] = avg_rank
            i = j + 1
        return ranks

    rx = rank_vector(xs)
    ry = rank_vector(ys)
    mx = statistics.mean(rx)
    my = statistics.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den > 0 else 0.0


def run_test1_causality(folios: List[FolioRecord], trials: int = 1000) -> None:
    print("=== TEST 1: THERMODYNAMIC CAUSALITY (qok- LIQUID PRIMING -> qot- STEAM DIVERSION) ===")
    print("Null Model: 1,000 exact within-folio / within-paragraph token-order permutations.\n")

    all_folio_units = [(r.folio, r.tokens) for r in folios]
    balneo_folio_units = [(r.folio, r.tokens) for r in folios if r.section == "B"]
    all_para_units = [
        (f"{r.folio}#P{idx}", p)
        for r in folios
        for idx, p in enumerate(r.paragraphs, start=1)
    ]
    balneo_para_units = [
        (f"{r.folio}#P{idx}", p)
        for r in folios
        if r.section == "B"
        for idx, p in enumerate(r.paragraphs, start=1)
    ]

    scenarios = [
        ("1A. All Folios — Strict L1 (qokain/ii/iii -> qotain/ii/iii)", all_folio_units, lambda t: t in QOK_STRICT, lambda t: t in QOT_STRICT),
        ("1B. Balneo Folios (f75r-f84v) — Strict L1",                   balneo_folio_units, lambda t: t in QOK_STRICT, lambda t: t in QOT_STRICT),
        ("1C. All Paragraphs — Strict L1",                              all_para_units, lambda t: t in QOK_STRICT, lambda t: t in QOT_STRICT),
        ("1D. All Folios — Broad Cores (qok* -> qot*)",                 all_folio_units, lambda t: t.startswith("qok"), lambda t: t.startswith("qot")),
        ("1E. Balneo Paragraphs — Broad Cores (qok* -> qot*)",          balneo_para_units, lambda t: t.startswith("qok"), lambda t: t.startswith("qot")),
    ]

    for title, units, fn_qok, fn_qot in scenarios:
        res = eval_causality_units(units, fn_qok, fn_qot, trials=trials)
        print(f"  [{title}]")
        if res["n_units"] == 0:
            print("    No qualifying units containing both qok and qot.\n")
            continue
        p1 = res["p_first"]
        p2 = res["p_delta"]
        p1_s = f"p < 0.001 ({p1:.4f})" if p1 < 0.001 else f"p = {p1:.4f}"
        p2_s = f"p < 0.001 ({p2:.4f})" if p2 < 0.001 else f"p = {p2:.4f}"
        print(
            f"    Qualifying Units       : {res['n_units']} "
            f"(qok-first: {res['obs_first_hits']}, Contradictions qot-first: {res['obs_contradictions']})"
        )
        print(
            f"    First-Occurrence Rate  : {res['obs_first_rate']:5.2f}% vs Null {res['null_first_mean']:5.2f}% "
            f"(SD={res['null_first_sd']:.2f}%) | Z = {res['z_first']:+.2f} | {p1_s}"
        )
        print(
            f"    Mean Position Shift Δp : {res['obs_mean_delta']:+.4f} vs Null {res['null_delta_mean']:+.4f} "
            f"(SD={res['null_delta_sd']:.4f}) | Z = {res['z_delta']:+.2f} | {p2_s}"
        )
        print(f"    Verdict                : {res['verdict']}\n")


def run_test2_cold_start(folios: List[FolioRecord], trials: int = 1000) -> None:
    print("=== TEST 2: 7-PHASE COLD-START POSITIONAL MONOTONICITY & FLUSH ('am') AUDIT ===")
    print("Normalized paragraph position: 0.000 = paragraph start, 0.500 = midpoint, 1.000 = paragraph end.\n")

    phase_positions: Dict[int, List[float]] = defaultdict(list)
    am_paras: List[Tuple[int, int, float]] = []

    for r in folios:
        for p in r.paragraphs:
            n = len(p)
            if n < 5:
                continue
            norm = float(n - 1)
            am_pos_here = []
            for idx, tok in enumerate(p):
                pos = idx / norm
                for phase_id, _, tok_set in COLD_START_PHASES:
                    if tok in tok_set:
                        phase_positions[phase_id].append(pos)
                if tok == "am":
                    am_pos_here.append(pos)
            if am_pos_here:
                am_paras.append((n, len(am_pos_here), statistics.mean(am_pos_here)))

    print(f"  {'Claimed Order':<46} | {'Hits':>5} | {'Mean Pos':>8} | {'SD':>6}")
    print("  " + "-" * 74)
    expected_ranks: List[float] = []
    observed_means: List[float] = []
    for phase_id, label, _ in COLD_START_PHASES:
        vals = phase_positions[phase_id]
        if vals:
            mu = statistics.mean(vals)
            sd = statistics.stdev(vals) if len(vals) > 1 else 0.0
            expected_ranks.append(float(phase_id))
            observed_means.append(mu)
            print(f"  {label:<46} | {len(vals):>5d} | {mu:>8.4f} | {sd:>6.4f}")
        else:
            print(f"  {label:<46} |     0 |      N/A |    N/A")

    rho = spearman_rho(expected_ranks, observed_means)
    mono_verdict = "[SUPPORTED]" if rho >= 0.70 else ("[FALSIFIED / CONTRADICTED]" if rho <= -0.50 else "[INCONCLUSIVE / NULL]")
    print(f"\n  Spearman Rank Correlation (Claimed 1->7 vs Observed Mean Position): rho = {rho:+.3f} -> {mono_verdict}")

    if am_paras:
        rng = random.Random(2027)
        obs_am = statistics.mean(item[2] for item in am_paras)
        null_am: List[float] = []
        for _ in range(trials):
            s_val = 0.0
            for n, k, _ in am_paras:
                samp = rng.sample(range(n), k)
                s_val += sum(samp) / (k * float(n - 1))
            null_am.append(s_val / len(am_paras))
        mu_null = statistics.mean(null_am)
        sd_null = statistics.stdev(null_am) if trials > 1 else 0.0
        z_am = (obs_am - mu_null) / sd_null if sd_null > 0 else 0.0
        p_am = (sum(1 for x in null_am if x >= obs_am) + 1) / (trials + 1)
        p_am_s = f"p < 0.001 ({p_am:.4f})" if p_am < 0.001 else f"p = {p_am:.4f}"
        am_verdict = "[SUPPORTED]" if (z_am >= 2.0 and p_am < 0.05) else ("[FALSIFIED / CONTRADICTED]" if z_am <= -2.0 else "[INCONCLUSIVE / NULL]")
        print(
            f"  End-of-Paragraph Flush ('am', {len(am_paras)} paras) : "
            f"Obs Pos = {obs_am:.4f} vs Null {mu_null:.4f} (SD={sd_null:.4f}) | Z = {z_am:+.2f} | {p_am_s} -> {am_verdict}\n"
        )


def run_test3_section_matrix(folios: List[FolioRecord]) -> None:
    print("=== TEST 3: SECTION x SUBSYSTEM ENRICHMENT MATRIX (HITS PER 1,000 TOKENS) ===")
    print("Stratified across codicological sections AND Currier Language A vs. B to expose confounding.\n")

    sec_totals: Counter = Counter()
    sec_group_hits: Dict[str, Counter] = defaultdict(Counter)
    currier_totals: Counter = Counter()
    currier_group_hits: Dict[str, Counter] = defaultdict(Counter)

    for r in folios:
        sec = r.section if r.section in ("H", "B", "P", "S", "T") else ("AZC" if r.section in ("A", "Z", "C") else "?")
        sec_totals[sec] += len(r.tokens)
        if r.currier in ("A", "B"):
            currier_totals[r.currier] += len(r.tokens)
        for tok in r.tokens:
            for gname, _, gset in SUBSYSTEM_GROUPS:
                if tok in gset:
                    sec_group_hits[sec][gname] += 1
                    if r.currier in ("A", "B"):
                        currier_group_hits[r.currier][gname] += 1

    cols = ["H", "B", "P", "AZC", "S"]
    header = (
        f"  {'Subsystem (L1)':<27} | {'Claimed':<22} | "
        + " | ".join(f"{c:>6}" for c in cols)
        + " ||  Cur-A |  Cur-B | Ratio B/A"
    )
    print(header)
    print("  " + "-" * (len(header) - 2))

    for gname, claimed, _ in SUBSYSTEM_GROUPS:
        rates = []
        for c in cols:
            tot = sec_totals[c]
            rate = (sec_group_hits[c][gname] / tot * 1000.0) if tot > 0 else 0.0
            rates.append(f"{rate:6.2f}")
        ra = (currier_group_hits["A"][gname] / currier_totals["A"] * 1000.0) if currier_totals["A"] > 0 else 0.0
        rb = (currier_group_hits["B"][gname] / currier_totals["B"] * 1000.0) if currier_totals["B"] > 0 else 0.0
        ratio_s = f"{rb / ra:6.2f}x" if ra > 0 else "   inf"
        print(f"  {gname:<27} | {claimed:<22} | " + " | ".join(rates) + f" || {ra:6.2f} | {rb:6.2f} | {ratio_s}")

    print(
        f"\n  Section Token Totals: "
        + ", ".join(f"{c}={sec_totals[c]}" for c in cols)
        + f" | Currier A={currier_totals['A']}, Currier B={currier_totals['B']}\n"
    )


def run_test4_unknown_audit(folios: List[FolioRecord]) -> None:
    print("=== TEST 4: RESIDUAL 13-15% UNKNOWN CONTRADICTION & BOUNDARY AUDIT ===")
    print("Tests whether unmapped tokens cluster in critical switching windows or break siphon repeats.\n")

    sec_tot: Counter = Counter()
    sec_unk: Counter = Counter()

    total_toks = 0
    total_unk = 0
    qot_neighbor_tot = 0
    qot_neighbor_unk = 0
    broken_siphon_unk = 0
    broken_siphon_known = 0

    for r in folios:
        sec = r.section if r.section in ("H", "B", "P", "S", "T") else ("AZC" if r.section in ("A", "Z", "C") else "?")
        layers = [classify_token(t)[0] for t in r.tokens]
        n = len(r.tokens)
        sec_tot[sec] += n
        total_toks += n

        for i, (tok, lay) in enumerate(zip(r.tokens, layers)):
            if lay == "UNKNOWN":
                sec_unk[sec] += 1
                total_unk += 1

            if tok.startswith("qot"):
                for nb in (i - 1, i + 1):
                    if 0 <= nb < n:
                        qot_neighbor_tot += 1
                        if layers[nb] == "UNKNOWN":
                            qot_neighbor_unk += 1

            if 1 <= i < n - 1 and r.tokens[i - 1] == r.tokens[i + 1] and r.tokens[i - 1] in VOYNICH_FULL_LUT:
                if lay == "UNKNOWN":
                    broken_siphon_unk += 1
                else:
                    broken_siphon_known += 1

    base_unk_rate = (total_unk / total_toks * 100.0) if total_toks else 0.0
    qot_unk_rate = (qot_neighbor_unk / qot_neighbor_tot * 100.0) if qot_neighbor_tot else 0.0
    gap_tot = broken_siphon_unk + broken_siphon_known
    gap_unk_rate = (broken_siphon_unk / gap_tot * 100.0) if gap_tot else 0.0

    print(f"  Global Residual UNKNOWN Rate                  : {total_unk}/{total_toks} ({base_unk_rate:.2f}%)")
    print(f"  UNKNOWN Adjacent to Steam Switch (qot* +/-1)  : {qot_neighbor_unk}/{qot_neighbor_tot} ({qot_unk_rate:.2f}%)")
    print(f"  UNKNOWN Interrupting Siphon Triplets (X.?.X)  : {broken_siphon_unk}/{gap_tot} ({gap_unk_rate:.2f}%)\n")

    print("  Residual UNKNOWN Rate by Codicological Section:")
    for sec in ("H", "B", "P", "AZC", "S", "T"):
        if sec_tot[sec] > 0:
            rate = sec_unk[sec] / sec_tot[sec] * 100.0
            print(f"    Section {sec:<3} : {sec_unk[sec]:5d} / {sec_tot[sec]:5d} ({rate:5.2f}%)")
    print()


def run_layer1_falsification_suite(zl_path: str, rf_path: str) -> None:
    print("==========================================================================")
    print("L0-ISM v2.1 LAYER I FALSIFICATION SUITE (SEQUENCE ORDER & CONTRADICTIONS)")
    print("==========================================================================\n")

    for label, path in [("PRIMARY CORPUS (ZL3b-n)", zl_path), ("CROSS-CHECK CORPUS (RF1b-e)", rf_path)]:
        print("##########################################################################")
        print(f"AUDIT TARGET: {label} -> {path}")
        print("##########################################################################\n")
        folios = parse_ivtff_structured(path)
        n_paras = sum(len(r.paragraphs) for r in folios)
        n_toks = sum(len(r.tokens) for r in folios)
        print(f"Parsed {len(folios)} folios | {n_paras} paragraphs | {n_toks} normalized EVA tokens.\n")

        run_test1_causality(folios, trials=1000)
        run_test2_cold_start(folios, trials=1000)
        run_test3_section_matrix(folios)
        run_test4_unknown_audit(folios)


if __name__ == "__main__":
    zl_file = sys.argv[1] if len(sys.argv) > 1 else "ZL3b-n.txt"
    rf_file = sys.argv[2] if len(sys.argv) > 2 else "RF1b-e.txt"
    run_layer1_falsification_suite(zl_file, rf_file)
