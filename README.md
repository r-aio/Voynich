# Voynich

## Full Reproducibility & Independent Verification

### Option A: Directly on GitHub (Zero Installation)
1. Open the **Actions** tab in this repository.
2. Select the **L0-ISM Full Voynich Verification** workflow.
3. Open the latest run (or click **Run workflow**) to inspect the C99 Zero-Heap compilation check, `ZL3b-n.txt` vs `RF1b-e.txt` cross-transcription coverage, `TOP 50 UNKNOWN` residual audit, Monte Carlo negative controls, and Microsoft Z3 `UNSAT` formal proofs.

### Option B: Locally (Linux / macOS / Windows)
```bash
git clone [https://github.com/r-aio/Voynich.git](https://github.com/r-aio/Voynich.git)
cd Voynich
pip install z3-solver
python voynich_ivtff_auditor.py ZL3b-n.txt RF1b-e.txt
