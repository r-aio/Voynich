import re
from collections import Counter
from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class LUTEntry:
    node: str
    cmd: str
    delta: int
    valve_pct: float


# Rozszerzona tablica LUT L0-ISM zgodna ze wszystkimi 40 podsystemami z Tabeli 2
VOYNICH_FULL_LUT: Dict[str, LUTEntry] = {
    # 1. Magistrala wodna / główny wymiennik (rdzeń k)
    "qokain":    LUTEntry("HUB_PRIMARY_COOLING",   "SET_WATER_GRADIENT",   1, 11.1),
    "qokaiin":   LUTEntry("HUB_PRIMARY_COOLING",   "SET_WATER_GRADIENT",   2, 22.2),
    "qokaiiin":  LUTEntry("HUB_PRIMARY_COOLING",   "SET_WATER_GRADIENT",   3, 33.3),
    "qokedy":    LUTEntry("HUB_PRIMARY_COOLING",   "REG_FLOW_STEADY",      0, 25.0),
    "qokeedy":   LUTEntry("HUB_PRIMARY_COOLING",   "REG_FLOW_STEADY",      0, 50.0),

    # 2. Magistrala parowo-powietrzna Hypocaustum (przełączenie rdzenia k -> t)
    "qotain":    LUTEntry("VALVE_HYPOCAUST_3WAY",  "SET_STEAM_GRADIENT",   1, 11.1),
    "qotaiin":   LUTEntry("VALVE_HYPOCAUST_3WAY",  "SET_STEAM_GRADIENT",   2, 22.2),
    "qotaiiin":  LUTEntry("VALVE_HYPOCAUST_3WAY",  "SET_STEAM_GRADIENT",   3, 33.3),

    # 3. Kalibracja, rezonans i weryfikacja równowagi SAT
    "qoko":      LUTEntry("HUB_FULCRUM_CALIB",     "CALIBRATE_ZERO",       0,  0.0),
    "oteedy":    LUTEntry("PUMP_THERMAL_RECIRC",   "APPLY_RESO_THERMAL",   0, 50.0),
    "qoteedy":   LUTEntry("PUMP_THERMAL_RECIRC",   "APPLY_RESO_THERMAL",   0, 50.0),
    "ol":        LUTEntry("LOG_MONITOR_NODE",      "CONFIRM_SAT",          0,  0.0),
    "or":        LUTEntry("REFLUX_CONDENSER",      "CONFIRM_SAT",          0, 15.0),
    "ar":        LUTEntry("CONDENSATE_STEAM_TRAP", "DRAIN_CONDENSATE",     0, 10.0),

    # 4. Wskaźniki poziomu (Sight Glass) i odpowietrzniki pływakowe
    "dain":      LUTEntry("LEVEL_SIGHT_GLASS",     "READ_COLUMN_LEVEL",    0,  0.0),
    "daiin":     LUTEntry("LEVEL_SIGHT_GLASS",     "READ_COLUMN_LEVEL",    0,  0.0),
    "al":        LUTEntry("FLOAT_AIR_VENT",        "BLEED_TRAPPED_AIR",    0,  0.0),
    "sol":       LUTEntry("FLOAT_AIR_VENT",        "BLEED_TRAPPED_AIR",    0,  0.0),

    # 5. Piec akumulacyjny, zawory zwrotne i akumulator hydrauliczny
    "daim":      LUTEntry("FURNACE_AIR_DAMPER",    "SET_DAMPER_GRADIENT", -1, 40.0),
    "dair":      LUTEntry("FURNACE_AIR_DAMPER",    "SET_DAMPER_GRADIENT",  1, 60.0),
    "shol":      LUTEntry("CHECK_VALVE_NODE",      "CLOSE_CHECK_VALVE",    0,  0.0),
    "shor":      LUTEntry("CHECK_VALVE_NODE",      "CHECK_NON_RETURN",     0,  0.0),
    "kedy":      LUTEntry("HYDRAULIC_ACCUM",       "APPLY_RESO",           1, 75.0),
    "shedy":     LUTEntry("HYDRAULIC_ACCUM",       "DAMP_WATER_HAMMER",    0, 75.0),

    # 6. Dozowanie chemiczne, płaszcz Bain-Marie i separacja osadu
    "chey":      LUTEntry("CHEM_DOSING_BUFFER",    "DOSE_ANTI_CALC",       0, 10.0),
    "qochey":    LUTEntry("CHEM_DOSING_BUFFER",    "DOSE_ANTI_CALC",       0, 20.0),
    "chol":      LUTEntry("BAIN_MARIE_JACKET",     "HOLD_100C_BATH",       0, 50.0),
    "qochol":    LUTEntry("BAIN_MARIE_JACKET",     "HOLD_100C_BATH",       0, 50.0),
    "qokey":     LUTEntry("PHASE_SEPARATOR",       "FLUSH_SEDIMENT",       0,  0.0),
    "am":        LUTEntry("SYSTEM_FLUSH_OUTLET",   "PURGE_TO_IDLE",        0,  0.0),

    # 7. Zbiornik przelewowy, kompensatory i wymienniki pomocnicze
    "otain":     LUTEntry("OVERFLOW_HEADER_TANK",  "BUFFER_HEAD_PRESSURE", 0, 20.0),
    "otaiin":    LUTEntry("OVERFLOW_HEADER_TANK",  "BUFFER_HEAD_PRESSURE", 0, 40.0),
    "ckain":     LUTEntry("THERMAL_EXP_BELLOWS",   "ABSORB_ELONGATION",    0,  0.0),
    "shain":     LUTEntry("TRICKLE_FILM_COOLER",   "EVAP_COOLING_STEP1",  -1, 30.0),
    "shaiin":    LUTEntry("TRICKLE_FILM_COOLER",   "EVAP_COOLING_STEP2",  -2, 60.0),
    "cthy":      LUTEntry("STATIC_SWIRL_MIXER",    "EQUALIZE_STRATA",      0,  0.0),
    "ckhy":      LUTEntry("STATIC_SWIRL_MIXER",    "EQUALIZE_STRATA",      0,  0.0),

    # 8. Bezpieczeństwo, bariera +/-9 i Air-Gap (f116v)
    "fachys":    LUTEntry("VALVE_SAFETY_RELIEF",   "PREPARE_CRIT_RELIEF",  8, 90.0),
    "qokaiiii":  LUTEntry("EMERGENCY_SHUTDOWN",    "TRIGGER_HARD_STOP", -999,  0.0),
    "oladabas":  LUTEntry("SYSTEM_MASTER_KEY",     "UNLOCK_AIRGAP",        0,100.0),
    "soix":      LUTEntry("SYSTEM_MASTER_KEY",     "UNLOCK_AIRGAP",        0,100.0),
}

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


def normalize_ivtff_line(raw_line: str) -> List[str]:
    """Czyści pojedynczą linię IVTFF (ZL lub RF1b-e) i zwraca listę znormalizowanych ramek EVA."""
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


def audit_ivtff_corpus(filepath: str) -> Tuple[int, Counter, Counter, List[Tuple[str, str]]]:
    """Przetwarza cały plik IVTFF i zlicza wywołania węzłów sprzętowych oraz powtórzenia stacjonarne."""
    total_tokens = 0
    cmd_hits: Counter = Counter()
    node_hits: Counter = Counter()
    steady_state_repeats: List[Tuple[str, str]] = []

    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            locus_match = re.match(r"^<([^>]+)>", line.strip())
            locus = locus_match.group(1) if locus_match else "UNKNOWN"
            tokens = normalize_ivtff_line(line)
            total_tokens += len(tokens)

            prev_tok = None
            for tok in tokens:
                if tok in VOYNICH_FULL_LUT:
                    entry = VOYNICH_FULL_LUT[tok]
                    cmd_hits[tok] += 1
                    node_hits[entry.node] += 1
                    # Detekcja stacjonarnego zrzutu zegara syfonowego dla dowolnej aktywnej ramki LUT
                    if tok == prev_tok:
                        steady_state_repeats.append((locus, tok))
                prev_tok = tok

    return total_tokens, cmd_hits, node_hits, steady_state_repeats


def compare_transcriptions(zl_path: str, rf_path: str) -> None:
    zl_total, zl_cmds, zl_nodes, zl_repeats = audit_ivtff_corpus(zl_path)
    rf_total, rf_cmds, rf_nodes, rf_repeats = audit_ivtff_corpus(rf_path)

    print(f"Całkowita liczba ramek EVA: ZL 3b = {zl_total} | RF1b-e = {rf_total}")
    print("\n=== PORÓWNANIE TRAFIEŃ ROZKAZÓW LUT (ZL 3b vs RF1b-e) ===")
    print(f"{'Ramka EVA':<12} | {'Węzeł sprzętowy L0-ISM':<23} | {'ZL 3b':>6} | {'RF1b-e':>6} | {'Różnica':>7}")
    print("-" * 68)

    for eva_word, entry in VOYNICH_FULL_LUT.items():
        c_zl = zl_cmds[eva_word]
        c_rf = rf_cmds[eva_word]
        diff = c_zl - c_rf
        print(f"{eva_word:<12} | {entry.node:<23} | {c_zl:>6d} | {c_rf:>6d} | {diff:>+7d}")

    print("\n=== STACJONARNE ZRZUTY ZEGARA SYFONOWEGO (POWTÓRZENIA SĄSIEDNIE LUT) ===")
    print(f"Wykryte sekwencje stacjonarne (wszystkie ramki LUT): ZL = {len(zl_repeats)}, RF = {len(rf_repeats)}")
    for locus, tok in zl_repeats[:25]:
        print(f"  [{locus:<12}] -> {tok} . {tok} (STEADY-STATE DUMP @ SAT)")


if __name__ == "__main__":
    compare_transcriptions("ZL3b-n.txt", "RF1b-e.txt")
