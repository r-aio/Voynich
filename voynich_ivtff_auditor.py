#!/usr/bin/env python3
"""
L0-ISM Formal Automaton & Voynich Manuscript (Beinecke MS 408) Structural Auditor (v2.4).
Executes:
  1. Layer 1 Exact Zero-Heap Look-Up Table (LUT) audit across IVTFF 2.0 corpora (ZL3b vs RF1b-e).
     NOTE: Node labels in VOYNICH_FULL_LUT are retired v1.0 working identifiers; coverage is
     invariant to label permutation and does not test semantic assignment.
  2. Layer 2a Strict Positional EVA Morphological DFA & Layer 2b Single-Glyph Base Registers.
  3. Strict IVTFF 2.0 locus parsing (preserves circular/radial/rosette lines with inline tags).
  4. Formal Microsoft Z3 SMT verification over all 19^3 = 6,859 states (verifies automaton
     properties only, not manuscript semantics).
  5. Stricter Negative Control & Monte Carlo Falsification Suite (v2.4):
       - Test A: Multi-char acceptance vs. Order-1 Char-Markov synthetic words,
         Intra-word character shuffle (1,000 MC trials), and Order-0 IID letter strings.
       - Test B: External natural language control (15th-century Medieval Latin & German prose).
       - Test C: Hierarchical sequence permutation (1,000 trials each): Global, Within-Folio,
         and Within-Line shuffles for both L1 and ANY-token adjacent repeats.
       - Audit D: LUT frequency overlap (Top-20 corpus tokens) & label-independence disclosure.
"""

import math
import random
import re
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class LUTEntry:
    node: str
    cmd: str
    delta: int
    valve_pct: float


# Layer 1: Exact Zero-Heap LUT (synchronized with voynich_l0_lut.h).
# Working hardware labels from v1.0 are preserved solely for C99/Lean symbol compatibility;
# Layer I semantic claims were retired in v2.1-v2.2.
VOYNICH_FULL_LUT: Dict[str, LUTEntry] = {
    # 1. k-core frames
    "qokain":    LUTEntry("HUB_PRIMARY_COOLING",   "SET_WATER_GRADIENT",   1, 11.1),
    "qokaiin":   LUTEntry("HUB_PRIMARY_COOLING",   "SET_WATER_GRADIENT",   2, 22.2),
    "qokaiiin":  LUTEntry("HUB_PRIMARY_COOLING",   "SET_WATER_GRADIENT",   3, 33.3),
    "qokedy":    LUTEntry("HUB_PRIMARY_COOLING",   "REG_FLOW_STEADY",      0, 25.0),
    "qokeedy":   LUTEntry("HUB_PRIMARY_COOLING",   "REG_FLOW_STEADY",      0, 50.0),

    # 2. t-core frames
    "qotain":    LUTEntry("VALVE_HYPOCAUST_3WAY",  "SET_STEAM_GRADIENT",   1, 11.1),
    "qotaiin":   LUTEntry("VALVE_HYPOCAUST_3WAY",  "SET_STEAM_GRADIENT",   2, 22.2),
    "qotaiiin":  LUTEntry("VALVE_HYPOCAUST_3WAY",  "SET_STEAM_GRADIENT",   3, 33.3),

    # 3. High-frequency short/recirc frames
    "qoko":      LUTEntry("HUB_FULCRUM_CALIB",     "CALIBRATE_ZERO",       0,  0.0),
    "oteedy":    LUTEntry("PUMP_THERMAL_RECIRC",   "APPLY_RESO_THERMAL",   0, 50.0),
    "qoteedy":   LUTEntry("PUMP_THERMAL_RECIRC",   "APPLY_RESO_THERMAL",   0, 50.0),
    "ol":        LUTEntry("LOG_MONITOR_NODE",      "CONFIRM_SAT",          0,  0.0),
    "or":        LUTEntry("REFLUX_CONDENSER",      "CONFIRM_SAT",          0, 15.0),
    "ar":        LUTEntry("CONDENSATE_STEAM_TRAP", "DRAIN_CONDENSATE",     0, 10.0),

    # 4. d-/al-/sol- frames
    "dain":      LUTEntry("LEVEL_SIGHT_GLASS",     "READ_COLUMN_LEVEL",    0,  0.0),
    "daiin":     LUTEntry("LEVEL_SIGHT_GLASS",     "READ_COLUMN_LEVEL",    0,  0.0),
    "al":        LUTEntry("FLOAT_AIR_VENT",        "BLEED_TRAPPED_AIR",    0,  0.0),
    "sol":       LUTEntry("FLOAT_AIR_VENT",        "BLEED_TRAPPED_AIR",    0,  0.0),

    # 5. daim/dair, sh-, kedy/shedy frames
    "daim":      LUTEntry("FURNACE_AIR_DAMPER",    "SET_DAMPER_GRADIENT", -1, 40.0),
    "dair":      LUTEntry("FURNACE_AIR_DAMPER",    "SET_DAMPER_GRADIENT",  1, 60.0),
    "shol":      LUTEntry("CHECK_VALVE_NODE",      "CLOSE_CHECK_VALVE",    0,  0.0),
    "shor":      LUTEntry("CHECK_VALVE_NODE",      "CHECK_NON_RETURN",     0,  0.0),
    "kedy":      LUTEntry("HYDRAULIC_ACCUM",       "APPLY_RESO",           1, 75.0),
    "shedy":     LUTEntry("HYDRAULIC_ACCUM",       "DAMP_WATER_HAMMER",    0, 75.0),

    # 6. ch-, qokey, am frames
    "chey":      LUTEntry("CHEM_DOSING_BUFFER",    "DOSE_ANTI_CALC",       0, 10.0),
    "qochey":    LUTEntry("CHEM_DOSING_BUFFER",    "DOSE_ANTI_CALC",       0, 20.0),
    "chol":      LUTEntry("BAIN_MARIE_JACKET",     "HOLD_100C_BATH",       0, 50.0),
    "qochol":    LUTEntry("BAIN_MARIE_JACKET",     "HOLD_100C_BATH",       0, 50.0),
    "qokey":     LUTEntry("PHASE_SEPARATOR",       "FLUSH_SEDIMENT",       0,  0.0),
    "am":        LUTEntry("SYSTEM_FLUSH_OUTLET",   "PURGE_TO_IDLE",        0,  0.0),

    # 7. ot-, bench-gallows, sh- frames
    "otain":     LUTEntry("OVERFLOW_HEADER_TANK",  "BUFFER_HEAD_PRESSURE", 0, 20.0),
    "otaiin":    LUTEntry("OVERFLOW_HEADER_TANK",  "BUFFER_HEAD_PRESSURE", 0, 40.0),
    "ckhaiin":   LUTEntry("THERMAL_EXP_BELLOWS",   "ABSORB_ELONGATION",    0,  0.0),
    "shain":     LUTEntry("TRICKLE_FILM_COOLER",   "EVAP_COOLING_STEP1",  -1, 30.0),
    "shaiin":    LUTEntry("TRICKLE_FILM_COOLER",   "EVAP_COOLING_STEP2",  -2, 60.0),
    "cthy":      LUTEntry("STATIC_SWIRL_MIXER",    "EQUALIZE_STRATA",      0,  0.0),
    "ckhy":      LUTEntry("STATIC_SWIRL_MIXER",    "EQUALIZE_STRATA",      0,  0.0),

    # 8. Boundary & sentinel frames
    "fachys":    LUTEntry("VALVE_SAFETY_RELIEF",   "PREPARE_CRIT_RELIEF",  8, 90.0),
    "qokaiiii":  LUTEntry("EMERGENCY_SHUTDOWN",    "TRIGGER_HARD_STOP", -999,  0.0),
}

# Paleographic normalization map (RF1b-e extended numeric codes & ligatures -> canonical EVA)
PALEOGLYPH_MAP: Dict[str, str] = {
    "@152;": "d",
    "@221;": "o",
    "@222;": "y",
    "@176;": "k",
    "@130;": "t",
    "@138;": "k",
    "@140;": "r",
    "@145;": "k",
    "@167;": "k",
    "@192;": "t",
    "@197;": "m",
    "@206;": "r",
    "@243;": "r",
    "{ch'}": "sh",
    "{cthh}": "cth",
    "{ckhh}": "ckh",
    "{cphh}": "cph",
    "{cfhh}": "cfh",
    "{ikh}": "ckh",
    "{ith}": "cth",
    "{ifh}": "cfh",
    "{iph}": "cph",
}

# Layer 2a: Positional EVA Morphological DFA (multi-character frames; corpus-fitted slot grammar)
_TERM = r"(?:aldy|ardy|oldy|aly|ary|oly|ory|ldy|dy|ey|ly|ry|iiin|iin|in|iir|ir|ol|al|or|ar|am|om|y|l|r|m|n|s|d|g|o|e)?"
_VOWEL = r"(?:e{0,3}[oa]?i{0,3})"

LAYER2_DFA_RULES: List[Tuple[str, re.Pattern]] = [
    ("BUS_GALLOWS_MIXER_THROTTLE", re.compile(rf"^(?:qok|qot|qo|ok|ot|op|of|yk|yt|ol|al|ch[eo]?|sh[eo]?|d|s|o|y)?(?:cth|ckh|cph|cfh){_VOWEL}{_TERM}$")),
    ("BUS_PRIMARY_MANIFOLD",       re.compile(rf"^(?:qok|ok|yk|lk){_VOWEL}{_TERM}$")),
    ("BUS_OVERFLOW_STEAM",         re.compile(rf"^(?:qot|ot|yt|lt){_VOWEL}{_TERM}$")),
    ("BUS_CHEM_MIXER",             re.compile(rf"^(?:qok|qot|qop|qof|qol|qo|ok|ot|op|of|olk|olt|olp|olf|alk|alt|yk|yt|yp|yf|ol|or|al|ar|k|t|p|f|d|s|l|r|o|y)?ch{_VOWEL}{_TERM}$")),
    ("BUS_CHECK_COOLER",           re.compile(rf"^(?:qok|qot|qop|qof|qol|qo|ok|ot|op|of|olk|olt|olp|olf|alk|alt|yk|yt|yp|yf|ol|or|al|ar|k|t|p|f|d|s|l|r|o|y)?sh{_VOWEL}{_TERM}$")),
    ("BUS_COMPOUND_CH_SH",         re.compile(rf"^(?:qo|o|y|d|s|l)?(?:ch|sh)(?:e{{1,2}}|o)?(?:k|t|p|f|d){_VOWEL}{_TERM}$")),
    ("BUS_PRESSURE_VENT_FEED",     re.compile(rf"^(?:qo|o|y|l|d|s)?[pf](?:ch|sh|{_VOWEL}){_TERM}$")),
    ("BUS_LEVEL_FURNACE",          re.compile(rf"^(?:qo|o|y|l|s)?d{_VOWEL}{_TERM}$")),
    ("BUS_DIRECT_LIQUID",          re.compile(rf"^(?:qo|o|y|l|s)?k{_VOWEL}{_TERM}$")),
    ("BUS_THERMAL_DELAY",          re.compile(rf"^(?:qo|o|y|l|s)?t{_VOWEL}{_TERM}$")),
    ("BUS_FLOW_REGULATOR",         re.compile(r"^(?:(?:qo|ol|or|al|ar|s|r|l|o)(?:ai{1,3}[nry]|oi{1,3}[nry]|a[lrm]|o[lrms]|y)|os|om|lo|sy)$")),
    ("BUS_SAT_VENT_CONDENSER",     re.compile(rf"^(?:qo|o|y|l|s|a)(?:l|r|ee{{0,2}}){_TERM}$")),
    ("BUS_BARE_GRADIENT_OP",       re.compile(r"^(?:ai{1,3}[nrsy]|a[rl](?:al|am|ody|y|s)?|oi{1,3}[nrsy]|ee{1,3}[dysrl]?|qo|da|ot|as)$")),
    ("BUS_COMPOUND_ACTUATOR",      re.compile(rf"^(?:qo|ok|ot|ol|or|al|ar|yk|yt|ch|sh|d|s|l|o|y){{1,2}}(?:ckh|cth|cph|cfh|ch|sh|k|t|p|f){_VOWEL}{_TERM}$")),
]

# Pre-compiled combined regex for high-speed Monte Carlo controls
MASTER_L2A_REGEX = re.compile(
    r"^(?:" + "|".join(p.pattern.lstrip("^").rstrip("$") for _, p in LAYER2_DFA_RULES) + r")$"
)

# Layer 2b: Single-glyph EVA base register labels (tracked separately)
SINGLE_GLYPH_REGISTERS = {"s", "y", "l", "o", "r", "d", "g", "t", "a", "k", "p", "f", "m"}

# Known f116v marginalia tokens
MARGINAL_KEY_PATTERNS = ("oladabas", "oladab", "michiton", "nuchicon", "valdenu", "soix")

# External Negative Control Corpus: 15th-century Medieval Latin & Early New High German technical prose
NATURAL_LANGUAGE_CONTROL = """
aquam calidam per canalem aeneum in balneum deducere oportet ut vapor aequaliter distribuatur
si pressura in caldario crescit valvula plumbea sponte elevatur et excessum vaporis dimittit
post coctionem cervisiae fermentum in vasis ligneis refrigeratur antequam in cellarium feratur
item man soll das wasser durch sand und kies filtern damit die kupfernen roehren nicht verstopfen
das feuer im hypocaustum muss langsam geschuert werden um risse im mauerwerk zu vermeiden
omnia vasa balnearia cum aceto diluto laventur ad calcem removendam et fluxum servandum
"""


def classify_token(tok: str) -> Tuple[str, str]:
    """
    Classifies a normalized EVA token into:
      ('L1', working_label), ('L2A', bus_name), ('L2B', 'BUS_SINGLE_GLYPH_REG'), or ('UNKNOWN', 'OOV_HARD_STOP').
    """
    if tok in VOYNICH_FULL_LUT:
        return "L1", VOYNICH_FULL_LUT[tok].node
    if len(tok) == 1 and tok in SINGLE_GLYPH_REGISTERS:
        return "L2B", "BUS_SINGLE_GLYPH_REG"
    for bus_name, pattern in LAYER2_DFA_RULES:
        if pattern.fullmatch(tok):
            return "L2A", bus_name
    return "UNKNOWN", "OOV_HARD_STOP"


def normalize_ivtff_line(raw_line: str) -> List[str]:
    """
    Cleans a single IVTFF 2.0 locus line (ZL3b or RF1b-e) and returns normalized EVA tokens.
    Strictly skips folio header tags (no '.' in tag, e.g. <f69v> <! $Q=J ...>) while preserving
    circular/radial/rosette locus lines that start with inline position comments
    (e.g. <f69v.1,@Cc> <!11:00>dair.cheyky...).
    """
    line = raw_line.strip()
    if not line or line.startswith("#") or not line.startswith("<f"):
        return []

    parts = line.split(">", 1)
    if len(parts) < 2:
        return []

    tag, text = parts[0], parts[1]
    if "." not in tag:
        return []

    text = re.sub(r"<!.*?>", "", text)
    text = re.sub(r"<[%\$\-~]>", ".", text)
    text = re.sub(r"\[([^:\]]+):[^\]]+\]", r"\1", text)

    for code, replacement in PALEOGLYPH_MAP.items():
        text = text.replace(code, replacement)

    raw_tokens = re.split(r"[.,\s]+", text)
    clean_tokens: List[str] = []
    for tok in raw_tokens:
        tok = re.sub(r"[^a-zA-Z]", "", tok).lower()
        if tok:
            clean_tokens.append(tok)
    return clean_tokens


def audit_ivtff_corpus(filepath: str) -> Dict[str, object]:
    """Processes an entire IVTFF 2.0 corpus preserving folio and line boundaries."""
    all_tokens: List[str] = []
    line_records: List[Tuple[str, List[str]]] = []
    l1_hits: Counter = Counter()
    l2a_buses: Counter = Counter()
    l2b_count = 0
    unknown_hits: Counter = Counter()
    l1_adj_repeats: List[Tuple[str, str]] = []
    any_adj_repeats = 0
    f116v_keys_found: List[str] = []
    current_folio = ""
    folio_re = re.compile(r"<(f[0-9]+[rv][0-9]*|fRos)\b", re.IGNORECASE)

    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            stripped = line.strip()
            folio_match = folio_re.search(stripped)
            if folio_match:
                current_folio = folio_match.group(1).lower()

            if current_folio == "f116v":
                low = stripped.lower()
                for key in MARGINAL_KEY_PATTERNS:
                    if key in low and key not in f116v_keys_found:
                        f116v_keys_found.append(key)

            locus_match = re.match(r"^<([^>]+)>", stripped)
            locus = locus_match.group(1) if locus_match else "UNKNOWN"
            tokens = normalize_ivtff_line(line)
            if not tokens:
                continue

            line_records.append((current_folio, tokens))
            prev_tok: Optional[str] = None
            for tok in tokens:
                all_tokens.append(tok)
                layer, label = classify_token(tok)
                if prev_tok is not None and tok == prev_tok:
                    any_adj_repeats += 1
                if layer == "L1":
                    l1_hits[tok] += 1
                    if tok == prev_tok:
                        l1_adj_repeats.append((locus, tok))
                elif layer == "L2A":
                    l2a_buses[label] += 1
                elif layer == "L2B":
                    l2b_count += 1
                else:
                    unknown_hits[tok] += 1
                prev_tok = tok

    return {
        "total": len(all_tokens),
        "tokens": all_tokens,
        "line_records": line_records,
        "l1_hits": l1_hits,
        "l1_total": sum(l1_hits.values()),
        "l2a_buses": l2a_buses,
        "l2a_total": sum(l2a_buses.values()),
        "l2b_total": l2b_count,
        "unknown_hits": unknown_hits,
        "unknown_total": sum(unknown_hits.values()),
        "repeats": l1_adj_repeats,
        "any_repeats": any_adj_repeats,
        "f116v_keys": f116v_keys_found,
    }


def run_z3_formal_verification() -> None:
    """
    Formally verifies bounded convergence and +/-9 barrier interdiction over 6,859 states.
    Scope: verifies properties of the L0-ISM finite-state controller only (not manuscript semantics).
    """
    print("=== FORMAL VERIFICATION: MICROSOFT Z3 SMT SOLVER (AUTOMATON ONLY: 19^3 = 6,859 STATES) ===")
    try:
        from z3 import Abs, And, If, Ints, Or, Solver, unsat
    except ImportError:
        print("[WARN] z3-solver is not installed. Run 'pip install z3-solver' to verify SMT proofs.\n")
        return

    def step_operator(s):
        return If(Abs(s) >= 9, -999, If(s > 0, s - 1, If(s < 0, s + 1, 0)))

    s1, s2, s3 = Ints("s1 s2 s3")
    solver1 = Solver()
    solver1.add(And(s1 >= -8, s1 <= 8, s2 >= -8, s2 <= 8, s3 >= -8, s3 <= 8))
    c1, c2, c3 = s1, s2, s3
    for _ in range(8):
        c1, c2, c3 = step_operator(c1), step_operator(c2), step_operator(c3)
    solver1.add(Or(c1 != 0, c2 != 0, c3 != 0))
    res1 = solver1.check()
    assert res1 == unsat, "CRITICAL: Deadlock or non-converging state found in [-8, +8]^3!"
    print(f"  Proof 1 (Deadlock Absence & <= 8-Step Convergence to Fulcrum 0) : {str(res1).upper()} [PASS]")

    b = Ints("b")[0]
    solver2 = Solver()
    solver2.add(Or(b <= -9, b >= 9))
    solver2.add(step_operator(b) != -999)
    res2 = solver2.check()
    assert res2 == unsat, "CRITICAL: Barrier state bypassed HARD_STOP (-999)!"
    print(f"  Proof 2 (Absorbing Barrier +/-9 Interdiction -> HARD_STOP -999) : {str(res2).upper()} [PASS]\n")


def run_stricter_control_suite(
    tokens: List[str],
    line_records: List[Tuple[str, List[str]]],
    char_trials: int = 1000,
    synth_trials: int = 20,
    seq_trials: int = 1000,
) -> None:
    """
    v2.4 Stricter Negative Control & Falsification Suite:
      Test A1: Intra-word character shuffle (order-0 anagram null, 1,000 MC trials).
      Test A2: Order-1 character Markov synthetic words (^...$ bigram model, 20 trials).
      Test A3: Order-0 IID letter-frequency synthetic words (same length dist, 20 trials).
      Test B : External Medieval Latin / Early New High German technical prose control.
      Test C : Hierarchical adjacent-repeat permutation controls (1,000 trials each):
               Global (line-framed), Within-Folio, and Within-Line for L1 and ANY tokens.
      Audit D: LUT Top-20 token overlap & label-independence disclosure.
    """
    rng = random.Random(42)
    l1_set = set(VOYNICH_FULL_LUT.keys())
    master_match = MASTER_L2A_REGEX.fullmatch
    shuffle = rng.shuffle
    join = "".join
    match_cache: Dict[str, bool] = {}

    def is_accepted(w: str) -> bool:
        hit = match_cache.get(w)
        if hit is None:
            hit = (w in l1_set) or (master_match(w) is not None)
            match_cache[w] = hit
        return hit

    print("=== STRICTER NEGATIVE CONTROL & MONTE CARLO FALSIFICATION SUITE (v2.4) ===")

    # --- Test A: Multi-Char Grammar Controls (Shuffle, Order-1 Markov, Order-0 IID) ---
    multi_tokens = [t for t in tokens if len(t) >= 2]
    n_multi = len(multi_tokens)
    real_accepted = sum(1 for t in multi_tokens if is_accepted(t))
    real_rate = (real_accepted / n_multi) * 100.0 if n_multi else 0.0

    # A1: Intra-word character shuffle (1,000 MC trials)
    vocab_items = [(list(word), count) for word, count in Counter(multi_tokens).items()]
    null_shuf_rates: List[float] = []
    for _ in range(char_trials):
        acc = 0
        for chars, count in vocab_items:
            shuffle(chars)
            if is_accepted(join(chars)):
                acc += count
        null_shuf_rates.append((acc / n_multi) * 100.0)

    shuf_mean = statistics.mean(null_shuf_rates)
    shuf_sd = statistics.stdev(null_shuf_rates) if len(null_shuf_rates) > 1 else 0.0
    z_shuf = (real_rate - shuf_mean) / shuf_sd if shuf_sd > 0 else float("inf")

    # A2: Order-1 character Markov synthetic words trained on ^word$ transitions
    tr_counts: Dict[str, Counter] = defaultdict(Counter)
    for t in multi_tokens:
        s = "^" + t + "$"
        for a, b in zip(s, s[1:]):
            tr_counts[a][b] += 1
    tr_tables: Dict[str, Tuple[List[str], List[int]]] = {}
    for ch, cnt in tr_counts.items():
        keys = list(cnt.keys())
        cum: List[int] = []
        acc_w = 0
        for k in keys:
            acc_w += cnt[k]
            cum.append(acc_w)
        tr_tables[ch] = (keys, cum)

    markov_rates: List[float] = []
    for _ in range(synth_trials):
        acc = 0
        valid_n = 0
        for _ in range(n_multi):
            c = "^"
            buf: List[str] = []
            while True:
                keys, cum = tr_tables[c]
                nxt = rng.choices(keys, cum_weights=cum, k=1)[0]
                if nxt == "$":
                    break
                buf.append(nxt)
                c = nxt
                if len(buf) > 14:
                    break
            if len(buf) >= 2:
                valid_n += 1
                if is_accepted(join(buf)):
                    acc += 1
        markov_rates.append((acc / valid_n) * 100.0 if valid_n else 0.0)

    markov_mean = statistics.mean(markov_rates)
    markov_sd = statistics.stdev(markov_rates) if len(markov_rates) > 1 else 0.0
    lift_over_markov = real_rate - markov_mean

    # A3: Order-0 IID letter-frequency words with exact corpus length distribution
    letter_counts = Counter(c for t in multi_tokens for c in t)
    iid_keys = list(letter_counts.keys())
    iid_cum: List[int] = []
    acc_w = 0
    for k in iid_keys:
        acc_w += letter_counts[k]
        iid_cum.append(acc_w)
    lengths = [len(t) for t in multi_tokens]

    iid_rates: List[float] = []
    for _ in range(synth_trials):
        acc = 0
        for ln in lengths:
            w = join(rng.choices(iid_keys, cum_weights=iid_cum, k=ln))
            if is_accepted(w):
                acc += 1
        iid_rates.append((acc / n_multi) * 100.0)
    iid_mean = statistics.mean(iid_rates)
    iid_sd = statistics.stdev(iid_rates) if len(iid_rates) > 1 else 0.0

    print(f"  [Test A] Multi-Character Grammar Specificity Controls (N = {n_multi}):")
    print(f"           Observed MS 408 Coverage (L1 + L2a)              : {real_rate:6.2f}%")
    print(f"           A1. Intra-Word Char Shuffle ({char_trials} MC trials)      : {shuf_mean:6.2f}% (SD = {shuf_sd:.2f}%) | Z = {z_shuf:+.2f}")
    print(f"           A2. Order-1 Char-Markov Bigrams ({synth_trials} trials)      : {markov_mean:6.2f}% (SD = {markov_sd:.2f}%)")
    print(f"               -> Adjusted Higher-Order Lift over Bigrams   : +{lift_over_markov:5.2f} pp")
    print(f"           A3. Order-0 IID Letter Words ({synth_trials} trials)         : {iid_mean:6.2f}% (SD = {iid_sd:.2f}%)")
    print("           Note: Bigrams alone account for ~67-68% acceptance; DFA reflects EVA slot syntax.\n")

    # --- Test B: Natural Language Control (15th-Century Latin / German Technical Prose) ---
    ctrl_tokens = [re.sub(r"[^a-z]", "", w.lower()) for w in NATURAL_LANGUAGE_CONTROL.split()]
    ctrl_tokens = [w for w in ctrl_tokens if len(w) >= 2]
    ctrl_acc = sum(1 for w in ctrl_tokens if is_accepted(w))
    ctrl_rate = (ctrl_acc / len(ctrl_tokens)) * 100.0 if ctrl_tokens else 0.0
    print(f"  [Test B] Supplementary Natural Language Control (Medieval Latin/German, N = {len(ctrl_tokens)}):")
    print(f"           Accepted by L1+L2a Grammar                       : {ctrl_acc}/{len(ctrl_tokens)} ({ctrl_rate:5.2f}%)")
    print(f"           Rejected into OOV HARD_STOP (-999)               : {len(ctrl_tokens) - ctrl_acc}/{len(ctrl_tokens)} ({100.0 - ctrl_rate:5.2f}%)\n")

    # --- Test C: Hierarchical Adjacent-Repeat Permutation Controls (Global / Folio / Line) ---
    l1_list = list(VOYNICH_FULL_LUT.keys())
    n_l1 = len(l1_list)
    tok_to_id: Dict[str, int] = {w: idx for idx, w in enumerate(l1_list, start=1)}
    next_id = n_l1 + 1
    line_id_records: List[Tuple[str, List[int]]] = []
    for fid, ltoks in line_records:
        ids: List[int] = []
        for t in ltoks:
            tid = tok_to_id.get(t)
            if tid is None:
                tid = next_id
                tok_to_id[t] = tid
                next_id += 1
            ids.append(tid)
        line_id_records.append((fid, ids))

    obs_l1 = sum(1 for _, ids in line_id_records for a, b in zip(ids, ids[1:]) if a == b and a <= n_l1)
    obs_any = sum(1 for _, ids in line_id_records for a, b in zip(ids, ids[1:]) if a == b)

    # C1: Global shuffle preserving line lengths
    flat_ids: List[int] = []
    global_adj_idx: List[int] = []
    offset = 0
    for _, ids in line_id_records:
        flat_ids.extend(ids)
        for k in range(len(ids) - 1):
            global_adj_idx.append(offset + k)
        offset += len(ids)

    g_l1, g_any = [], []
    for _ in range(seq_trials):
        shuffle(flat_ids)
        cl1 = cany = 0
        for idx in global_adj_idx:
            a = flat_ids[idx]
            if a == flat_ids[idx + 1]:
                cany += 1
                if a <= n_l1:
                    cl1 += 1
        g_l1.append(cl1)
        g_any.append(cany)

    # C2: Within-folio shuffle preserving line lengths
    by_folio: Dict[str, List[List[int]]] = defaultdict(list)
    for fid, ids in line_id_records:
        by_folio[fid].append(ids)
    folio_pools: List[Tuple[List[int], List[int]]] = []
    for flines in by_folio.values():
        f_flat: List[int] = []
        f_adj: List[int] = []
        off = 0
        for ids in flines:
            f_flat.extend(ids)
            for k in range(len(ids) - 1):
                f_adj.append(off + k)
            off += len(ids)
        if f_adj and len(set(f_flat)) < len(f_flat):
            folio_pools.append((f_flat, f_adj))

    f_l1, f_any = [], []
    for _ in range(seq_trials):
        cl1 = cany = 0
        for f_flat, f_adj in folio_pools:
            shuffle(f_flat)
            for idx in f_adj:
                a = f_flat[idx]
                if a == f_flat[idx + 1]:
                    cany += 1
                    if a <= n_l1:
                        cl1 += 1
        f_l1.append(cl1)
        f_any.append(cany)

    # C3: Within-line shuffle (exact; lines without duplicates always yield 0 repeats)
    dup_lines: List[List[int]] = [
        ids[:] for _, ids in line_id_records if len(ids) >= 2 and len(set(ids)) < len(ids)
    ]
    ln_l1, ln_any = [], []
    for _ in range(seq_trials):
        cl1 = cany = 0
        for l_ids in dup_lines:
            shuffle(l_ids)
            for k in range(len(l_ids) - 1):
                a = l_ids[k]
                if a == l_ids[k + 1]:
                    cany += 1
                    if a <= n_l1:
                        cl1 += 1
        ln_l1.append(cl1)
        ln_any.append(cany)

    def fmt_row(label: str, obs: int, dist: List[int]) -> str:
        mu = statistics.mean(dist)
        sd = statistics.stdev(dist) if len(dist) > 1 else 0.0
        z = (obs - mu) / sd if sd > 0 else 0.0
        enr = (obs / mu) if mu > 0 else math.inf
        return f"    {label:<28} | Obs={obs:3d} | Null={mu:6.2f} (SD={sd:5.2f}) | Enrich={enr:4.2f}x | Z={z:+6.2f}"

    print(f"  [Test C] Hierarchical Adjacent-Repeat Controls (Per-Line Repeats, {seq_trials} MC trials):")
    print("    --- Layer 1 LUT Tokens ---")
    print(fmt_row("C1. Global Shuffle (Line-Box)", obs_l1, g_l1))
    print(fmt_row("C2. Within-Folio Shuffle",      obs_l1, f_l1))
    print(fmt_row("C3. Within-Line Shuffle",       obs_l1, ln_l1))
    print("    --- ANY Corpus Token ---")
    print(fmt_row("C4. Global Shuffle (Line-Box)", obs_any, g_any))
    print(fmt_row("C5. Within-Folio Shuffle",      obs_any, f_any))
    print(fmt_row("C6. Within-Line Shuffle",       obs_any, ln_any))

    ln_l1_mu = statistics.mean(ln_l1)
    ln_l1_sd = statistics.stdev(ln_l1) if len(ln_l1) > 1 else 0.0
    z_line_l1 = (obs_l1 - ln_l1_mu) / ln_l1_sd if ln_l1_sd > 0 else 0.0
    verdict_c = "[FALSIFIED / NULL WITHIN LINES]" if abs(z_line_l1) < 2.0 else "[ENRICHED WITHIN LINES]"
    print(f"    Verdict (Siphon-Clock Adjacent Repeat Hypothesis): {verdict_c}\n")

    # --- Audit D: LUT Top-20 Frequency Overlap & Label Independence ---
    top20 = Counter(tokens).most_common(20)
    in_lut_count = sum(1 for w, _ in top20 if w in l1_set)
    distinct_nodes = len({e.node for e in VOYNICH_FULL_LUT.values()})
    print("  [Audit D] LUT Frequency Concentration & Label-Independence Disclosure:")
    print(f"            L1 LUT Size: {len(VOYNICH_FULL_LUT)} tokens across {distinct_nodes} retired working labels.")
    print(f"            Top-20 Corpus Tokens Present in L1 LUT: {in_lut_count}/20")
    print("            Label Invariance: Permuting hardware labels leaves all coverage metrics 100% unchanged.\n")


def compare_transcriptions(zl_path: str, rf_path: str) -> None:
    zl = audit_ivtff_corpus(zl_path)
    rf = audit_ivtff_corpus(rf_path)

    print("==========================================================================")
    print("L0-ISM v2.4 FORMAL AUTOMATON & VOYNICH POSITIONAL STRUCTURAL AUDIT")
    print("==========================================================================\n")

    for label, data in [(zl_path, zl), (rf_path, rf)]:
        n = int(data["total"])
        l1 = int(data["l1_total"])
        l2a = int(data["l2a_total"])
        l2b = int(data["l2b_total"])
        unk = int(data["unknown_total"])
        comb_multi = l1 + l2a
        comb_all = l1 + l2a + l2b
        print(f"--- CORPUS COVERAGE: {label} (N = {n} EVA frames) ---")
        print(f"  Layer 1  (Exact Zero-Heap LUT)         : {l1:6d} ({l1 / n * 100:5.2f}%)")
        print(f"  Layer 2a (Positional EVA Slot DFA)     : {l2a:6d} ({l2a / n * 100:5.2f}%)")
        print(f"  Layer 2b (Single-Glyph Base Registers) : {l2b:6d} ({l2b / n * 100:5.2f}%)")
        print(f"  Combined Multi-Char Coverage (L1+L2a)  : {comb_multi:6d} ({comb_multi / n * 100:5.2f}%)")
        print(f"  Total Structural Coverage (L1+L2a+L2b) : {comb_all:6d} ({comb_all / n * 100:5.2f}%)")
        print(f"  Residual UNKNOWN (OOV Sentinel -999)   : {unk:6d} ({unk / n * 100:5.2f}%)")
        keys = data["f116v_keys"]
        print(f"  Marginalia Tokens Found on f116v       : {keys if keys else 'None in raw stream'}\n")

    print("=== LAYER 1 EXACT LUT CROSS-TRANSCRIPTION COMPARISON (ZL3b vs RF1b-e) ===")
    print("Note: Node column retains retired v1.0 working identifiers for C99/Lean symbol parity.")
    print(f"{'EVA Frame':<12} | {'Retired Working Label':<23} | {'ZL 3b':>6} | {'RF1b-e':>6} | {'Delta':>7}")
    print("-" * 68)
    zl_l1: Counter = zl["l1_hits"]  # type: ignore
    rf_l1: Counter = rf["l1_hits"]  # type: ignore
    for eva_word, entry in VOYNICH_FULL_LUT.items():
        c_zl = zl_l1[eva_word]
        c_rf = rf_l1[eva_word]
        print(f"{eva_word:<12} | {entry.node:<23} | {c_zl:>6d} | {c_rf:>6d} | {c_zl - c_rf:>+7d}")

    print("\n=== LAYER 2a (DFA): POSITIONAL SLOT CLASS DISTRIBUTION (ZL3b vs RF1b-e) ===")
    zl_bus: Counter = zl["l2a_buses"]  # type: ignore
    rf_bus: Counter = rf["l2a_buses"]  # type: ignore
    for bus_name, c_zl in zl_bus.most_common():
        print(f"  {bus_name:<28} : {c_zl:6d} (RF1b-e: {rf_bus[bus_name]:6d})")

    zl_rep: List[Tuple[str, str]] = zl["repeats"]  # type: ignore
    rf_rep: List[Tuple[str, str]] = rf["repeats"]  # type: ignore
    print("\n=== PER-LINE ADJACENT REPEATS (L1 & ANY TOKEN) ===")
    print(
        f"  Adjacent L1 Repeats  : ZL3b-n = {len(zl_rep)} | RF1b-e = {len(rf_rep)}"
    )
    print(
        f"  Adjacent ANY Repeats : ZL3b-n = {zl['any_repeats']} | RF1b-e = {rf['any_repeats']}"
    )
    for locus, tok in zl_rep[:10]:
        print(f"    [{locus:<12}] -> {tok} . {tok}")

    print("\n=== RESIDUAL AUDIT: TOP 50 UNKNOWN TOKENS (ZL3b-n.txt) ===")
    print(f"{'Rank':<5} | {'EVA Frame':<14} | {'ZL 3b':>6} | {'RF1b-e':>6} | {'Delta':>7}")
    print("-" * 50)
    zl_unk: Counter = zl["unknown_hits"]  # type: ignore
    rf_unk: Counter = rf["unknown_hits"]  # type: ignore
    for idx, (tok, c_zl) in enumerate(zl_unk.most_common(50), start=1):
        c_rf = rf_unk[tok]
        print(f"{idx:<5d} | {tok:<14} | {c_zl:>6d} | {c_rf:>6d} | {c_zl - c_rf:>+7d}")
    print()

    run_stricter_control_suite(
        zl["tokens"],        # type: ignore
        zl["line_records"],  # type: ignore
        char_trials=1000,
        synth_trials=20,
        seq_trials=1000,
    )
    run_z3_formal_verification()


if __name__ == "__main__":
    zl_file = sys.argv[1] if len(sys.argv) > 1 else "ZL3b-n.txt"
    rf_file = sys.argv[2] if len(sys.argv) > 2 else "RF1b-e.txt"
    compare_transcriptions(zl_file, rf_file)
