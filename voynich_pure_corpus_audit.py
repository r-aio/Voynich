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
                # Near window: distance 1..5
                lo_n = max(0, i - 5)
                hi_n = min(n, i + 6)
                has_near = any(seq[j] == tok for j in range(lo_n, hi_n) if j != i)
                near_tot += 1
                if has_near:
                    near_hits += 1

                # Far window on same folio: distance > 5
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
