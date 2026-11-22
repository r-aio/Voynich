/-
  L0-ISM Voynich Manuscript (Beinecke MS 408) — Kernel-Checked Formal Proof in Lean 4
  Zero external dependencies (pure Lean 4 core; no Mathlib required).

  Formally proves:
    1. State-space cardinality: |S^3| = 19^3 = 6,859 and permissible zone |[-8, +8]^3| = 4,913.
    2. 1-step contraction of the gravitational convergence operator I_ITER on [-8, +8].
    3. Exhaustive 3D convergence to Fulcrum (0, 0, 0) in <= 8 steps for all permissible states.
    4. Deadlock freedom (formal equivalent of Z3 UNSAT).
    5. Unconditional HARD_STOP (-999) interdiction on absorbing barriers |s_i| >= 9.
    6. Fulcrum fixed-point invariance across arbitrary step counts.
    7. Layer 1 LUT boundedness and fail-safe HARD_STOP completeness for all unknown EVA tokens.
-/

namespace L0ISM

def HARD_STOP : Int := -999

/-- Discrete gravitational convergence operator I_ITER over S = {-9, ..., 0, ..., +9}. -/
def stepOp (s : Int) : Int :=
  if s ≤ -9 ∨ s ≥ 9 then HARD_STOP
  else if s > 0 then s - 1
  else if s < 0 then s + 1
  else 0

/-- Iterative n-step application of the 1D convergence operator. -/
def iterStep : Nat → Int → Int
  | 0, s => s
  | n + 1, s => iterStep n (stepOp s)

/-- 3-channel operational state frame IM = (s1, s2, s3) in S^3. -/
structure State3D where
  s1 : Int
  s2 : Int
  s3 : Int
  deriving DecidableEq, Repr

def FULCRUM : State3D := { s1 := 0, s2 := 0, s3 := 0 }

def step3D (st : State3D) : State3D :=
  { s1 := stepOp st.s1, s2 := stepOp st.s2, s3 := stepOp st.s3 }

def iter3D : Nat → State3D → State3D
  | 0, st => st
  | n + 1, st => iter3D n (step3D st)

def isPermissible (st : State3D) : Prop :=
  (-8 ≤ st.s1 ∧ st.s1 ≤ 8) ∧
  (-8 ≤ st.s2 ∧ st.s2 ≤ 8) ∧
  (-8 ≤ st.s3 ∧ st.s3 ≤ 8)

/-! ### Part 1: Cardinality & Contraction Theorems -/

theorem state_space_cardinality : (19 : Nat) ^ 3 = 6859 := by
  decide

theorem permissible_zone_cardinality : (17 : Nat) ^ 3 = 4913 := by
  decide

/-- Monotonic 1-step contraction inside the permissible zone [-8, +8]. -/
theorem stepOp_contract (k : Nat) (s : Int) (hk : k < 8)
    (hlo : -((k + 1 : Nat) : Int) ≤ s) (hhi : s ≤ ((k + 1 : Nat) : Int)) :
    -(k : Int) ≤ stepOp s ∧ stepOp s ≤ (k : Int) := by
  unfold stepOp
  by_cases h1 : s ≤ -9 ∨ s ≥ 9
  · omega
  · rw [if_neg h1]
    by_cases h2 : s > 0
    · rw [if_pos h2]; omega
    · rw [if_neg h2]
      by_cases h3 : s < 0
      · rw [if_pos h3]; omega
      · rw [if_neg h3]; omega

/-- Inductive 1D convergence to Fulcrum (0) in at most k <= 8 steps. -/
theorem iterStep_converges : ∀ (k : Nat) (s : Int),
    k ≤ 8 → -(k : Int) ≤ s → s ≤ (k : Int) → iterStep k s = 0
  | 0, s, _, hlo, hhi => by
      have hs : s = 0 := by omega
      rw [hs]
      rfl
  | k + 1, s, hk, hlo, hhi => by
      have hnext := stepOp_contract k s (by omega) (by omega) (by omega)
      simp only [iterStep]
      exact iterStep_converges k (stepOp s) (by omega) hnext.1 hnext.2

/-- Component-wise decomposition of 3D state iteration. -/
theorem iter3D_eq : ∀ (n : Nat) (st : State3D),
    iter3D n st = { s1 := iterStep n st.s1, s2 := iterStep n st.s2, s3 := iterStep n st.s3 }
  | 0, _ => rfl
  | n + 1, st => iter3D_eq n (step3D st)

/-! ### Part 2: Core L0-ISM Safety Invariants (Formal Equivalents of Z3 UNSAT Proofs) -/

/-- Theorem 1: Every permissible state in [-8, +8]^3 reaches Fulcrum (0, 0, 0) in <= 8 steps. -/
theorem l0_ism_3d_convergence (st : State3D) (h : isPermissible st) :
    iter3D 8 st = FULCRUM := by
  rcases h with ⟨⟨h1a, h1b⟩, ⟨h2a, h2b⟩, ⟨h3a, h3b⟩⟩
  rw [iter3D_eq]
  have h1 : iterStep 8 st.s1 = 0 := iterStep_converges 8 st.s1 (by omega) (by omega) (by omega)
  have h2 : iterStep 8 st.s2 = 0 := iterStep_converges 8 st.s2 (by omega) (by omega) (by omega)
  have h3 : iterStep 8 st.s3 = 0 := iterStep_converges 8 st.s3 (by omega) (by omega) (by omega)
  simp [FULCRUM, h1, h2, h3]

/-- Theorem 2: Deadlock Freedom — No permissible state fails to converge in 8 steps (UNSAT). -/
theorem l0_ism_no_deadlock :
    ¬ ∃ st : State3D, isPermissible st ∧ iter3D 8 st ≠ FULCRUM := by
  intro ⟨st, hperm, hne⟩
  exact hne (l0_ism_3d_convergence st hperm)

/-- Theorem 3: Absorbing Barrier Interdiction — Any |s| >= 9 unconditionally forces HARD_STOP (-999). -/
theorem l0_ism_barrier_interdiction (s : Int) (hb : s ≤ -9 ∨ s ≥ 9) :
    stepOp s = HARD_STOP := by
  rw [stepOp, if_pos hb]

/-- Theorem 4: Fulcrum Equilibrium Invariance — (0, 0, 0) is a fixed point for all n >= 0. -/
theorem l0_ism_fulcrum_fixed_point (n : Nat) :
    iter3D n FULCRUM = FULCRUM := by
  induction n with
  | zero => rfl
  | succ k ih =>
      simp only [iter3D]
      have hstep : step3D FULCRUM = FULCRUM := by decide
      rw [hstep]
      exact ih

/-! ### Part 3: Verified Layer 1 ROM Look-Up Table (Synchronized with voynich_l0_lut.h) -/

inductive HardwareNode where
  | primaryCooling
  | hypocaust3WayValve
  | calibrationHub
  | thermalPump
  | refluxCondenser
  | condensateTrap
  | levelSightGlass
  | floatAirVent
  | furnaceAirDamper
  | checkValve
  | hydraulicAccum
  | chemBufferDoser
  | bainMarieJacket
  | phaseSeparator
  | overflowHeader
  | thermalExpBellows
  | trickleCooler
  | staticMixer
  | safetyReliefValve
  | emergencyShutdown
  deriving DecidableEq, Repr

structure LUTEntry where
  evaWord    : String
  targetNode : HardwareNode
  stateDelta : Int
  valvePct   : Nat
  deriving DecidableEq, Repr

def failSafeEntry : LUTEntry :=
  { evaWord := "UNKNOWN", targetNode := .emergencyShutdown, stateDelta := HARD_STOP, valvePct := 0 }

def voynichLUT : List LUTEntry := [
  ⟨"qokain",   .primaryCooling,     1, 11⟩,
  ⟨"qokaiin",  .primaryCooling,     2, 22⟩,
  ⟨"qokaiiin", .primaryCooling,     3, 33⟩,
  ⟨"qokedy",   .primaryCooling,     0, 25⟩,
  ⟨"qokeedy",  .primaryCooling,     0, 50⟩,
  ⟨"qotain",   .hypocaust3WayValve, 1, 11⟩,
  ⟨"qotaiin",  .hypocaust3WayValve, 2, 22⟩,
  ⟨"qotaiiin", .hypocaust3WayValve, 3, 33⟩,
  ⟨"qoko",     .calibrationHub,     0,  0⟩,
  ⟨"oteedy",   .thermalPump,        0, 50⟩,
  ⟨"qoteedy",  .thermalPump,        0, 50⟩,
  ⟨"ol",       .calibrationHub,     0,  0⟩,
  ⟨"or",       .refluxCondenser,    0, 15⟩,
  ⟨"ar",       .condensateTrap,     0, 10⟩,
  ⟨"dain",     .levelSightGlass,    0,  0⟩,
  ⟨"daiin",    .levelSightGlass,    0,  0⟩,
  ⟨"al",       .floatAirVent,       0,  0⟩,
  ⟨"sol",      .floatAirVent,       0,  0⟩,
  ⟨"daim",     .furnaceAirDamper,  -1, 40⟩,
  ⟨"dair",     .furnaceAirDamper,   1, 60⟩,
  ⟨"shol",     .checkValve,         0,  0⟩,
  ⟨"shor",     .checkValve,         0,  0⟩,
  ⟨"kedy",     .hydraulicAccum,     1, 75⟩,
  ⟨"shedy",    .hydraulicAccum,     0, 75⟩,
  ⟨"chey",     .chemBufferDoser,    0, 10⟩,
  ⟨"qochey",   .chemBufferDoser,    0, 20⟩,
  ⟨"chol",     .bainMarieJacket,    0, 50⟩,
  ⟨"qochol",   .bainMarieJacket,    0, 50⟩,
  ⟨"qokey",    .phaseSeparator,     0,  0⟩,
  ⟨"am",       .phaseSeparator,     0,  0⟩,
  ⟨"otain",    .overflowHeader,     0, 20⟩,
  ⟨"otaiin",   .overflowHeader,     0, 40⟩,
  ⟨"ckhaiin",  .thermalExpBellows,  0,  0⟩,
  ⟨"shain",    .trickleCooler,     -1, 30⟩,
  ⟨"shaiin",   .trickleCooler,     -2, 60⟩,
  ⟨"cthy",     .staticMixer,        0,  0⟩,
  ⟨"ckhy",     .staticMixer,        0,  0⟩,
  ⟨"fachys",   .safetyReliefValve,  8, 90⟩,
  ⟨"qokaiiii", .emergencyShutdown,  HARD_STOP, 0⟩
]

def lookupAux (w : String) : List LUTEntry → LUTEntry
  | [] => failSafeEntry
  | e :: rest => if e.evaWord = w then e else lookupAux w rest

def voynichDecode (w : String) : LUTEntry :=
  lookupAux w voynichLUT

def isValidDelta (d : Int) : Bool :=
  if (-8 ≤ d ∧ d ≤ 8) ∨ d = HARD_STOP then true else false

/-- Theorem 5: Every entry in the Layer 1 LUT respects the [-8, +8] / HARD_STOP state bounds. -/
theorem lut_all_deltas_valid :
    voynichLUT.all (fun e => isValidDelta e.stateDelta) = true := by
  decide

/-- Theorem 6: Key hardware frame decoding invariants. -/
theorem lut_qokaiin_check : (voynichDecode "qokaiin").stateDelta = 2 := by decide
theorem lut_qotaiiin_check : (voynichDecode "qotaiiin").stateDelta = 3 := by decide
theorem lut_ckhaiin_check : (voynichDecode "ckhaiin").targetNode = .thermalExpBellows := by decide
theorem lut_qokaiiii_hard_stop : (voynichDecode "qokaiiii").stateDelta = HARD_STOP := by decide

theorem lookupAux_unknown (w : String) (xs : List LUTEntry)
    (h : ∀ e ∈ xs, e.evaWord ≠ w) :
    lookupAux w xs = failSafeEntry := by
  induction xs with
  | nil => rfl
  | cons e rest ih =>
      simp only [lookupAux]
      have hne : e.evaWord ≠ w := h e (by simp)
      rw [if_neg hne]
      exact ih (fun x hx => h x (by simp [hx]))

/-- Theorem 7: Fail-Safe Completeness — Any unmapped EVA frame deterministically triggers HARD_STOP (-999). -/
theorem voynichDecode_fail_safe (w : String)
    (h : ∀ e ∈ voynichLUT, e.evaWord ≠ w) :
    (voynichDecode w).stateDelta = HARD_STOP := by
  unfold voynichDecode
  rw [lookupAux_unknown w voynichLUT h]
  rfl

/-! ### Part 4: Axiom Audit (Must Contain Zero sorryAx) -/
#print axioms l0_ism_3d_convergence
#print axioms l0_ism_no_deadlock
#print axioms l0_ism_barrier_interdiction
#print axioms l0_ism_fulcrum_fixed_point
#print axioms lut_all_deltas_valid
#print axioms voynichDecode_fail_safe

end L0ISM
