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


# Kompletna tablica LUT L0-ISM (zgodna z MW2.pdf / r-aio-data-physics-voynich-l0-ism-monograph.pdf)
VOYNICH_FULL_LUT: Dict[str, LUTEntry] = {
    # Magistrala wodna mCDU (rdzeń k)
    "qokain":   LUTEntry("HUB_mCDU_PRIMARY",      "SET_WATER_GRADIENT",  1, 11.1),
    "qokaiin":  LUTEntry("HUB_mCDU_PRIMARY",      "SET_WATER_GRADIENT",  2, 22.2),
    "qokaiiin": LUTEntry("HUB_mCDU_PRIMARY",      "SET_WATER_GRADIENT",  3, 33.3),
    # Magistrala parowo-powietrzna Hypocaustum (przełączenie rdzenia k -> t)
    "qotain":   LUTEntry("VALVE_HYPOCAUST_3WAY",  "SET_STEAM_GRADIENT",  1, 11.1),
    "qotaiin":  LUTEntry("VALVE_HYPOCAUST_3WAY",  "SET_STEAM_GRADIENT",  2, 22.2),
    "qotaiiin": LUTEntry("VALVE_HYPOCAUST_3WAY",  "SET_STEAM_GRADIENT",  3, 33.3),
    # Kalibracja, rezonans i weryfikacja równowagi SAT
    "qoko":     LUTEntry("HUB_FULCRUM_CALIB",     "CALIBRATE_ZERO",      0,  0.0),
    "tede":     LUTEntry("PUMP_THERMAL_RECIRC",   "APPLY_RESO_THERMAL",  0, 50.0),
    "ol":       LUTEntry("LOG_MONITOR_NODE",      "CONFIRM_SAT",         0,  0.0),
    "or":       LUTEntry("REFLUX_CONDENSER",      "CONFIRM_SAT",         0, 15.0),
    # Piec akumulacyjny, zawory zwrotne i akumulator hydrauliczny
    "daim":     LUTEntry("FURNACE_AIR_DAMPER",    "SET_DAMPER_GRADIENT",-1, 40.0),
    "dair":     LUTEntry("FURNACE_AIR_DAMPER",    "SET_DAMPER_GRADIENT", 1, 60.0),
    "shol":     LUTEntry("CHECK_VALVE_NODE",      "CLOSE_CHECK_VALVE",   0,  0.0),
    "kedy":     LUTEntry("HYDRAULIC_ACCUM",       "APPLY_RESO",          1, 75.0),
    # Dozowanie chemiczne i separacja osadu
    "chey":     LUTEntry("CHEM_DOSING_BUFFER",    "DOSE_ANTI_CALC",      0, 10.0),
    "qokey":    LUTEntry("PHASE_SEPARATOR",       "FLUSH_SEDIMENT",      0,  0.0),
    # Bezpieczeństwo, bariera +/-9 i Air-Gap (f116v)
    "fachys":   LUTEntry("VALVE_SAFETY_RELIEF",   "PREPARE_CRIT_RELIEF", 8, 90.0),
    "qokaiiii": LUTEntry("EMERGENCY_SHUTDOWN",    "TRIGGER_HARD_STOP",-999,  0.0),
    "soix":     LUTEntry("SYSTEM_MASTER_KEY",     "UNLOCK_AIRGAP",       0,100.0),
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
    # Pominięcie nagłówków kart typu <f1r> <! ...>
    if re.match(r"^<f[^>]+>\s*<!", line):
        return []

    # Wyodrębnienie treści po znaczniku locus <f...>
    parts = line.split(">", 1)
    if len(parts) < 2:
        return []
    text = parts[1]

    # Usunięcie komentarzy inline <!...> oraz znaczników układu <%>, <$>, <->, <~>
    text = re.sub(r"<!.*?>", "", text)
    text = re.sub(r"<[%\$\-~]>", ".", text)

    # Rozstrzygnięcie wariantów niepewnych [a:b] -> pierwszy wariant 'a'
    text = re.sub(r"\[([^:\]]+):[^\]]+\]", r"\1", text)

    # Normalizacja kodów numerycznych i ligatur z RF1b-e
    for code, replacement in PALEOGLYPH_MAP.items():
        text = text.replace(code, replacement)

    # Podział po kropkach i przecinkach na dyskretne ramki telemetryczne
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
                    # Detekcja stacjonarnego zrzutu zegara syfonowego (identyczne ramki obok siebie)
                    if tok == prev_tok and tok in {"qokain", "qokaiin", "qotain", "qotaiin"}:
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

    print("\n=== STACJONARNE ZRZUTY ZEGARA SYFONOWEGO (POWTÓRZENIA SĄSIEDNIE) ===")
    print(f"Wykryte sekwencje stacjonarne (qokain/qokaiin/qotain/qotaiin): ZL = {len(zl_repeats)}, RF = {len(rf_repeats)}")
    for locus, tok in zl_repeats[:15]:
        print(f"  [{locus:<12}] -> {tok} . {tok} (STEADY-STATE DUMP @ SAT)")


if __name__ == "__main__":
    # Uruchomienie dla lokalnych plików transkrypcji IVTFF 2.0:
    # compare_transcriptions("ZL3b-n.txt", "RF1b-e.txt")
    pass
