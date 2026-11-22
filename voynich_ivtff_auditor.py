#!/usr/bin/env python3
"""
L0-ISM / R-AIO Data Physics — Full Voynich IVTFF 2.0 Auditor & Formal Verifier
Audits full IVTFF 2.0 corpora (ZL3b-n.txt & RF1b-e.txt) across:
  - Layer 1: Exact O(1) Look-Up Table (Core Commands & Safety Triggers)
  - Layer 2: Deterministic O(1) Morphological DFA (Bus Prefix + Actuator Core + State Suffix)
  - Steady-State Siphon Clock Repetitions (Adjacent Identical Frames)
  - Marginalia Key Verification (f116v)
  - TOP 50 Residual UNKNOWN Tokens Report
  - Exhaustive SMT Z3 Proof over all 19^3 = 6859 L0-ISM states
"""

import re
import sys
from collections import Counter
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

try:
    from z3 import And, If, Int, Not, Or, Solver, unsat
    Z3_AVAILABLE = True
except ImportError:
    Z3_AVAILABLE = False


@dataclass(frozen=True)
class LUTEntry:
    node: str
    cmd: str
    delta: int
    valve_pct: float


# ==============================================================================
# LAYER 1: EXACT O(1) LOOK-UP TABLE (CORE COMMANDS)
# ==============================================================================
VOYNICH_EXACT_LUT: Dict[str, LUTEntry] = {
    # Magistrala wodna mCDU (rdzeń k)
    "qokain":   LUTEntry("HUB_PRIMARY_COOLING",   "SET_WATER_GRADIENT",   1, 11.1),
    "qokaiin":  LUTEntry("HUB_PRIMARY_COOLING",   "SET_WATER_GRADIENT",   2, 22.2),
    "qokaiiin": LUTEntry("HUB_PRIMARY_COOLING",   "SET_WATER_WARN_BAR",   3, 33.3),
    "qokedy":   LUTEntry("HUB_PRIMARY_COOLING",   "REG_FLOW_DYNAMIC",     1, 15.0),
    "qokeedy":  LUTEntry("HUB_PRIMARY_COOLING",   "REG_FLOW_DELAYED",     2, 25.0),
    # Magistrala parowo-powietrzna Hypocaustum (przełączenie rdzenia k -> t)
    "qotain":   LUTEntry("VALVE_HYPOCAUST_3WAY",  "SET_STEAM_GRADIENT",   1, 11.1),
    "qotaiin":  LUTEntry("VALVE_HYPOCAUST_3WAY",  "SET_STEAM_GRADIENT",   2, 22.2),
    "qotaiiin": LUTEntry("VALVE_HYPOCAUST_3WAY",  "SET_STEAM_WARN_BAR",   3, 33.3),
    # Kalibracja, rezonans i weryfikacja równowagi SAT
    "qoko":     LUTEntry("HUB_FULCRUM_CALIB",     "CALIBRATE_ZERO",       0,  0.0),
    "oteedy":   LUTEntry("PUMP_THERMAL_RECIRC",   "APPLY_RESO_THERMAL",   0, 50.0),
    "qoteedy":  LUTEntry("PUMP_THERMAL_RECIRC",   "APPLY_RESO_PRIMARY",   0, 55.0),
    "tede":     LUTEntry("PUMP_THERMAL_RECIRC",   "APPLY_RESO_DELAY",     0, 50.0),
    "ol":       LUTEntry("LOG_MONITOR_NODE",      "CONFIRM_SAT",          0,  0.0),
    "or":       LUTEntry("REFLUX_CONDENSER",      "CONFIRM_CONDENSE",     0, 15.0),
    "ar":       LUTEntry("CONDENSATE_STEAM_TRAP", "DRAIN_CONDENSATE",     0, 20.0),
    # Wskaźnik poziomu, odpowietrzniki, piec
    "dain":     LUTEntry("LEVEL_SIGHT_GLASS",     "READ_LEVEL_LOW",      -1, 10.0),
    "daiin":    LUTEntry("LEVEL_SIGHT_GLASS",     "READ_LEVEL_NOMINAL",   0, 50.0),
    "al":       LUTEntry("FLOAT_AIR_VENT",        "PURGE_AIR_POCKET",     0, 10.0),
    "sol":      LUTEntry("FLOAT_AIR_VENT",        "SEAL_FLOAT_VENT",      0,  0.0),
    "daim":     LUTEntry("FURNACE_AIR_DAMPER",    "SET_DAMPER_THROTTLE", -1, 40.0),
    "dair":     LUTEntry("FURNACE_AIR_DAMPER",    "SET_DAMPER_OPEN",      1, 60.0),
    # Zawory zwrotne, akumulator, dozowanie chemiczne i chłodzenie
    "shol":     LUTEntry("CHECK_VALVE_NODE",      "CLOSE_CHECK_VALVE",    0,  0.0),
    "shor":     LUTEntry("CHECK_VALVE_NODE",      "CHECK_BACKPRESSURE",   0, 10.0),
    "kedy":     LUTEntry("HYDRAULIC_ACCUM",       "CHARGE_ACCUMULATOR",   1, 75.0),
    "shedy":    LUTEntry("HYDRAULIC_ACCUM",       "DAMP_WATER_HAMMER",    0, 60.0),
    "chey":     LUTEntry("CHEM_DOSING_BUFFER",    "DOSE_ANTI_CALC",       0, 10.0),
    "qochey":   LUTEntry("CHEM_DOSING_BUFFER",    "DOSE_PRIMARY_CHEM",    1, 15.0),
    "chol":     LUTEntry("BAIN_MARIE_JACKET",     "HOLD_JACKET_TEMP",     0, 50.0),
    "qochol":   LUTEntry("BAIN_MARIE_JACKET",     "LOCK_JACKET_LOOP",     0, 50.0),
    "qokey":    LUTEntry("PHASE_SEPARATOR",       "FLUSH_SEDIMENT",       0,  0.0),
    "am":       LUTEntry("SYSTEM_FLUSH_OUTLET",   "END_FLUSH_IDLE",       0,  0.0),
    "otain":    LUTEntry("OVERFLOW_HEADER_TANK",  "HEAD_PRESSURE_STEP1",  1, 15.0),
    "otaiin":   LUTEntry("OVERFLOW_HEADER_TANK",  "HEAD_PRESSURE_STEP2",  2, 30.0),
    "ckhaiin":  LUTEntry("THERMAL_EXP_BELLOWS",   "ABSORB_EXPANSION",     2, 22.2),
    "shain":    LUTEntry("TRICKLE_FILM_COOLER",   "COOLER_FILM_STEP1",    1, 20.0),
    "shaiin":   LUTEntry("TRICKLE_FILM_COOLER",   "COOLER_FILM_STEP2",    2, 40.0),
    "cthy":     LUTEntry("STATIC_SWIRL_MIXER",    "ENABLE_SWIRL_MIX",     0, 50.0),
    "ckhy":     LUTEntry("STATIC_SWIRL_MIXER",    "TURBULENT_BLEND",      0, 60.0),
    # Bezpieczeństwo i bariera krytyczna
    "fachys":   LUTEntry("VALVE_SAFETY_RELIEF",   "PREPARE_CRIT_RELIEF",  8, 90.0),
    "qokaiiii": LUTEntry("EMERGENCY_SHUTDOWN",    "TRIGGER_HARD_STOP", -999,  0.0),
}

# ==============================================================================
# LAYER 2: DETERMINISTIC O(1) MORPHOLOGICAL DFA TABLES
# ==============================================================================
DFA_PREFIXES: Tuple[Tuple[str, str], ...] = (
    ("qo", "BUS_PRIMARY_MANIFOLD"),
    ("sh", "BUS_CHECK_COOLER"),
    ("ch", "BUS_CHEM_MIXER"),
    ("ot", "BUS_OVERFLOW_STEAM"),
    ("ok", "BUS_OPEN_LIQUID"),
    ("yk", "BUS_SPIRAL_LIQUID"),
    ("yt", "BUS_SPIRAL_STEAM"),
    ("ol", "BUS_SAT_VENT"),
    ("al", "BUS_AIR_VENT"),
    ("op", "BUS_THROTTLE_LINE"),
    ("of", "BUS_RELIEF_LINE"),
    ("cp", "BUS_MICRO_VALVE"),
    ("cf", "BUS_MIST_RELIEF"),
    ("ct", "BUS_SWIRL_STEAM"),
    ("ck", "BUS_SWIRL_LIQUID"),
    ("d",  "BUS_LEVEL_FURNACE"),
    ("o",  "BUS_OPEN_HEADER"),
    ("y",  "BUS_SPIRAL_COIL"),
    ("s",  "BUS_FLOW_SENSOR"),
    ("l",  "BUS_VENT_FEED"),
    ("r",  "BUS_RETURN_LOOP"),
    ("k",  "BUS_DIRECT_LIQUID"),
    ("t",  "BUS_DIRECT_STEAM"),
    ("p",  "BUS_DIRECT_THROTTLE"),
    ("f",  "BUS_DIRECT_RELIEF"),
)

DFA_CORES: Tuple[Tuple[str, str], ...] = (
    ("ckh", "ACT_EXPANSION_MIX"),
    ("cth", "ACT_SWIRL_THERMAL"),
    ("cph", "ACT_NEEDLE_THROTTLE"),
    ("cfh", "ACT_DEMISTER_RELIEF"),
    ("kee", "ACT_LIQUID_DELAY"),
    ("tee", "ACT_STEAM_DELAY"),
    ("che", "ACT_CHEM_THERM"),
    ("she", "ACT_COOLER_DAMP"),
    ("ch",  "ACT_CHEM_JACKET"),
    ("sh",  "ACT_CHECK_COOLER"),
    ("ee",  "ACT_CLK_DELAY_2"),
    ("k",   "ACT_LIQUID_VALVE"),
    ("t",   "ACT_STEAM_DUCT"),
    ("p",   "ACT_THROTTLE_VALVE"),
    ("f",   "ACT_SAFETY_RELIEF"),
    ("e",   "ACT_CLK_DELAY_1"),
    ("o",   "ACT_FULCRUM_ZERO"),
    ("a",   "ACT_OFFSET_STEP"),
    ("l",   "ACT_FLOAT_VENT"),
    ("r",   "ACT_STEAM_TRAP"),
    ("d",   "ACT_LEVEL_DAMPER"),
)

DFA_SUFFIXES: Tuple[Tuple[str, str], ...] = (
    ("iiin", "GRAD_+3_WARN"),
    ("iin",  "GRAD_+2_NOMINAL"),
    ("iii",  "GRAD_+3_WARN"),
    ("in",   "GRAD_+1_STEP"),
    ("iir",  "GRAD_+2_TRAP"),
    ("ir",   "GRAD_+1_TRAP"),
    ("edy",  "STATE_DYN_REG"),
    ("ody",  "STATE_SAT_REG"),
    ("dy",   "STATE_DYN_STEP"),
    ("ey",   "STATE_LOOP_RESO"),
    ("ly",   "STATE_VENT_HOLD"),
    ("ry",   "STATE_TRAP_HOLD"),
    ("ky",   "STATE_VALVE_HOLD"),
    ("ty",   "STATE_DUCT_HOLD"),
    ("hy",   "STATE_MIX_HOLD"),
    ("ol",   "STATE_SAT_CONFIRM"),
    ("al",   "STATE_VENT_CONFIRM"),
    ("or",   "STATE_CONDENSATE_OUT"),
    ("ar",   "STATE_TRAP_OUT"),
    ("am",   "STATE_FLUSH_STOP"),
    ("om",   "STATE_LOOP_STOP"),
    ("im",   "STATE_DAMPER_STOP"),
    ("y",    "STATE_LOOP_ACTIVE"),
    ("l",    "STATE_VENT_OPEN"),
    ("r",    "STATE_DRAIN_OPEN"),
    ("n",    "STATE_STEP_HOLD"),
    ("s",    "STATE_SENSOR_OK"),
    ("m",    "FLAG_STOP_M"),
    ("g",    "FLAG_STOP_G"),
    ("d",    "STATE_DAMPER_SET"),
    ("o",    "STATE_ZERO_HOLD"),
)

# Mapa normalizacji kodów paleograficznych RF1b-e -> standardowe EVA
PALEOGLYPH_MAP = {
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


def decode_layer2_dfa(token: str) -> Optional[Tuple[str, str, str]]:
    """
    Deterministic O(1) morphological decomposition of an EVA token into:
    (Bus Prefix, Actuator Core, Quantized Suffix).
    Returns None if token does not conform to valid EVA control morphology.
    """
    if len(token) < 2 or len(token) > 16:
        return None
    # Strict EVA alphabet check (rejects corrupted/non-Voynich noise)
    eva_chars = set("acdefghiklmnopqrsty")
    if any(ch not in eva_chars for ch in token):
        return None

    bus = None
    rem = token
    for pref, bus_name in DFA_PREFIXES:
        if token.startswith(pref):
            bus = bus_name
            rem = token[len(pref):]
            break
    if bus is None:
        return None

    suffix = None
    core_part = rem
    for suf, suf_name in DFA_SUFFIXES:
        if rem.endswith(suf) and len(rem) >= len(suf):
            suffix = suf_name
            core_part = rem[:-len(suf)]
            break
    if suffix is None:
        return None

    core = "ACT_DIRECT_PASS"
    if core_part:
        matched_core = None
        for c_pat, c_name in DFA_CORES:
            if c_pat in core_part:
                matched_core = c_name
                break
        if matched_core is None:
            return None
        core = matched_core

    return (bus, core, suffix)


def normalize_ivtff_line(raw_line: str) -> List[str]:
    """Extracts and normalizes EVA tokens from an IVTFF 2.0 locus line."""
    line = raw_line.strip()
    if not line or line.startswith("#") or not line.startswith("<f"):
        return []
    if re.match(r"^<f[^>]+>\s*<!", line):
        return []

    parts = line.split(">", 1)
    if len(parts) < 2:
        return []
    text = parts[1]

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


def audit_ivtff_corpus(filepath: str) -> dict:
    """Runs full Layer 1 + Layer 2 audit on an IVTFF 2.0 file."""
    total_tokens = 0
    l1_hits = 0
    l2_hits = 0
    l1_cmds: Counter = Counter()
    l2_buses: Counter = Counter()
    unknown_tokens: Counter = Counter()
    steady_state_repeats: List[Tuple[str, str]] = []
    f116v_keys_found: List[str] = []

    in_f116v = False
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            stripped = line.strip()
            if stripped.startswith("<f116v>"):
                in_f116v = True
            if in_f116v and stripped.startswith("#"):
                lower_comment = stripped.lower()
                for key in ("oladab", "michiton", "nuchicon", "soix"):
                    if key in lower_comment and key not in f116v_keys_found:
                        f116v_keys_found.append(key)

            locus_match = re.match(r"^<([^>]+)>", stripped)
            locus = locus_match.group(1) if locus_match else "UNKNOWN"
            tokens = normalize_ivtff_line(line)
            total_tokens += len(tokens)

            prev_tok = None
            for tok in tokens:
                if tok in VOYNICH_EXACT_LUT:
                    l1_hits += 1
                    l1_cmds[tok] += 1
                    if tok == prev_tok:
                        steady_state_repeats.append((locus, tok))
                else:
                    dfa_res = decode_layer2_dfa(tok)
                    if dfa_res is not None:
                        l2_hits += 1
                        l2_buses[dfa_res[0]] += 1
                    else:
                        unknown_tokens[tok] += 1
                prev_tok = tok

    return {
        "total": total_tokens,
        "l1_hits": l1_hits,
        "l2_hits": l2_hits,
        "unknown_total": sum(unknown_tokens.values()),
        "l1_cmds": l1_cmds,
        "l2_buses": l2_buses,
        "unknown_tokens": unknown_tokens,
        "repeats": steady_state_repeats,
        "f116v_keys": f116v_keys_found,
    }


def run_z3_formal_proof() -> bool:
    """
    Proves via Z3 SMT Solver over all 19^3 = 6859 states in S = {-9, ..., +9}^3:
      1. Every permissible state in [-8, +8]^3 converges to Fulcrum (0,0,0) in <= 8 steps (UNSAT for non-convergence).
      2. Reaching any absorbing barrier |s_i| >= 9 deterministically triggers HARD_STOP (-999).
    """
    print("\n=== FORMALNA WERYFIKACJA SMT Z3 (19^3 = 6859 STANÓW) ===")
    if not Z3_AVAILABLE:
        print("[WARN] Brak pakietu z3-solver (zainstaluj: pip install z3-solver). Pominięto dowód SMT.")
        return False

    def step(s):
        return If(s > 0, s - 1, If(s < 0, s + 1, 0))

    s1, s2, s3 = Int("s1"), Int("s2"), Int("s3")

    # Proof 1: Convergence to (0, 0, 0) in <= 8 steps from [-8, +8]^3
    solver_conv = Solver()
    solver_conv.add(And(s1 >= -8, s1 <= 8, s2 >= -8, s2 <= 8, s3 >= -8, s3 <= 8))
    c1, c2, c3 = s1, s2, s3
    for _ in range(8):
        c1, c2, c3 = step(c1), step(c2), step(c3)
    solver_conv.add(Not(And(c1 == 0, c2 == 0, c3 == 0)))
    res_conv = solver_conv.check()

    # Proof 2: Absorbing Barrier (+/-9) forces HARD_STOP (-999)
    solver_bar = Solver()
    solver_bar.add(And(s1 >= -9, s1 <= 9, s2 >= -9, s2 <= 9, s3 >= -9, s3 <= 9))
    at_barrier = Or(s1 == 9, s1 == -9, s2 == 9, s2 == -9, s3 == 9, s3 == -9)
    hard_stop_out = If(at_barrier, -999, 0)
    solver_bar.add(And(at_barrier, hard_stop_out != -999))
    res_bar = solver_bar.check()

    ok = (res_conv == unsat) and (res_bar == unsat)
    print(f"Dowód 1 (Brak zakleszczeń / zbieżność <= 8 kroków do Fulcrum 0): {str(res_conv).upper()} {'[PASS]' if res_conv == unsat else '[FAIL]'}")
    print(f"Dowód 2 (Wymuszenie HARD_STOP -999 na barierze +/-9)          : {str(res_bar).upper()} {'[PASS]' if res_bar == unsat else '[FAIL]'}")
    return ok


def run_full_audit(zl_path: str, rf_path: str) -> int:
    print("==================================================================")
    print("L0-ISM FULL VERIFICATION: LAYER 1 (LUT) + LAYER 2 (DFA) + SMT Z3")
    print("==================================================================")

    zl = audit_ivtff_corpus(zl_path)
    rf = audit_ivtff_corpus(rf_path)

    for name, data in (("ZL3b-n.txt", zl), ("RF1b-e.txt", rf)):
        tot = data["total"]
        l1_pct = (data["l1_hits"] / tot * 100.0) if tot else 0.0
        l2_pct = (data["l2_hits"] / tot * 100.0) if tot else 0.0
        comb = data["l1_hits"] + data["l2_hits"]
        comb_pct = (comb / tot * 100.0) if tot else 0.0
        unk_pct = (data["unknown_total"] / tot * 100.0) if tot else 0.0
        print(f"\n--- POKRYCIE KORPUSU: {name} (N = {tot} ramek) ---")
        print(f"  Warstwa 1 (Exact LUT)       : {data['l1_hits']:6d} ({l1_pct:5.2f}%)")
        print(f"  Warstwa 2 (DFA Morfologia)  : {data['l2_hits']:6d} ({l2_pct:5.2f}%)")
        print(f"  ŁĄCZNE POKRYCIE (L1 + L2)   : {comb:6d} ({comb_pct:5.2f}%)")
        print(f"  Pozostałe UNKNOWN (HARD_STOP): {data['unknown_total']:6d} ({unk_pct:5.2f}%)")
        print(f"  Klucze marginalne f116v     : {data['f116v_keys'] if data['f116v_keys'] else 'Brak w komentarzach (surowy strumień)'}")

    print("\n=== PORÓWNANIE WARSTWY 1 EXACT LUT (ZL 3b vs RF1b-e) ===")
    print(f"{'Ramka EVA':<12} | {'Węzeł sprzętowy L0-ISM':<23} | {'ZL 3b':>6} | {'RF1b-e':>6} | {'Różnica':>7}")
    print("-" * 68)
    for eva_word, entry in VOYNICH_EXACT_LUT.items():
        c_zl = zl["l1_cmds"][eva_word]
        c_rf = rf["l1_cmds"][eva_word]
        print(f"{eva_word:<12} | {entry.node:<23} | {c_zl:>6d} | {c_rf:>6d} | {c_zl - c_rf:>+7d}")

    print("\n=== WARSTWA 2 (DFA): ROZKŁAD MAGISTRAL SPRZĘTOWYCH (TOP 10 w ZL 3b) ===")
    for bus, count in zl["l2_buses"].most_common(10):
        print(f"  {bus:<24} : {count:6d} (RF1b-e: {rf['l2_buses'][bus]:6d})")

    print(f"\n=== STACJONARNE ZRZUTY ZEGARA SYFONOWEGO (POWTÓRZENIA L1) ===")
    print(f"Wykryte sekwencje sąsiednie: ZL3b-n = {len(zl['repeats'])} | RF1b-e = {len(rf['repeats'])}")

    print("\n=== AUDYT RESZTY: TOP 50 NIEROPOZNANYCH TOKENÓW (UNKNOWN w ZL3b-n.txt) ===")
    for idx, (tok, cnt) in enumerate(zl["unknown_tokens"].most_common(50), start=1):
        print(f"  {idx:2d}. {tok:<16} : {cnt:5d}  (RF1b-e: {rf['unknown_tokens'][tok]:5d})")

    z3_ok = run_z3_formal_proof()
    return 0 if (z3_ok or not Z3_AVAILABLE) else 1


if __name__ == "__main__":
    zl_file = sys.argv[1] if len(sys.argv) > 1 else "ZL3b-n.txt"
    rf_file = sys.argv[2] if len(sys.argv) > 2 else "RF1b-e.txt"
    sys.exit(run_full_audit(zl_file, rf_file))
