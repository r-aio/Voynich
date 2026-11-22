#!/usr/bin/env python3
"""
L0-ISM Voynich Manuscript (Beinecke MS 408) — Positional & Scribal Ablation Suite (v2.2)
Tests the two competing explanations for the empirical qot* precedence (Z = -3.37 / -3.60)
discovered in v2.1, incorporating codicological constraints documented on voynich.nu:

  1. Paragraph Top-Line Ablation (voynich.nu gallows/top-line anomaly):
     Measures qot*, qok*, ot*, ok*, and gallows (p/f/t/k) density on paragraph line 1 vs.
     body lines, and re-runs the within-folio/paragraph qok* -> qot* causality test AFTER
     stripping all paragraph top lines.
  2. Line-as-a-Functional-Unit Audit (voynich.nu line-initial / line-final constraints):
     Computes exact line-initial, mid-line, and line-final rates and runs a 1,000-trial
     within-line permutation test for both (qok* vs qot*) and (ok* vs ot*).
  3. Prefix-Independent Control (ok* vs ot*):
     Tests whether 't' systematically precedes 'k' even without the 'q-' prefix, isolating
     general Voynichese positional syntax from qo-specific behavior.
  4. Scribe ($H=1..5) x Currier ($L=A/B) x Quire ($Q=) Stratification (Davis / voynich.nu):
     Stratifies qot* precedence by individual scribal hand, isolates Herbal Currier A vs.
     Herbal Currier B (same visual section, different dialect), and audits quire consistency.
"""

import random
import re
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from voynich_ivtff_auditor import normalize_ivtff_line


@dataclass
class LineRecord:
    folio: str
    locus: str
    section: str
    currier: str
    hand: str
    quire: str
    para_id: int
    line_in_para: int  # 0 = top line of paragraph (<%> or @P0), >=1 = body line
    is_para_text: bool
    tokens: List[str] = field(default_factory=list)


def parse_ivtff_lines(filepath: str) -> List[LineRecord]:
    """Parses IVTFF 2.0 line-by-line preserving $I (section), $L (Currier), $H (hand), $Q (quire)."""
    header_re = re.compile(r"^#?\s*<(f[0-9]+[rv][0-9]*|fRos)>\s*<!(.*?)>", re.IGNORECASE)
    locus_re = re.compile(r"^<((f[0-9]+[rv][0-9]*|fRos)\.[^>]+)>", re.IGNORECASE)

    meta_by_folio: Dict[str, Dict[str, str]] = {}
    lines: List[LineRecord] = []

    current_folio = ""
    para_counter = 0
    in_para = False
    line_in_para = 0

    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        for raw_line in f:
            stripped = raw_line.strip()
            if not stripped:
                continue

            hm = header_re.match(stripped)
            if hm:
                fid = hm.group(1)
                meta_str = hm.group(2)
                sec_m = re.search(r"\$I=([A-Z])", meta_str)
                cur_m = re.search(r"\$L=([A-Z])", meta_str)
                hnd_m = re.search(r"\$H=([0-9A-Z])", meta_str)
                qur_m = re.search(r"\$Q=([A-Z])", meta_str)
                meta_by_folio[fid] = {
                    "I": sec_m.group(1) if sec_m else "?",
                    "L": cur_m.group(1) if cur_m else "?",
                    "H": hnd_m.group(1) if hnd_m else "?",
                    "Q": qur_m.group(1) if qur_m else "?",
                }
                if current_folio != fid:
                    in_para = False
                    line_in_para = 0
                current_folio = fid
                continue

            lm = locus_re.match(stripped)
            if not lm:
                continue

            locus = lm.group(1)
            fid = lm.group(2)
            if current_folio != fid:
                in_para = False
                line_in_para = 0
                current_folio = fid

            tokens = normalize_ivtff_line(raw_line)
            if not tokens:
                continue

            is_para = any(tag in locus for tag in (",@P", ",+P", ",*P", ",=P"))
            has_start = "<%>" in stripped or ",@P" in locus
            has_end = "<$>" in stripped

            if is_para:
                if has_start or not in_para:
                    para_counter += 1
                    in_para = True
                    line_in_para = 0
                else:
                    line_in_para += 1
                pid = para_counter
                lip = line_in_para
            else:
                pid = -1
                lip = -1

            meta = meta_by_folio.get(fid, {"I": "?", "L": "?", "H": "?", "Q": "?"})
            lines.append(
                LineRecord(
                    folio=fid,
                    locus=locus,
                    section=meta["I"],
                    currier=meta["L"],
                    hand=meta["H"],
                    quire=meta["Q"],
                    para_id=pid,
                    line_in_para=lip,
                    is_para_text=is_para,
                    tokens=tokens,
                )
            )

            if is_para and has_end:
                in_para = False
                line_in_para = 0

    return lines


def run_within_unit_order_test(
    units: List[Tuple[str, List[str]]],
    fn_a,
    fn_b,
    trials: int = 1000,
    seed: int = 2201,
) -> Dict[str, object]:
    """
    Tests whether family A precedes family B within each unit vs. 1,000 exact within-unit shuffles.
    Negative Z / negative delta_pos means family B systematically precedes family A.
    """
    rng = random.Random(seed)
    qualifying: List[Tuple[int, int, int, bool, float]] = []

    for _, toks in units:
        n = len(toks)
        if n < 2:
            continue
        pos_a = [i for i, t in enumerate(toks) if fn_a(t)]
        pos_b = [i for i, t in enumerate(toks) if fn_b(t)]
        if not pos_a or not pos_b:
            continue
        if len(pos_a) + len(pos_b) > n:
            continue
        a_first = pos_a[0] < pos_b[0]
        norm = float(n - 1)
        delta_pos = (sum(pos_b) / (len(pos_b) * norm)) - (sum(pos_a) / (len(pos_a) * norm))
        qualifying.append((n, len(pos_a), len(pos_b), a_first, delta_pos))

    m = len(qualifying)
    if m == 0:
        return {"n_units": 0}

    obs_first_hits = sum(1 for q in qualifying if q[3])
    obs_first_rate = obs_first_hits / m * 100.0
    obs_delta = statistics.mean(q[4] for q in qualifying)

    null_first: List[float] = []
    null_delta: List[float] = []
    for _ in range(trials):
        hits = 0
        dsum = 0.0
        for n, ka, kb, _, _ in qualifying:
            samp = rng.sample(range(n), ka + kb)
            pa = samp[:ka]
            pb = samp[ka:]
            if min(pa) < min(pb):
                hits += 1
            norm = float(n - 1)
            dsum += (sum(pb) / (kb * norm)) - (sum(pa) / (ka * norm))
        null_first.append(hits / m * 100.0)
        null_delta.append(dsum / m)

    nf_mu = statistics.mean(null_first)
    nf_sd = statistics.stdev(null_first) if trials > 1 else 0.0
    z_first = (obs_first_rate - nf_mu) / nf_sd if nf_sd > 0 else 0.0

    nd_mu = statistics.mean(null_delta)
    nd_sd = statistics.stdev(null_delta) if trials > 1 else 0.0
    z_delta = (obs_delta - nd_mu) / nd_sd if nd_sd > 0 else 0.0

    # Two-sided empirical p-value for first-occurrence shift
    if obs_first_rate <= nf_mu:
        p_tail = (sum(1 for x in null_first if x <= obs_first_rate) + 1) / (trials + 1)
    else:
        p_tail = (sum(1 for x in null_first if x >= obs_first_rate) + 1) / (trials + 1)
    p_two = min(1.0, 2.0 * p_tail)

    return {
        "n_units": m,
        "a_first": obs_first_hits,
        "b_first": m - obs_first_hits,
        "obs_first_rate": obs_first_rate,
        "null_first_mean": nf_mu,
        "null_first_sd": nf_sd,
        "z_first": z_first,
        "obs_delta": obs_delta,
        "null_delta_mean": nd_mu,
        "null_delta_sd": nd_sd,
        "z_delta": z_delta,
        "p_two": p_two,
    }


def print_order_result(title: str, res: Dict[str, object], label_a: str, label_b: str) -> None:
    print(f"  [{title}]")
    if res["n_units"] == 0:
        print("    No qualifying units.\n")
        return
    p = res["p_two"]
    p_str = f"p < 0.002 ({p:.4f})" if p <= 0.002 else f"p = {p:.4f}"
    direction = f"{label_b} precedes {label_a}" if res["z_first"] <= -2.0 else (
        f"{label_a} precedes {label_b}" if res["z_first"] >= 2.0 else "No significant order bias"
    )
    print(
        f"    Units: {res['n_units']:>4d} ({label_a}-first: {res['a_first']}, {label_b}-first: {res['b_first']}) | "
        f"Rate: {res['obs_first_rate']:5.2f}% vs Null {res['null_first_mean']:5.2f}% (SD={res['null_first_sd']:.2f}%)"
    )
    print(
        f"    First-Occ Z = {res['z_first']:+.2f} ({p_str}) | "
        f"Mean Shift Δp = {res['obs_delta']:+.4f} (Z = {res['z_delta']:+.2f}) -> [{direction}]\n"
    )


def run_ablation1_topline(lines: List[LineRecord], trials: int = 1000) -> None:
    print("=== ABLATION 1: PARAGRAPH TOP-LINE vs. BODY LINES (voynich.nu GALLOWS ANOMALY) ===")
    top_toks = [t for ln in lines if ln.is_para_text and ln.line_in_para == 0 for t in ln.tokens]
    body_toks = [t for ln in lines if ln.is_para_text and ln.line_in_para > 0 for t in ln.tokens]

    n_top = len(top_toks)
    n_body = len(body_toks)
    print(f"  Paragraph Top-Line Tokens (line 0): N = {n_top} | Body-Line Tokens (line >= 1): N = {n_body}\n")

    features = [
        ("qot* (claimed steam)",      lambda t: t.startswith("qot")),
        ("qok* (claimed liquid)",     lambda t: t.startswith("qok")),
        ("ot*  (t-core without q-)",  lambda t: t.startswith("ot")),
        ("ok*  (k-core without q-)",  lambda t: t.startswith("ok")),
        ("p*   (gallows p-initial)",  lambda t: t.startswith("p")),
        ("f*   (gallows f-initial)",  lambda t: t.startswith("f")),
        ("t*   (gallows t-initial)",  lambda t: t.startswith("t")),
        ("k*   (gallows k-initial)",  lambda t: t.startswith("k")),
    ]

    print(f"  {'Token Class':<26} | {'Top-Line /1k':>12} | {'Body /1k':>10} | {'Top/Body Ratio':>14}")
    print("  " + "-" * 70)
    for name, fn in features:
        c_top = sum(1 for t in top_toks if fn(t))
        c_body = sum(1 for t in body_toks if fn(t))
        r_top = (c_top / n_top * 1000.0) if n_top else 0.0
        r_body = (c_body / n_body * 1000.0) if n_body else 0.0
        ratio = (r_top / r_body) if r_body > 0 else float("inf")
        print(f"  {name:<26} | {r_top:>12.2f} | {r_body:>10.2f} | {ratio:>13.2f}x")
    print()

    # Re-run causality test on full paragraphs vs. body-only paragraphs (line 0 stripped)
    para_full: Dict[int, List[str]] = defaultdict(list)
    para_body: Dict[int, List[str]] = defaultdict(list)
    folio_body: Dict[str, List[str]] = defaultdict(list)

    for ln in lines:
        if ln.is_para_text:
            para_full[ln.para_id].extend(ln.tokens)
            if ln.line_in_para > 0:
                para_body[ln.para_id].extend(ln.tokens)
                folio_body[ln.folio].extend(ln.tokens)

    res_p_full = run_within_unit_order_test(
        [(str(k), v) for k, v in para_full.items()],
        lambda t: t.startswith("qok"),
        lambda t: t.startswith("qot"),
        trials=trials,
    )
    res_p_body = run_within_unit_order_test(
        [(str(k), v) for k, v in para_body.items()],
        lambda t: t.startswith("qok"),
        lambda t: t.startswith("qot"),
        trials=trials,
    )
    res_f_body = run_within_unit_order_test(
        [(k, v) for k, v in folio_body.items()],
        lambda t: t.startswith("qok"),
        lambda t: t.startswith("qot"),
        trials=trials,
    )

    print_order_result("1A. Full Paragraphs (All Lines): qok* vs qot*", res_p_full, "qok*", "qot*")
    print_order_result("1B. Paragraphs AFTER Stripping Top Line (Line 0 Removed): qok* vs qot*", res_p_body, "qok*", "qot*")
    print_order_result("1C. Folios AFTER Stripping All Paragraph Top Lines: qok* vs qot*", res_f_body, "qok*", "qot*")


def run_ablation2_line_unit(lines: List[LineRecord], trials: int = 1000) -> None:
    print("=== ABLATION 2: LINE AS A FUNCTIONAL UNIT (voynich.nu LINE-POSITION RULES) ===")
    para_lines = [ln for ln in lines if ln.is_para_text and len(ln.tokens) >= 3]

    init_toks = [ln.tokens[0] for ln in para_lines]
    mid_toks = [t for ln in para_lines for t in ln.tokens[1:-1]]
    fin_toks = [ln.tokens[-1] for ln in para_lines]

    print(
        f"  Evaluated {len(para_lines)} paragraph lines (len >= 3): "
        f"Initial={len(init_toks)}, Mid-Line={len(mid_toks)}, Final={len(fin_toks)}\n"
    )

    classes = [
        ("qot*", lambda t: t.startswith("qot")),
        ("qok*", lambda t: t.startswith("qok")),
        ("ot*",  lambda t: t.startswith("ot")),
        ("ok*",  lambda t: t.startswith("ok")),
        ("qo*",  lambda t: t.startswith("qo")),
    ]
    print(f"  {'Class':<10} | {'Line-Init /1k':>13} | {'Mid-Line /1k':>12} | {'Line-Final /1k':>14} | {'Init/Mid':>8} | {'Final/Mid':>9}")
    print("  " + "-" * 78)
    for name, fn in classes:
        ri = sum(1 for t in init_toks if fn(t)) / len(init_toks) * 1000.0 if init_toks else 0.0
        rm = sum(1 for t in mid_toks if fn(t)) / len(mid_toks) * 1000.0 if mid_toks else 0.0
        rf = sum(1 for t in fin_toks if fn(t)) / len(fin_toks) * 1000.0 if fin_toks else 0.0
        im = (ri / rm) if rm > 0 else 0.0
        fm = (rf / rm) if rm > 0 else 0.0
        print(f"  {name:<10} | {ri:>13.2f} | {rm:>12.2f} | {rf:>14.2f} | {im:>7.2f}x | {fm:>8.2f}x")
    print()

    line_units = [(ln.locus, ln.tokens) for ln in para_lines]
    res_l_qo = run_within_unit_order_test(
        line_units, lambda t: t.startswith("qok"), lambda t: t.startswith("qot"), trials=trials
    )
    res_l_o = run_within_unit_order_test(
        line_units, lambda t: t.startswith("ok"), lambda t: t.startswith("ot"), trials=trials
    )
    print_order_result("2A. Within Single Lines: qok* vs qot*", res_l_qo, "qok*", "qot*")
    print_order_result("2B. Within Single Lines: ok* vs ot* (Prefix-Free Control)", res_l_o, "ok*", "ot*")


def run_ablation3_prefix_control(lines: List[LineRecord], trials: int = 1000) -> None:
    print("=== ABLATION 3: PREFIX-INDEPENDENT CONTROL (ok* vs. ot* ACROSS FOLIOS & PARAGRAPHS) ===")
    print("If ot* also precedes ok* without 'q-', the asymmetry reflects general Voynichese t/k positioning.\n")

    folio_toks: Dict[str, List[str]] = defaultdict(list)
    para_toks: Dict[int, List[str]] = defaultdict(list)
    for ln in lines:
        folio_toks[ln.folio].extend(ln.tokens)
        if ln.is_para_text:
            para_toks[ln.para_id].extend(ln.tokens)

    res_f_o = run_within_unit_order_test(
        [(k, v) for k, v in folio_toks.items()],
        lambda t: t.startswith("ok"),
        lambda t: t.startswith("ot"),
        trials=trials,
    )
    res_p_o = run_within_unit_order_test(
        [(str(k), v) for k, v in para_toks.items()],
        lambda t: t.startswith("ok"),
        lambda t: t.startswith("ot"),
        trials=trials,
    )
    print_order_result("3A. All Folios: ok* vs ot*", res_f_o, "ok*", "ot*")
    print_order_result("3B. All Paragraphs: ok* vs ot*", res_p_o, "ok*", "ot*")


def run_ablation4_scribe_currier_quire(lines: List[LineRecord], trials: int = 1000) -> None:
    print("=== ABLATION 4: SCRIBE ($H), HERBAL A vs. B ISOLATION & QUIRE ($Q) CONTROL ===")
    print("Follows Lisa Fagin Davis's 5-scribe model & voynich.nu metadata to separate scribe from section.\n")

    # Group tokens per folio with metadata
    folio_toks: Dict[str, List[str]] = defaultdict(list)
    folio_meta: Dict[str, Tuple[str, str, str, str]] = {}
    for ln in lines:
        folio_toks[ln.folio].extend(ln.tokens)
        if ln.folio not in folio_meta:
            folio_meta[ln.folio] = (ln.section, ln.currier, ln.hand, ln.quire)

    # 4A: By Scribe ($H)
    hands = sorted({m[2] for m in folio_meta.values() if m[2] != "?"})
    if hands:
        print("  --- 4A. qok* vs qot* Precedence Stratified by Scribal Hand ($H) ---")
        for h in hands:
            units = [(f, folio_toks[f]) for f, m in folio_meta.items() if m[2] == h]
            res = run_within_unit_order_test(
                units, lambda t: t.startswith("qok"), lambda t: t.startswith("qot"), trials=trials
            )
            print_order_result(f"Hand $H={h} (Folios={len(units)})", res, "qok*", "qot*")
    else:
        print("  [Note] No $H= scribal hand metadata present in this IVTFF edition.\n")

    # 4B: Within-Herbal Isolation (Herbal Currier A vs. Herbal Currier B)
    ha_toks = [t for f, toks in folio_toks.items() if folio_meta[f][0] == "H" and folio_meta[f][1] == "A" for t in toks]
    hb_toks = [t for f, toks in folio_toks.items() if folio_meta[f][0] == "H" and folio_meta[f][1] == "B" for t in toks]
    bb_toks = [t for f, toks in folio_toks.items() if folio_meta[f][0] == "B" and folio_meta[f][1] == "B" for t in toks]

    if ha_toks and hb_toks:
        print("  --- 4B. Within-Section Currier Isolation: Herbal-A vs. Herbal-B vs. Balneo-B (per 1,000 tokens) ---")
        print(f"  Token Totals: Herbal-A={len(ha_toks)} | Herbal-B={len(hb_toks)} | Balneo-B={len(bb_toks)}\n")
        probes = [
            ("qok* (claimed liquid)",     lambda t: t.startswith("qok")),
            ("qot* (claimed steam)",      lambda t: t.startswith("qot")),
            ("kedy/shedy (accumulator)",  lambda t: t in {"kedy", "shedy"}),
            ("shol/shor (check valve)",   lambda t: t in {"shol", "shor"}),
            ("chol/qochol (bain-marie)",  lambda t: t in {"chol", "qochol"}),
            ("chey/qochey (chem doser)",  lambda t: t in {"chey", "qochey"}),
        ]
        print(f"  {'Probe Group':<26} | {'Herbal-A':>10} | {'Herbal-B':>10} | {'Balneo-B':>10} | {'HB/HA':>8} | {'BB/HB':>8}")
        print("  " + "-" * 84)
        for name, fn in probes:
            r_ha = sum(1 for t in ha_toks if fn(t)) / len(ha_toks) * 1000.0
            r_hb = sum(1 for t in hb_toks if fn(t)) / len(hb_toks) * 1000.0
            r_bb = sum(1 for t in bb_toks if fn(t)) / len(bb_toks) * 1000.0 if bb_toks else 0.0
            hb_ha = (r_hb / r_ha) if r_ha > 0 else float("inf")
            bb_hb = (r_bb / r_hb) if r_hb > 0 else float("inf")
            print(f"  {name:<26} | {r_ha:>10.2f} | {r_hb:>10.2f} | {r_bb:>10.2f} | {hb_ha:>7.2f}x | {bb_hb:>7.2f}x")
        print()

    # 4C: Quire-level summary of qot* vs qok* precedence (Leave-One-Quire-Out transparency)
    quires = sorted({m[3] for m in folio_meta.values() if m[3] != "?"})
    if quires:
        print("  --- 4C. Quire-by-Quire ($Q) Breakdown of qok* vs qot* First-Occurrence ---")
        print(f"  {'Quire':<6} | {'Sec/Cur':<8} | {'Qual. Folios':>12} | {'qok-first':>9} | {'qot-first':>9} | {'Mean Δp (qot-qok)':>17}")
        print("  " + "-" * 74)
        for q in quires:
            q_folios = [f for f, m in folio_meta.items() if m[3] == q]
            sec_set = "/".join(sorted({folio_meta[f][0] for f in q_folios}))
            cur_set = "/".join(sorted({folio_meta[f][1] for f in q_folios if folio_meta[f][1] != "?"}))
            deltas = []
            qok_f = 0
            qot_f = 0
            for f in q_folios:
                toks = folio_toks[f]
                pa = [i for i, t in enumerate(toks) if t.startswith("qok")]
                pb = [i for i, t in enumerate(toks) if t.startswith("qot")]
                if pa and pb and len(toks) >= 2:
                    if pa[0] < pb[0]:
                        qok_f += 1
                    else:
                        qot_f += 1
                    norm = float(len(toks) - 1)
                    deltas.append((sum(pb) / (len(pb) * norm)) - (sum(pa) / (len(pa) * norm)))
            if deltas:
                print(
                    f"  $Q={q:<3} | {sec_set + ':' + cur_set:<8} | {len(deltas):>12d} | "
                    f"{qok_f:>9d} | {qot_f:>9d} | {statistics.mean(deltas):>+17.4f}"
                )
        print()


def main() -> None:
    zl_file = sys.argv[1] if len(sys.argv) > 1 else "ZL3b-n.txt"
    print("==========================================================================")
    print("L0-ISM v2.2 POSITIONAL & SCRIBAL ABLATION SUITE (voynich.nu CONSTRAINTS)")
    print("==========================================================================\n")
    print(f"Primary Annotated Corpus: {zl_file} (carries $I, $L, $H, $Q codicological tags)\n")

    lines = parse_ivtff_lines(zl_file)
    print(f"Parsed {len(lines)} lines across {len({ln.folio for ln in lines})} folios.\n")

    run_ablation1_topline(lines, trials=1000)
    run_ablation2_line_unit(lines, trials=1000)
    run_ablation3_prefix_control(lines, trials=1000)
    run_ablation4_scribe_currier_quire(lines, trials=1000)


if __name__ == "__main__":
    main()
