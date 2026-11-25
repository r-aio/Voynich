#!/usr/bin/env python3
"""
Voynich Manuscript (MS 408) — Tyrol-Bavaria Balneological/Herbal Treatises Audit (v3.4)
Konrad Kyeser (Bellifortis, BSB Clm 30150) & Alpine Kunstbuch / Ricettari (Brixen/Innsbruck, 1405-1445)
Zero external dependencies (Python 3.11 stdlib only). No L0-ISM / No semantic labels.

Tests the top-scoring archival track from v3.3 (TYROL-KUNSTBUCH = 5/6 & BSB-CLM-30150 = 4/6):
  1. Kyeser-Bellifortis (1405 / c. 1430, BSB Clm 30150):
     Bilingual Latin + Early New High German bath/furnace/distillation prose encoded with
     Kyeser's 1:1 cipher alphabet (mapped to canonical EVA glyphs).
  2. Tyrol-Kunstbuch Guild Abbreviation / Tachygraphy (c. 1410-1445, Brixen / Innsbruck):
     Bilingual Latin + Early New High German herbal/balneological ricettari compressed via
     workshop abbreviation rules (stem truncation + looped gallows prefixes qo-/ch-/cth- +
     standardized formulaic endings -aiin/-edy/-ol/-or, ~0.75x compression).
  3. Tyrol-Kunstbuch + Scribal Workshop Habits (Paragraph Stem Reuse + Sandhi + 3.5% 2D Copy):
     Adds documented scribal layout habits (within-line boundary assimilation with line-end
     reset, paragraph stem-mutation drift, and 3.5% vertical column copying).

Evaluated head-to-head against REAL (ZL3b-n) and out-of-sample LOQO Cur-4 + 2D(3.5%)
across all 12 empirical metrics:
  h2(s), h2(B), TTR, MI1, Reset%, len_r, VertEx, W5Ex%, TwinW5%, TwinLift, Label MedGlyphs, Ex+Ed1%.
"""

from __future__ import annotations

import math
import random
import re
import statistics
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass
class LineEntry:
    folio: str
    quire: str
    section: str
    currier: str
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
                folio_meta[fid] = {
                    "quire": q_m.group(1) if q_m else "?",
                    "section": i_m.group(1) if i_m else "?",
                    "currier": l_m.group(1) if l_m else "?",
                }
                continue
            lm = LOCUS_RE.match(line)
            if not lm:
                continue
            fid = lm.group(1).lower()
            body = lm.group(3)
            fmeta = folio_meta.get(fid, {})
            quire = fmeta.get("quire", "?")
            section = fmeta.get("section", "?")
            currier = fmeta.get("currier", "?")
            q_ov = re.search(r"\$Q=([A-Z0-9]+)", body)
            if q_ov:
                quire = q_ov.group(1)
            i_ov = re.search(r"\$I=([A-Z])", body)
            if i_ov:
                section = i_ov.group(1)
            l_ov = re.search(r"\$L=([A-Z])", body)
            if l_ov:
                currier = l_ov.group(1)
            toks = tokenize_ivtff_body(body)
            if toks:
                entries.append(LineEntry(fid, quire, section, currier, toks))
    return entries


def is_edit_le_1(a: str, b: str) -> bool:
    if a == b:
        return True
    la, lb = len(a), len(b)
    if la == lb:
        diffs = 0
        for ca, cb in zip(a, b):
            if ca != cb:
                diffs += 1
                if diffs > 1:
                    return False
        return True
    if la - lb == 1:
        i = 0
        while i < lb and a[i] == b[i]:
            i += 1
        return a[i + 1 :] == b[i:]
    if lb - la == 1:
        i = 0
        while i < la and a[i] == b[i]:
            i += 1
        return a[i:] == b[i + 1 :]
    return False


def is_edit_eq_1(a: str, b: str) -> bool:
    return a != b and is_edit_le_1(a, b)


def h2_stream(lines: List[List[str]]) -> float:
    c2: Counter = Counter()
    c1: Counter = Counter()
    n2 = 0
    for toks in lines:
        if not toks:
            continue
        s = " ".join(toks)
        for i in range(len(s) - 1):
            c1[s[i]] += 1
            c2[s[i : i + 2]] += 1
            n2 += 1
    if n2 == 0:
        return 0.0
    inv = 1.0 / n2
    h_joint = -sum((v * inv) * math.log2(v * inv) for v in c2.values())
    h_pre = -sum((v * inv) * math.log2(v * inv) for v in c1.values())
    return max(0.0, h_joint - h_pre)


def mutual_info_1char(lines: List[List[str]]) -> float:
    cx: Counter = Counter()
    cy: Counter = Counter()
    cxy: Counter = Counter()
    n = 0
    for toks in lines:
        for i in range(len(toks) - 1):
            a = toks[i][-1]
            b = toks[i + 1][0]
            cx[a] += 1
            cy[b] += 1
            cxy[(a, b)] += 1
            n += 1
    if n == 0:
        return 0.0
    inv = 1.0 / n
    return max(
        0.0,
        sum((v * inv) * math.log2((v * inv) / ((cx[a] * inv) * (cy[b] * inv))) for (a, b), v in cxy.items()),
    )


def cross_line_mi_1char(folio_lines: Dict[str, List[List[str]]]) -> float:
    cx: Counter = Counter()
    cy: Counter = Counter()
    cxy: Counter = Counter()
    n = 0
    for lines in folio_lines.values():
        for i in range(len(lines) - 1):
            if lines[i] and lines[i + 1]:
                a = lines[i][-1][-1]
                b = lines[i + 1][0][0]
                cx[a] += 1
                cy[b] += 1
                cxy[(a, b)] += 1
                n += 1
    if n == 0:
        return 0.0
    inv = 1.0 / n
    return max(
        0.0,
        sum((v * inv) * math.log2((v * inv) / ((cx[a] * inv) * (cy[b] * inv))) for (a, b), v in cxy.items()),
    )


def pearson_len_r(lines: List[List[str]]) -> float:
    sx = sy = sxx = syy = sxy = 0.0
    n = 0
    for toks in lines:
        for i in range(len(toks) - 1):
            x = len(toks[i])
            y = len(toks[i + 1])
            sx += x
            sy += y
            sxx += x * x
            syy += y * y
            sxy += x * y
            n += 1
    if n < 2:
        return 0.0
    mx, my = sx / n, sy / n
    num = sxy - n * mx * my
    den = math.sqrt(max(0.0, (sxx - n * mx * mx) * (syy - n * my * my)))
    return (num / den) if den > 1e-12 else 0.0


def vertical_interior_exact(folio_lines: Dict[str, List[List[str]]]) -> float:
    ex = tot = 0
    for lines in folio_lines.values():
        valid = [ln for ln in lines if len(ln) >= 3]
        for li in range(1, len(valid)):
            prev, curr = valid[li - 1], valid[li]
            lp, lc = len(prev), len(curr)
            scale = (lp - 1) / (lc - 1)
            for i in range(1, lc - 1):
                tok = curr[i]
                proj = round(i * scale)
                lo = max(0, proj - 1)
                hi = min(lp, proj + 2)
                tot += 1
                if tok in prev[lo:hi]:
                    ex += 1
    return (ex / tot * 100.0) if tot else 0.0


def window5_stats(folio_lines: Dict[str, List[List[str]]]) -> Tuple[float, float]:
    ex = ed1_only = tot = 0
    for lines in folio_lines.values():
        seq = [t for ln in lines for t in ln]
        n = len(seq)
        for i in range(n):
            tok = seq[i]
            lo = max(0, i - 5)
            hi = min(n, i + 6)
            f_ex = False
            f_ed1 = False
            for j in range(lo, hi):
                if j == i:
                    continue
                other = seq[j]
                if other == tok:
                    f_ex = True
                    break
                if not f_ed1 and is_edit_eq_1(tok, other):
                    f_ed1 = True
            tot += 1
            if f_ex:
                ex += 1
            elif f_ed1:
                ed1_only += 1
    if tot == 0:
        return 0.0, 0.0
    return ex / tot * 100.0, ed1_only / tot * 100.0


def label_bottleneck_stats(
    folio_order: List[str], folio_lines: Dict[str, List[List[str]]], folio_section: Dict[str, str]
) -> Tuple[float, float, float]:
    prose_vocab = set()
    label_toks: List[str] = []
    for f in folio_order:
        sec = folio_section[f]
        for ln in folio_lines[f]:
            if len(ln) <= 2:
                label_toks.extend(ln)
            elif len(ln) >= 5 and sec in ("H", "B", "S"):
                prose_vocab.update(ln)
    if not label_toks:
        return 0.0, 0.0, 0.0
    med_g = statistics.median(len(t) for t in label_toks)
    in_prose = sum(1 for t in label_toks if t in prose_vocab) / len(label_toks) * 100.0
    ex_ed1 = 0
    for t in label_toks:
        if t in prose_vocab or any(is_edit_le_1(t, p) for p in prose_vocab if abs(len(p) - len(t)) <= 1):
            ex_ed1 += 1
    return med_g, in_prose, (ex_ed1 / len(label_toks) * 100.0)


def evaluate_model(
    folio_order: List[str],
    folio_lines: Dict[str, List[List[str]]],
    folio_section: Dict[str, str],
    n_shuffles: int = 5,
    seed: int = 408,
) -> Dict[str, float]:
    rng = random.Random(seed)
    all_lines = [ln for f in folio_order for ln in folio_lines[f]]
    all_toks = [t for ln in all_lines for t in ln]
    n_toks = len(all_toks)
    ttr = len(set(all_toks)) / n_toks if n_toks else 0.0

    h2_all = h2_stream(all_lines)
    b_lines = [ln for f in folio_order if folio_section[f] == "B" for ln in folio_lines[f]]
    h2_b = h2_stream(b_lines) if b_lines else h2_all

    obs_mi1 = mutual_info_1char(all_lines)
    obs_cl_mi = cross_line_mi_1char(folio_lines)
    obs_lr = pearson_len_r(all_lines)
    obs_vex = vertical_interior_exact(folio_lines)
    w5_ex, w5_twin = window5_stats(folio_lines)

    n_mi1, n_cl, n_lr, n_vex = [], [], [], []
    for _ in range(n_shuffles):
        sh_map: Dict[str, List[List[str]]] = {}
        sh_all: List[List[str]] = []
        for f in folio_order:
            fl = []
            for ln in folio_lines[f]:
                cp = ln[:]
                rng.shuffle(cp)
                fl.append(cp)
                sh_all.append(cp)
            sh_map[f] = fl
        n_mi1.append(mutual_info_1char(sh_all))
        n_cl.append(cross_line_mi_1char(sh_map))
        n_lr.append(pearson_len_r(sh_all))
        n_vex.append(vertical_interior_exact(sh_map))

    fsh_map: Dict[str, List[List[str]]] = {}
    for f in folio_order:
        flat = [t for ln in folio_lines[f] for t in ln]
        rng.shuffle(flat)
        rebuilt = []
        pos = 0
        for ln in folio_lines[f]:
            rebuilt.append(flat[pos : pos + len(ln)])
            pos += len(ln)
        fsh_map[f] = rebuilt
    _, fsh_twin = window5_stats(fsh_map)

    net_mi1 = obs_mi1 - statistics.mean(n_mi1)
    net_cl = obs_cl_mi - statistics.mean(n_cl)
    reset_pct = (1.0 - max(0.0, net_cl) / net_mi1) * 100.0 if net_mi1 > 1e-6 else 0.0

    med_g, in_prose, ex_ed1 = label_bottleneck_stats(folio_order, folio_lines, folio_section)

    return {
        "h2": h2_all,
        "h2_b": h2_b,
        "ttr": ttr,
        "mi1": net_mi1,
        "reset": reset_pct,
        "len_r": obs_lr - statistics.mean(n_lr),
        "vex": obs_vex - statistics.mean(n_vex),
        "w5_ex": w5_ex,
        "twin": w5_twin,
        "twin_lift": w5_twin - fsh_twin,
        "med_g": med_g,
        "in_prose": in_prose,
        "ex_ed1": ex_ed1,
    }


# ==============================================================================
# BILINGUAL LATIN + EARLY NEW HIGH GERMAN BALNEOLOGICAL / HERBAL CORPUS (1405-1445)
# ==============================================================================

ALPINE_BILINGUAL_PROSE = (
    # Latin balneological, herbal, furnace & astro-medical source lines
    "balneum vaporis cum herbis calidis et aqua fontis praeparatur ad humores malos educendos "
    "fornax aenea sub caldario lente calefiat ne fistula rumpatur et vapor per canales ascendat "
    "radix plantaginis cum foliis salviae in vino albo decoquatur contra dolorem capitis et febres "
    "sub signo arietis et luna crescente collecta herba virtutem habet purgandi sanguinem et stomachum "
    "vasa vitrea cum cinere et aqua pura laventur antequam liquor destillatus in cellario reponatur "
    # Early New High German (Tirol / Bayern Kunstbuch & Ricettari, 1410-1445)
    "man sol das wasser in dem kupfernen kessel sieden lassen bis der dampf durch die roehren steigt "
    "nim salbei und wegerich mit weissem wein und seud es sanft ueber dem feuer fuer das fieber "
    "das bad sol warm sein doch nicht zu heiss damit die kraefte des leibes nicht geschwaecht werden "
    "so der mond wachset im zeichen des widders sol man die wurzel graben und im schatten trocknen "
    "filter das wasser durch reinen sand und kieselstein in ein glaessernes gefaess ohne luft "
).split()


def build_bilingual_alpine_stream(
    folio_order: List[str],
    folio_lines: Dict[str, List[List[str]]],
    folio_currier: Dict[str, str],
    seed: int = 88,
) -> Dict[str, List[List[str]]]:
    """
    Simulates a bilingual Tyrolean/Bavarian medical-balneological compendium where Currier A
    and Currier B reflect dialect/register shifts across sections while preserving topical
    folio slices.
    """
    rng = random.Random(seed)
    n_total = len(ALPINE_BILINGUAL_PROSE)
    half = n_total // 2
    latin_pool = ALPINE_BILINGUAL_PROSE[:half]
    german_pool = ALPINE_BILINGUAL_PROSE[half:]

    out: Dict[str, List[List[str]]] = {}
    for fi, f in enumerate(folio_order):
        cur = folio_currier[f]
        src = latin_pool if cur == "A" else (german_pool if cur == "B" else ALPINE_BILINGUAL_PROSE)
        start = (fi * 5) % len(src)
        folio_pool = [src[(start + k) % len(src)] for k in range(30)]
        out[f] = [[rng.choice(folio_pool) for _ in range(len(ln))] for ln in folio_lines[f]]
    return out


def gen_kyeser_bellifortis_1430(
    folio_order: List[str],
    folio_lines: Dict[str, List[List[str]]],
    folio_currier: Dict[str, str],
    seed: int = 11,
) -> Dict[str, List[List[str]]]:
    """
    Konrad Kyeser, Bellifortis (BSB Clm 30150, c. 1430 / Göttingen 1405):
    1:1 cipher alphabet applied to bilingual Latin/German bath, furnace, and distillation text.
    """
    rng = random.Random(seed)
    plain = build_bilingual_alpine_stream(folio_order, folio_lines, folio_currier, seed=seed)
    alpha_in = "abcdefghijklmnopqrstuvwxyz"
    eva_out = [
        "a", "p", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l", "m",
        "n", "o", "q", "r", "s", "t", "u", "v", "w", "x", "y", "z", "ch",
    ]
    perm = eva_out[:]
    rng.shuffle(perm)
    sub = dict(zip(alpha_in, perm))
    return {f: [["".join(sub.get(ch, ch) for ch in w) for w in ln] for ln in plain[f]] for f in folio_order}


def gen_tyrol_kunstbuch_tachygraphy(
    folio_order: List[str],
    folio_lines: Dict[str, List[List[str]]],
    folio_currier: Dict[str, str],
    with_workshop_habits: bool = False,
    seed: int = 11,
) -> Dict[str, List[List[str]]]:
    """
    Alpine Kunstbuch / Ricettari (Brixen / Neustift / Innsbruck, c. 1410-1445):
      - Truncates inflectional endings and maps stems into reduced EVA consonant-vowel
        shorthand (notae),
      - Attaches guild gallows/loop prefixes (qo-, ch-, sh-, cth-, ok-, ot-) and standardized
        formulaic suspension endings (-aiin, -ain, -edy, -ol, -or, -dy, -y) (~0.75-0.90x length),
      - Optional scribal workshop habits: paragraph stem-mutation drift (Edit==1 variants),
        within-line cross-space sandhi with line-end reset, and 3.5% vertical column copy.
    """
    rng = random.Random(seed)
    plain = build_bilingual_alpine_stream(folio_order, folio_lines, folio_currier, seed=seed + 3)

    cons_map = {
        "b": "p", "c": "k", "d": "d", "f": "f", "g": "k", "h": "ch", "j": "y",
        "k": "k", "l": "l", "m": "m", "n": "n", "p": "p", "q": "q", "r": "r",
        "s": "s", "t": "t", "v": "f", "w": "f", "x": "k", "z": "s",
    }
    vowel_map = {"a": "a", "e": "e", "i": "i", "o": "o", "u": "o", "y": "y"}

    prefixes_a = ["", "ch", "sh", "ot", "ok", "cth", "ckh", "o"]
    prefixes_b = ["qo", "qok", "qot", "ch", "sh", "ol", "ot", ""]
    endings_a = ["ol", "or", "aiin", "ain", "y", "dy", "al", "ar"]
    endings_b = ["edy", "eedy", "aiin", "dy", "y", "ol", "ar", "ain"]

    def abbreviate_word(w: str, cur: str) -> str:
        # Stem truncation to first 3-4 letters (guild suspension)
        stem_raw = w[:3] if len(w) <= 5 else w[:4]
        core = "".join(cons_map.get(c, vowel_map.get(c, "")) for c in stem_raw)
        if not core:
            core = "ok"
        pfx = rng.choice(prefixes_b if cur == "B" else prefixes_a)
        sfx = rng.choice(endings_b if cur == "B" else endings_a)
        tok = pfx + core + sfx
        return tok[:6]

    def mutate_ed1(tok: str, cur: str) -> str:
        if len(tok) < 3:
            return tok + "y"
        r = rng.random()
        if r < 0.50:
            # Minim / vowel alternation (ain <-> aiin, edy <-> eedy)
            if "aiin" in tok:
                return tok.replace("aiin", "ain", 1)
            if "ain" in tok:
                return tok.replace("ain", "aiin", 1)
            if "eedy" in tok:
                return tok.replace("eedy", "edy", 1)
            if "edy" in tok:
                return tok.replace("edy", "eedy", 1)
        # 1-char substitution in middle
        i = rng.randrange(1, len(tok) - 1)
        repl = rng.choice("eoaiykrtdl" if cur == "B" else "oaieychslr")
        return tok[:i] + repl + tok[i + 1 :]

    out: Dict[str, List[List[str]]] = {}
    for f in folio_order:
        cur = folio_currier[f]
        gen_lines: List[List[str]] = []
        para_stems: List[str] = []
        for li, target_ln in enumerate(folio_lines[f]):
            n_toks = len(target_ln)
            src_words = plain[f][li]
            line: List[str] = []
            for pos in range(n_toks):
                # 3.5% vertical column copy from line k-1
                if with_workshop_habits and li >= 1 and n_toks >= 3 and rng.random() < 0.035:
                    prev_ln = gen_lines[li - 1]
                    proj = round(pos * (len(prev_ln) - 1) / (n_toks - 1)) if len(prev_ln) > 1 else 0
                    cand = prev_ln[max(0, min(len(prev_ln) - 1, proj))]
                    line.append(cand if rng.random() < 0.45 else mutate_ed1(cand, cur))
                    continue

                # 22% paragraph stem-mutation reuse (generates Edit==1 twins)
                if with_workshop_habits and para_stems and rng.random() < 0.22:
                    base = rng.choice(para_stems[-10:])
                    tok = base if rng.random() < 0.35 else mutate_ed1(base, cur)
                else:
                    w = src_words[pos % len(src_words)]
                    tok = abbreviate_word(w, cur)

                # Within-line cross-space sandhi (resets at line breaks)
                if with_workshop_habits and line:
                    prev_end = line[-1][-1]
                    if prev_end == "y" and rng.random() < 0.50 and not tok.startswith("q"):
                        tok = "q" + tok
                    elif prev_end in ("r", "s") and rng.random() < 0.50 and not tok.startswith("a"):
                        tok = "a" + tok

                line.append(tok)
                para_stems.append(tok)
            gen_lines.append(line)
        out[f] = gen_lines
    return out


def gen_loqo_cur4_2d(
    folio_order: List[str],
    folio_lines: Dict[str, List[List[str]]],
    folio_currier: Dict[str, str],
    folio_quire: Dict[str, str],
    p_vert: float = 0.035,
    seed: int = 11,
) -> Dict[str, List[List[str]]]:
    """Leave-One-Quire-Out (strict out-of-sample) Order-4 Currier Char Stream + 3.5% 2D Memory."""
    rng = random.Random(seed)
    K = 4
    quires = sorted(set(folio_quire.values()))
    all_lines = [ln for f in folio_order for ln in folio_lines[f]]
    alpha = sorted({c for ln in all_lines for t in ln for c in t})

    def fit_tables(train_lines: List[List[str]]) -> List[Dict[str, Tuple[List[str], List[int]]]]:
        raw: List[Dict[str, Counter]] = [defaultdict(Counter) for _ in range(K + 1)]
        for toks in train_lines:
            if not toks:
                continue
            s = "^" * K + " ".join(toks) + "$"
            for i in range(K, len(s)):
                ch = s[i]
                for o in range(1, K + 1):
                    raw[o][s[i - o : i]][ch] += 1
                raw[0][""][ch] += 1
        return [{ctx: (list(cnt.keys()), list(cnt.values())) for ctx, cnt in raw[o].items()} for o in range(K + 1)]

    def sample_ch(tables: List[Dict[str, Tuple[List[str], List[int]]]], ctx: str) -> str:
        for o in range(min(K, len(ctx)), 0, -1):
            ent = tables[o].get(ctx[-o:])
            if ent is not None:
                return rng.choices(ent[0], weights=ent[1])[0]
        ent0 = tables[0][""]
        return rng.choices(ent0[0], weights=ent0[1])[0]

    def mutate_eva(tok: str) -> str:
        lt = len(tok)
        r = rng.random()
        if r < 0.55 and lt >= 2:
            i = rng.randrange(lt)
            return tok[:i] + rng.choice(alpha) + tok[i + 1 :]
        if r < 0.80:
            i = rng.randrange(lt + 1)
            return tok[:i] + rng.choice(alpha) + tok[i:]
        if lt >= 3:
            i = rng.randrange(lt)
            return tok[:i] + tok[i + 1 :]
        return tok

    out: Dict[str, List[List[str]]] = {}
    for held_q in quires:
        train_by_cur: Dict[str, List[List[str]]] = defaultdict(list)
        train_all: List[List[str]] = []
        for f in folio_order:
            if folio_quire[f] != held_q:
                train_by_cur[folio_currier[f]].extend(folio_lines[f])
                train_all.extend(folio_lines[f])
        global_t = fit_tables(train_all)
        cur_t = {c: fit_tables(ls) for c, ls in train_by_cur.items()}

        for f in folio_order:
            if folio_quire[f] != held_q:
                continue
            tables = cur_t.get(folio_currier[f], global_t)
            gen_lines: List[List[str]] = []
            for target_ln in folio_lines[f]:
                n_toks = len(target_ln)
                line: List[str] = []
                ctx = "^" * K
                li = len(gen_lines)
                for pos in range(n_toks):
                    if p_vert > 0.0 and li >= 1 and n_toks >= 3 and rng.random() < p_vert:
                        lag = rng.choices((1, 2, 3), weights=(0.60, 0.25, 0.15))[0]
                        if li >= lag:
                            prev_ln = gen_lines[li - lag]
                            lp = len(prev_ln)
                            proj = round(pos * (lp - 1) / (n_toks - 1)) if n_toks > 1 else 0
                            cand = rng.choice(prev_ln[max(0, proj - 1) : min(lp, proj + 2)])
                            tok = cand if rng.random() < 0.42 else mutate_eva(cand)
                            line.append(tok)
                            ctx = (ctx + tok + " ")[-K:]
                            continue
                    buf: List[str] = []
                    steps = 0
                    while steps < 25:
                        ch = sample_ch(tables, ctx)
                        steps += 1
                        if ch in (" ", "$"):
                            if buf:
                                ctx = (ctx + " ")[-K:]
                                break
                            if ch == "$":
                                ctx = "^" * K
                            continue
                        buf.append(ch)
                        ctx = (ctx + ch)[-K:]
                    line.append("".join(buf) if buf else "ol")
                gen_lines.append(line)
            out[f] = gen_lines
    return out


def main() -> None:
    t0 = time.time()
    zl_path = sys.argv[1] if len(sys.argv) > 1 else "ZL3b-n.txt"

    print("==========================================================================")
    print("VOYNICH v3.4 — TYROL-BAVARIA BALNEOLOGICAL / KUNSTBUCH AUDIT (1405-1445)")
    print("==========================================================================\n")

    entries = parse_ivtff(zl_path)
    folio_order: List[str] = []
    folio_lines: Dict[str, List[List[str]]] = defaultdict(list)
    folio_currier: Dict[str, str] = {}
    folio_quire: Dict[str, str] = {}
    folio_section: Dict[str, str] = {}

    for e in entries:
        if e.folio not in folio_lines:
            folio_order.append(e.folio)
        folio_lines[e.folio].append(e.tokens)
        folio_currier[e.folio] = e.currier if e.currier in ("A", "B") else "OTHER"
        folio_quire[e.folio] = e.quire
        folio_section[e.folio] = e.section

    print(f"Loaded {len(entries)} lines across {len(folio_order)} folios from {zl_path}.")
    print("Net MI1 / Reset% / len_r / VertEx computed over 5 within-line shuffles.\n")

    models: List[Tuple[str, Dict[str, List[List[str]]]]] = [
        ("REAL (ZL3b-n)", dict(folio_lines)),
        ("LOQO (Cross-Quire) Cur-4+2D", gen_loqo_cur4_2d(folio_order, folio_lines, folio_currier, folio_quire, 0.035, 11)),
        ("Kyeser-Bellifortis (Clm 30150)", gen_kyeser_bellifortis_1430(folio_order, folio_lines, folio_currier, 11)),
        ("Tyrol-Kunstbuch Pure Tachy", gen_tyrol_kunstbuch_tachygraphy(folio_order, folio_lines, folio_currier, False, 11)),
        ("Tyrol-Kunstbuch + Workshop 2D", gen_tyrol_kunstbuch_tachygraphy(folio_order, folio_lines, folio_currier, True, 11)),
    ]

    print(
        "  Model                           | h2(s) | h2(B) |    TTR |   MI1  | Reset% |  len_r | VertEx | W5Ex% | TwinW5% | TwinLift | LblMed | Ex+Ed1%"
    )
    print(
        "  -------------------------------------------------------------------------------------------------------------------------------------------"
    )

    for mname, mdata in models:
        r = evaluate_model(folio_order, mdata, folio_section, n_shuffles=5, seed=408)
        print(
            f"  {mname:<31} | {r['h2']:5.3f} | {r['h2_b']:5.3f} | {r['ttr']:6.4f} | "
            f"{r['mi1']:+6.3f} | {r['reset']:5.1f}% | {r['len_r']:+6.3f} | {r['vex']:+6.2f} | "
            f"{r['w5_ex']:5.2f} | {r['twin']:7.2f} | {r['twin_lift']:+8.2f} | {r['med_g']:6.1f} | {r['ex_ed1']:6.1f}%"
        )

    print(f"\nCompleted in {time.time() - t0:.1f}s.")


if __name__ == "__main__":
    main()
