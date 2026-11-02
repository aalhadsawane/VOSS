"""H16 (E25): planner advantage over the best single loop by mean session length M and Weibull shape k, and survival dependence
(greedy vs survival-blind greedy). Reads the per-run CSV written by ``experiments.analysis.round4 E25 <csv>``."""
import ast, numpy as np, pandas as pd
from experiments.analysis.common import bootstrap_ci
df=pd.read_csv("docs/validation/data/E25_runs.csv")
def cell(s):
    d=ast.literal_eval(s)["tiers"]; M={5400.0:0.25,21600:1,86400:4}[float(d["nightly"]["length"]["median"])]; return M, d["idle"]["length"]["shape"]
df["M"],df["k"]=zip(*df.churn.map(cell))
def get(M,k,lab): return df[(df.M==M)&(df.k==k)&(df.label==lab)].set_index("seed").p99
rows=[]
for k in (0.6,1.0):
    for M in (0.25,1,4):
        g=get(M,k,"plan_greedy"); b=get(M,k,"plan_greedy_blind")
        singles={l:get(M,k,l).mean() for l in ("keepalive_inf","hist_prewarm")}; best=min(singles,key=singles.get)
        s=get(M,k,best); A=(1-g/s).to_numpy(); B=(b/g-1).to_numpy()
        a=bootstrap_ci(A,n=10000); bb=bootstrap_ci(B,n=10000)
        rows.append(dict(k=k,M=M,best=best,A=a[0],A_lo=a[1],A_hi=a[2],B=bb[0],B_lo=bb[1],B_hi=bb[2]))
r=pd.DataFrame(rows); print(r.round(3).to_string())
for k in (0.6,1.0):
    x={M:(1-get(M,k,"plan_greedy")/get(M,k,min(("keepalive_inf","hist_prewarm"),key=lambda l:get(M,k,l).mean()))).to_numpy() for M in (0.25,1,4)}
    for a,b in ((1,0.25),(1,4)):
        d=x[a]-x[b]; m,lo,hi=bootstrap_ci(d,n=10000); print(f"shape {k}: A(M={a}) - A(M={b}) = {m:.3f} [{lo:.3f},{hi:.3f}]")
