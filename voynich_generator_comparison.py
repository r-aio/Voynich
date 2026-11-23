# Run inside Voynich-2.4/: python3 voynich_generator_comparison.py (about 4 min; needs voynich_ivtff_auditor.py and ZL3b-n.txt)
import sys, re, math, random, statistics
from collections import Counter, defaultdict
sys.path.insert(0,'.')
import voynich_ivtff_auditor as A
rng=random.Random(11)
folio_re=re.compile(r"<(f[0-9]+[rv][0-9]*|fRos)\b",re.I)
fol=defaultdict(list); cur=""
for raw in open('ZL3b-n.txt',encoding='utf-8',errors='ignore'):
    s=raw.strip(); m=folio_re.search(s)
    if m: cur=m.group(1).lower()
    t=A.normalize_ivtff_line(raw)
    if len(t)>=2: fol[cur].append(t)
real=dict(fol)
alltoks=[t for ls in real.values() for l in ls for t in l]
gfreq=Counter(alltoks); gw=list(gfreq); gc=list(gfreq.values())
alpha=sorted(set("".join(alltoks)))

# ---------- metrics ----------
def MI(p):
    n=len(p); c=Counter(p); x=Counter(a for a,_ in p); y=Counter(b for _,b in p)
    return sum(v/n*math.log2((v/n)/((x[a]/n)*(y[b]/n))) for (a,b),v in c.items())
def pairs(lines,lag): return [(l[i][-1],l[i+lag][0]) for l in lines for i in range(len(l)-lag)]
def shuf(lines):
    out=[]
    for l in lines: x=l[:]; rng.shuffle(x); out.append(x)
    return out
def pear(xs,ys):
    mx,my=statistics.mean(xs),statistics.mean(ys)
    num=sum((a-mx)*(b-my) for a,b in zip(xs,ys)); den=math.sqrt(sum((a-mx)**2 for a in xs)*sum((b-my)**2 for b in ys))
    return num/den if den else 0
def lenr(lines):
    xs=[len(l[i]) for l in lines for i in range(len(l)-1)]; ys=[len(l[i+1]) for l in lines for i in range(len(l)-1)]
    return pear(xs,ys)
def vert(flines):
    hit=n=0; nh=0
    for ls in flines.values():
        for k in range(1,len(ls)):
            prev,curl=ls[k-1],ls[k]; sh=curl[:]; rng.shuffle(sh)
            for j in range(1,len(curl)-1):
                win=prev[max(0,j-1):j+2]
                n+=1; hit+= curl[j] in win; nh+= sh[j] in win
    return hit/n*100, nh/n*100
def metrics(flines):
    lines=[l for ls in flines.values() for l in ls]
    out={}
    for lag in (1,2):
        o=MI(pairs(lines,lag)); b=statistics.mean(MI(pairs(shuf(lines),lag)) for _ in range(2)); out[f"MI{lag}"]=o-b
    out["len_r"]=lenr(lines)-statistics.mean(lenr(shuf(lines)) for _ in range(2))
    o,b=vert(flines); out["vert_pp"]=o-b
    return out

# ---------- generators (same folio/line-length structure as real) ----------
def shape(flines): return {f:[len(l) for l in ls] for f,ls in flines.items()}
SH=shape(real)

def g_iid_folio():
    out={}
    for f,ls in real.items():
        pool=[t for l in ls for t in l]
        out[f]=[[rng.choice(pool) for _ in range(len(l))] for l in ls]
    return out
# grille: word = prefix+mid+suffix, each part from global tables
def split3(t):
    n=len(t); a=max(1,n//3); b=max(a,n-max(1,n//3)); return t[:a],t[a:b],t[b:]
parts=[split3(t) for t in alltoks]
P=Counter(p[0] for p in parts); M=Counter(p[1] for p in parts); S=Counter(p[2] for p in parts)
def draw(C): return rng.choices(list(C),weights=list(C.values()))[0]
def g_grille(walk=False):
    Pl=[k for k,_ in P.most_common()]; Ml=[k for k,_ in M.most_common()]; Sl=[k for k,_ in S.most_common()]
    out={}
    for f,ls in SH.items():
        res=[]; idx=[rng.randrange(len(Pl)),rng.randrange(len(Ml)),rng.randrange(len(Sl))]
        for n in ls:
            line=[]
            for _ in range(n):
                if walk:
                    idx[0]=(idx[0]+rng.choice((-1,0,1)))%len(Pl); idx[1]=(idx[1]+rng.choice((-1,0,1)))%len(Ml); idx[2]=(idx[2]+rng.choice((-1,0,1)))%len(Sl)
                    w=Pl[idx[0]]+Ml[idx[1]]+Sl[idx[2]]
                else: w=draw(P)+draw(M)+draw(S)
                line.append(w)
            res.append(line)
        out[f]=res
    return out
def mutate(w):
    r=rng.random()
    if r<0.4 and len(w)>1: i=rng.randrange(len(w)); return w[:i]+rng.choice(alpha)+w[i+1:]
    if r<0.7: i=rng.randrange(len(w)+1); return w[:i]+rng.choice(alpha)+w[i:]
    if len(w)>2: i=rng.randrange(len(w)); return w[:i]+w[i+1:]
    return w
def g_timm(pc):
    out={}
    for f,ls in SH.items():
        hist=[]; res=[]
        for n in ls:
            line=[]
            for _ in range(n):
                if hist and rng.random()<pc:
                    w=mutate(rng.choice(hist[-10:])) if rng.random()<0.7 else rng.choice(hist[-10:])
                else: w=rng.choices(gw,weights=gc)[0]
                line.append(w); hist.append(w)
            res.append(line)
        out[f]=res
    return out
# order-3 character stream with space
K=3; tr=defaultdict(Counter)
for ls in real.values():
    for l in ls:
        s="^"*K+" ".join(l)+"$"
        for i in range(K,len(s)): tr[s[i-K:i]][s[i]]+=1
trc={k:(list(v),list(v.values())) for k,v in tr.items()}
def g_char():
    out={}
    for f,ls in SH.items():
        res=[]
        for n in ls:
            while True:
                s="^"*K; 
                while len(s)<K+900:
                    ks,ws=trc[s[-K:]]
                    c=rng.choices(ks,weights=ws)[0]
                    if c=="$": break
                    s+=c
                toks=s[K:].split()
                if len(toks)>=n: res.append(toks[:n]); break
        out[f]=res
    return out
def selfstat(flines,W=10):
    eq=n1=tot=0
    def d1(a,b):
        if a==b or abs(len(a)-len(b))>1: return False
        if len(a)==len(b): return sum(x!=y for x,y in zip(a,b))==1
        if len(a)>len(b): a,b=b,a
        i=0
        while i<len(a) and a[i]==b[i]: i+=1
        return a[i:]==b[i+1:]
    for ls in flines.values():
        sq=[t for l in ls for t in l]
        for i,t in enumerate(sq):
            w=sq[max(0,i-W):i]
            if not w: continue
            tot+=1
            if t in w: eq+=1
            elif any(d1(t,x) for x in w): n1+=1
    return eq/tot*100,n1/tot*100
rows=[("REAL (ZL3b-n)",real)]
rows.append(("iid from folio vocab",g_iid_folio()))
rows.append(("Rugg-like grille, memoryless",g_grille(False)))
rows.append(("Rugg-like grille, drifting walk",g_grille(True)))
best=None
for pc in (0.15,0.3):
    g=g_timm(pc); e,n=selfstat(g)
    print(f"  Timm pc={pc}: identical-in-window {e:.1f}%  ed1 {n:.1f}%   (real 7.2% / 19.9%)")
    if best is None or abs(n-19.9)+abs(e-7.2)<best[0]: best=(abs(n-19.9)+abs(e-7.2),pc,g)
rows.append((f"Timm-like self-citation pc={best[1]}",best[2]))
rows.append(("char order-3 stream (with space)",g_char()))
print("\n%-36s %8s %8s %8s %9s"%("model","MI lag1","MI lag2","len r","vert pp"))
for name,fl in rows:
    m=metrics(fl)
    print("%-36s %8.3f %8.3f %8.3f %9.2f"%(name,m["MI1"],m["MI2"],m["len_r"],m["vert_pp"]))
