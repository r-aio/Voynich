# Run from inside Voynich-2.3/: python3 voynich_stricter_controls.py  (needs voynich_ivtff_auditor.py and ZL3b-n.txt in cwd)

import sys, random, re, statistics
from collections import Counter, defaultdict
sys.path.insert(0,'.')
import voynich_ivtff_auditor as A

def load(path):
    lines=[]; cur=""
    folio_re=re.compile(r"<(f[0-9]+[rv][0-9]*|fRos)\b",re.I)
    for raw in open(path,encoding='utf-8',errors='ignore'):
        s=raw.strip(); m=folio_re.search(s)
        if m: cur=m.group(1).lower()
        t=A.normalize_ivtff_line(raw)
        if t: lines.append((cur,t))
    return lines

lines=load('ZL3b-n.txt')
toks=[t for _,l in lines for t in l]
print("tokens",len(toks),"lines",len(lines))
isL1=lambda t: A.classify_token(t)[0]=="L1"
L1flag={t:isL1(t) for t in set(toks)}

def adj(ls):
    n=0
    for l in ls:
        for a,b in zip(l,l[1:]):
            if a==b and L1flag.get(a,False): n+=1
    return n
obs=adj([l for _,l in lines]); print("observed adjacent L1 repeats (per line):",obs)

lens=[len(l) for _,l in lines]
def null_global(rng):
    t=toks[:]; rng.shuffle(t); out=[];i=0
    for n in lens: out.append(t[i:i+n]); i+=n
    return out
def null_folio(rng):
    byf=defaultdict(list)
    for f,l in lines: byf[f].append(l)
    out=[]
    for f,ls in byf.items():
        pool=[t for l in ls for t in l]; rng.shuffle(pool); i=0
        for l in ls: out.append(pool[i:i+len(l)]); i+=len(l)
    return out
def null_line(rng):
    out=[]
    for _,l in lines:
        x=l[:]; rng.shuffle(x); out.append(x)
    return out
rng=random.Random(1)
for name,fn in [("global shuffle (author's null)",null_global),("within-folio shuffle",null_folio),("within-line shuffle",null_line)]:
    v=[adj(fn(rng)) for _ in range(300)]
    m=statistics.mean(v); sd=statistics.pstdev(v)
    print(f"{name:32s} null mean={m:7.2f} sd={sd:5.2f}  enrichment={obs/m:4.2f}x  Z={(obs-m)/sd:+.2f}")

# repeats of ANY token (not only L1)
def adj_any(ls): return sum(1 for l in ls for a,b in zip(l,l[1:]) if a==b)
oa=adj_any([l for _,l in lines]); print("\nobserved adjacent repeats, any token:",oa)
for name,fn in [("global",null_global),("within-folio",null_folio),("within-line",null_line)]:
    v=[adj_any(fn(rng)) for _ in range(300)]
    print(f"{name:14s} mean={statistics.mean(v):6.2f} sd={statistics.pstdev(v):5.2f} enrich={oa/statistics.mean(v):.2f}x")

# ---- coverage controls for the L2a "positional DFA" ----
multi=[t for t in toks if len(t)>1]
acc=lambda t: A.classify_token(t)[0] in ("L1","L2A")
print("\nobserved multi-char acceptance:", sum(map(acc,multi))/len(multi))
# order-1 character Markov within words (start/end symbols), trained on corpus
tr=defaultdict(Counter)
for t in multi:
    s="^"+t+"$"
    for a,b in zip(s,s[1:]): tr[a][b]+=1
def gen():
    c="^"; out=""
    while True:
        ch=rng.choices(list(tr[c].keys()),weights=list(tr[c].values()))[0]
        if ch=="$" : break
        out+=ch; c=ch
        if len(out)>14: break
    return out
G=[gen() for _ in range(len(multi))]
G=[g for g in G if len(g)>1]
print("order-1 char-Markov synthetic words: acceptance =", sum(map(acc,G))/len(G), "(n=%d)"%len(G))
# order-0 letter-frequency words with same length distribution
fc=Counter(c for t in multi for c in t); cs=list(fc); w=list(fc.values())
R=["".join(rng.choices(cs,weights=w,k=len(t))) for t in multi]
print("iid letter words, same lengths:    acceptance =", sum(map(acc,R))/len(R))
# shuffle within word (author's test) for reference
S=[]
for t in multi:
    x=list(t); rng.shuffle(x); S.append("".join(x))
print("within-word shuffle (author's):    acceptance =", sum(map(acc,S))/len(S))

# ---- label independence of coverage ----
lab={t:A.VOYNICH_FULL_LUT[t].node for t in A.VOYNICH_FULL_LUT}
print("\nL1 LUT size:",len(lab),"distinct nodes:",len(set(lab.values())))
print("L1 words are the most frequent tokens? top-20 corpus tokens in LUT:",
      [(t,c,t in lab) for t,c in Counter(toks).most_common(20)])
