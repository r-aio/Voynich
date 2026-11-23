#!/usr/bin/env python3
"""
L0-ISM v2.6 — Codex Continuity, Cross-Transcription Divergence & Locus-Type Audit
Evaluates three physical/codicological hypotheses using IVTFF metadata and
dual-transcription comparisons (ZL3b-n.txt vs. RF1b-e.txt):

  1. Quire ($Q), Section ($I), Currier ($L) & Scribe ($H) Continuity:
     Detects transitions/jumps across ordered folios and compares adjacent-folio
     vocabulary Jaccard overlap within the same quire vs. across quires.
  2. Per-Folio Cross-Transcription Divergence & Residual UNKNOWN Audit:
     Compares ZL3b-n vs. RF1b-e token streams per folio to flag high-divergence
     folios (where bleed-through, damage, or difficult layout often cluster)
     alongside per-folio UNKNOWN rates.
  3. Locus / Line-Type Structural Contrast (Continuous vs. Diagram/Label Loci):
     Compares line token lengths and residual UNKNOWN rates across IVTFF locus
     types (e.g., paragraph lines @P, circle/ring/label/radial loci if present).
"""

import re
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from voynich_ivtff_auditor import MASTER_L2A_REGEX, VOYNICH_FULL_LUT, normalize_ivtff_line


@dataclass
class LocusRecord:
    folio: str
    locus_id: str
    locus_type: str
    quire: str
    section: str
    currier: str
    scribe: str
    tokens: List[str]


def is_known_structural(tok: str, l1_set: Set[str]) -> bool:
    if not tok:
        return False
    if tok in l1_set:
        return True
    if MASTER_L2A_REGEX.fullmatch(tok) is not None:
        return True
    if len(tok) == 1 and tok.isalpha():
        return True
    return False


def parse_ivtff_records(filepath: str) -> List[LocusRecord]:
    header_re = re.compile(r"^#?\s*<(f[0-9]+[rv][0-9]*|fRos)>\s*<!(.*?)>", re.IGNORECASE)
    locus_re = re.compile(r"^<(f[0-9]+[rv][0-9]*|fRos)\.([^>\s]+)>\s*(.*)$", re.IGNORECASE)

    folio_meta: Dict[str, Dict[str, str]] = {}
    records: List[LocusRecord] = []

    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        for raw in f:
            s = raw.strip()
            if not s:
                continue

            hm = header_re.match(s)
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

            lm = locus_re.match(s)
            if not lm:
                continue

            fid = lm.group(1).lower()
            loc_id = lm.group(2)
            body = lm.group(3)

            # Locus code in IVTFF often follows semicolon in locus_id, e.g., f1r.1;H or f57v.1;C
            ltype = "?"
            if ";" in loc_id:
                tail = loc_id.split(";", 1)[1]
                code_m = re.match(r"([A-Za-z0-9]+)", tail)
                if code_m:
                    ltype = code_m.group(1)
            else:
                # Fallback: check inline locus type markers if present
                inline_m = re.search(r";([A-Za-z0-9]+)>", raw)
                if inline_m:
                    ltype = inline_m.group(1)

            # Also check inline $H / $L / $Q overrides if present
            fmeta = folio_meta.get(fid, {})
            quire = fmeta.get("quire", "?")
            section = fmeta.get("section", "?")
            currier = fmeta.get("currier", "?")
            scribe = fmeta.get("scribe", "?")

            h_ov = re.search(r"\$H=([A-Z0-9]+)", body)
            if h_ov:
                scribe = h_ov.group(1)
            l_ov = re.search(r"\$L=([A-Z])", body)
            if l_ov:
                currier = l_ov.group(1)

            toks = normalize_ivtff_line(raw)
            if toks:
                records.append(
                    LocusRecord(
                        folio=fid,
                        locus_id=loc_id,
                        locus_type=ltype,
                        quire=quire,
                        section=section,
                        currier=currier,
                        scribe=scribe,
                        tokens=toks,
                    )
                )

    return records


def jaccard_overlap(a: List[str], b: List[str]) -> Optional[float]:
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return None
    union = sa | sb
    return len(sa & sb) / len(union) if union else None


def run_check1_codex_continuity(records: List[LocusRecord]) -> None:
    print("=== CHECK 1: QUIRE ($Q), SECTION ($I), CURRIER ($L) & SCRIBE ($H) CONTINUITY ===")

    ordered_folios: List[str] = []
    folio_info: Dict[str, LocusRecord] = {}
    folio_tokens: Dict[str, List[str]] = defaultdict(list)

    for r in records:
        if r.folio not in folio_info:
            ordered_folios.append(r.folio)
            folio_info[r.folio] = r
        folio_tokens[r.folio].extend(r.tokens)

    quire_changes = 0
    sec_changes = 0
    cur_changes = 0
    scr_changes = 0

    same_quire_jacc: List[float] = []
    diff_quire_jacc: List[float] = []
    notable_jumps: List[str] = []

    for idx in range(1, len(ordered_folios)):
        prev_f = ordered_folios[idx - 1]
        cur_f = ordered_folios[idx]
        p = folio_info[prev_f]
        c = folio_info[cur_f]

        dq = p.quire != c.quire
        ds = p.section != c.section
        dl = p.currier != c.currier
        dh = p.scribe != c.scribe

        if dq:
            quire_changes += 1
        if ds:
            sec_changes += 1
        if dl:
            cur_changes += 1
        if dh:
            scr_changes += 1

        j = jaccard_overlap(folio_tokens[prev_f], folio_tokens[cur_f])
        if j is not None:
            if not dq:
                same_quire_jacc.append(j)
            else:
                diff_quire_jacc.append(j)

        if (not dq) and (ds or dl or dh):
            notable_jumps.append(
                f"{prev_f}->{cur_f} ($Q={c.quire}): "
                f"sec {p.section}->{c.section}, cur {p.currier}->{c.currier}, scribe {p.scribe}->{c.scribe}"
            )

    print(f"  Ordered Folios Evaluated            : {len(ordered_folios)} ({len(ordered_folios) - 1} adjacent transitions)")
    print(f"  Quire ($Q) Boundary Transitions     : {quire_changes}")
    print(f"  Section ($I) Transitions            : {sec_changes}")
    print(f"  Currier ($L) Transitions            : {cur_changes}")
    print(f"  Scribe ($H) Transitions             : {scr_changes}")

    if same_quire_jacc:
        print(
            f"  Adjacent Jaccard (Same Quire, n={len(same_quire_jacc):3d}) : "
            f"mean={statistics.mean(same_quire_jacc):.4f}, median={statistics.median(same_quire_jacc):.4f}"
        )
    if diff_quire_jacc:
        print(
            f"  Adjacent Jaccard (Diff Quire, n={len(diff_quire_jacc):3d}) : "
            f"mean={statistics.mean(diff_quire_jacc):.4f}, median={statistics.median(diff_quire_jacc):.4f}"
        )

    print(f"  Intra-Quire Metadata Shifts (sec/cur/scribe change inside same $Q): {len(notable_jumps)}")
    for item in notable_jumps[:15]:
        print(f"    - {item}")
    print()


def run_check2_dual_transcription_divergence(
    zl_records: List[LocusRecord],
    rf_records: List[LocusRecord],
) -> None:
    print("=== CHECK 2: PER-FOLIO DIVERGENCE (ZL3b-n vs. RF1b-e) & RESIDUAL UNKNOWN RATE ===")
    l1_set = set(VOYNICH_FULL_LUT.keys())

    zl_by_folio: Dict[str, List[str]] = defaultdict(list)
    rf_by_folio: Dict[str, List[str]] = defaultdict(list)

    for r in zl_records:
        zl_by_folio[r.folio].extend(r.tokens)
    for r in rf_records:
        rf_by_folio[r.folio].extend(r.tokens)

    all_folios = sorted(set(zl_by_folio.keys()) | set(rf_by_folio.keys()))

    folio_rows: List[Tuple[float, float, int, int, str]] = []
    for fid in all_folios:
        zt = zl_by_folio.get(fid, [])
        rt = rf_by_folio.get(fid, [])
        n_min = min(len(zt), len(rt))
        n_max = max(len(zt), len(rt))
        if n_max == 0:
            continue

        pos_diffs = sum(1 for i in range(n_min) if zt[i] != rt[i]) + abs(len(zt) - len(rt))
        pos_div_pct = (pos_diffs / n_max) * 100.0

        zl_unk = sum(1 for t in zt if not is_known_structural(t, l1_set))
        zl_unk_pct = (zl_unk / len(zt)) * 100.0 if zt else 0.0

        folio_rows.append((pos_div_pct, zl_unk_pct, len(zt), len(rt), fid))

    if not folio_rows:
        print("  No overlapping folios found.\n")
        return

    mean_div = statistics.mean(r[0] for r in folio_rows)
    med_div = statistics.median(r[0] for r in folio_rows)
    print(f"  Folios Compared                     : {len(folio_rows)}")
    print(f"  Per-Folio Positional Token Diff Rate: mean={mean_div:.2f}%, median={med_div:.2f}%")

    print("\n  Top 15 Folios by Positional Token Divergence (ZL3b-n vs. RF1b-e):")
    print("  Folio    |  ZL Toks |  RF Toks | PosDiff % | ZL Unk %")
    print("  -------------------------------------------------------")
    for div_p, unk_p, n_z, n_r, fid in sorted(folio_rows, reverse=True)[:15]:
        print(f"  {fid:<8} | {n_z:8d} | {n_r:8d} | {div_p:8.2f}% | {unk_p:7.2f}%")

    print("\n  Top 10 Folios by ZL3b-n Residual UNKNOWN Rate (min 20 tokens):")
    print("  Folio    |  ZL Toks | ZL Unk % | PosDiff %")
    print("  ---------------------------------------------")
    unk_elig = [r for r in folio_rows if r[2] >= 20]
    for div_p, unk_p, n_z, _, fid in sorted(unk_elig, key=lambda x: x[1], reverse=True)[:10]:
        print(f"  {fid:<8} | {n_z:8d} | {unk_p:7.2f}% | {div_p:8.2f}%")
    print()


def run_check3_locus_type_contrast(records: List[LocusRecord]) -> None:
    print("=== CHECK 3: LOCUS / LINE-TYPE CONTRAST (LINE LENGTH & RESIDUAL UNKNOWN RATE) ===")
    l1_set = set(VOYNICH_FULL_LUT.keys())

    by_type_lines: Dict[str, List[int]] = defaultdict(list)
    by_type_toks: Dict[str, List[str]] = defaultdict(list)

    for r in records:
        by_type_lines[r.locus_type].append(len(r.tokens))
        by_type_toks[r.locus_type].extend(r.tokens)

    print("  LocusType | Lines |   Tokens | MeanLen | MedLen | Unk Rate")
    print("  ----------------------------------------------------------")
    for ltype in sorted(by_type_toks.keys(), key=lambda k: len(by_type_toks[k]), reverse=True):
        lens = by_type_lines[ltype]
        toks = by_type_toks[ltype]
        n_lines = len(lens)
        n_toks = len(toks)
        m_len = statistics.mean(lens) if lens else 0.0
        med_len = statistics.median(lens) if lens else 0.0
        unk_cnt = sum(1 for t in toks if not is_known_structural(t, l1_set))
        unk_pct = (unk_cnt / n_toks) * 100.0 if n_toks else 0.0
        print(f"  {ltype:<9} | {n_lines:5d} | {n_toks:8d} | {m_len:7.2f} | {med_len:6.1f} | {unk_pct:7.2f}%")
    print()


def main() -> None:
    zl_path = sys.argv[1] if len(sys.argv) > 1 else "ZL3b-n.txt"
    rf_path = sys.argv[2] if len(sys.argv) > 2 else "RF1b-e.txt"

    print("==========================================================================")
    print("L0-ISM v2.6 — CODEX CONTINUITY, DIVERGENCE & LOCUS-TYPE AUDIT")
    print("==========================================================================\n")

    zl_records = parse_ivtff_records(zl_path)
    print(f"Loaded {len(zl_records)} locus lines across {len({r.folio for r in zl_records})} folios from {zl_path}.\n")

    run_check1_codex_continuity(zl_records)
    run_check3_locus_type_contrast(zl_records)

    try:
        rf_records = parse_ivtff_records(rf_path)
        if rf_records:
            print(f"Loaded {len(rf_records)} locus lines across {len({r.folio for r in rf_records})} folios from {rf_path}.\n")
            run_check2_dual_transcription_divergence(zl_records, rf_records)
    except FileNotFoundError:
        print(f"[INFO] Secondary corpus {rf_path} not found; skipping dual-transcription divergence.\n")


if __name__ == "__main__":
    main()
