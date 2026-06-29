# Decision-making paradigms: Body regulation, homeostasis, interoception, active inference, and reinforcement learning in adaptive behavior

---

## 1. Homeostatic Regulation
Organisms select actions to restore internal physiological variables to genetically or developmentally fixed setpoints via negative-feedback control loops, with behavioral urgency (drive) proportional to the signed deviation from those setpoints.

**Key authors**: Walter B. Cannon, Claude Bernard, Clark L. Hull, Mehdi Keramati, Boris Gutkin, Karl Friston, Frederike H. Petzschner
**Key concepts**:
- Physiological state vector H(t) and setpoint H*
- Drive D(H(t)) = m·Σᵢ|hᵢ* − hᵢ,ₜ|ⁿ (motivational distance from setpoint)
- Primary reward r(Hₜ, Kₜ) = D(Hₜ) − D(Hₜ + Kₜ) (drive reduction)
- Negative feedback control loop: sensor → comparator → error → effector
- Predictive homeostasis and allostasis (setpoint shifting)
- Outcome impact vector Kₜ (additive physiological shift per action)
- Sensory-control loop closure (internal state → afferent signal → action → state change)
- Every good regulator must be a model of the system it regulates (Conant & Ashby, 1970)

---

## 2. Homeostatic Reinforcement Learning
A normative computational theory that formally unifies homeostatic regulation and temporal-difference reinforcement learning by redefining primary reward as drive reduction, proving mathematically that reward-maximization and physiological-stability minimization are equivalent objectives under temporal discounting.

**Key authors**: Mehdi Keramati, Boris Gutkin
**Key concepts**:
- Homeostatic reward r(Hₜ, Kₜ) = D(Hₜ) − D(Hₜ + Kₜ) as the RL reward signal
- Joint state-space of external environment sₜ and internal physiology Hₜ
- Homeostatic reward prediction error (hRPE) δₜ = r(Hₜ,Kₜ) + γ·V(Hₜ₊₁,sₜ₊₁) − V(Hₜ,sₜ)
- Equivalence theorem: argmax SDRπ = argmin SDDπ iff γ < 1
- State-dependent reward valuation / alliesthesia (same outcome, different internal states → different reward magnitude)
- Anticipatory responding (learned preventive actions before deficits arise)
- Orosensory proxy K̂ₜ for pre-consumption impact estimation
- Hyperpalatability as systematic overestimation of Kₜ → model of diet-induced obesity
- Physiological rationality: temporal discounting is normatively necessary for homeostatic stability

---

## 3. Bayesian Brain Hypothesis
*(Existing backbone slug: **bayesian-brain-hypothesis**)* The brain is a hierarchical Bayesian inference machine that continuously combines top-down prior predictions with bottom-up sensory likelihoods to form posterior beliefs about the causes of its sensory inputs; perception, learning, and cognition are all forms of approximate posterior inference.

**Key authors**: Hermann von Helmholtz, Richard Gregory, Rao & Ballard, Karl Friston
**Key concepts**:
- Generative model p(s̃, ϑ|m) encoding likelihood and priors over hidden causes
- Recognition density q(ϑ|μ) as the approximate posterior encoded in neural states μ
- Variational free energy F(s̃,μ) as a tractable upper bound on surprise: F ≥ −ln p(s̃|m)
- Precision Π (inverse variance) as the neural substrate of attention and reliability weighting
- Perceptual inference: update μ to minimize KL-divergence from true posterior
- Learning: update generative model parameters θ from persistent prediction errors
- Hierarchical prediction: each cortical level generates predictions for the level below; bottom-up signals carry only prediction errors
- Drive D(Hₜ) = −ln p(Hₜ) establishes formal equivalence between surprise and homeostatic cost

---

## 4. Active Inference (Free Energy Principle)
*(Existing backbone slug: **active-inference**)* Adaptive agents minimize variational free energy — a bound on sensory surprise — through two simultaneous routes: updating internal beliefs (perception) and acting to make sensory inputs conform to predictions; action, perception, learning, and attention are all facets of a single free-energy-minimizing objective.

**Key authors**: Karl Friston, Stefan Kiebel
**Key concepts**:
- Free energy principle: F = Energy − Entropy = Complexity − Accuracy
- Action as self-fulfilling prophecy: reflex arcs fulfill proprioceptive predictions
- Epistemic foraging: agents sample states that reduce uncertainty (expected free energy minimization)
- Hierarchical generative model: top-down predictions, bottom-up prediction errors
- Precision-weighted prediction errors implement attention
- Active inference vs. perceptual inference as dual routes to free energy reduction
- Policy selection based on expected free energy across future trajectories
- Formal unification of motor control, Pavlovian behavior, and goal-directed planning

---

## 5. Interoceptive Active Inference
An extension of the Free Energy Principle applied specifically to the internal milieu: biological agents maintain physiological homeostasis and allostasis by minimizing variational free energy over *interoceptive* sensory channels, with the brain constructing a hierarchical generative model of bodily states and selecting regulatory actions to fulfill survival-compatible interoceptive priors.

**Key authors**: Karl Friston, Frederike H. Petzschner, Sarah N. Garfinkel, Martin P. Paulus, Christof Koch, Sahib S. Khalsa, Mehdi Keramati, Boris Gutkin
**Key concepts**:
- Interoceptive sensory signal s̃(t) as the observation (heart rate, glucose, temperature, osmolality, etc.)
- Interoceptive prediction error ε(t) = s̃(t) − p̂(t) driving both model updating and regulatory action
- Survival-compatible interoceptive priors replacing fixed setpoints
- Dual equivalence: D(Hₜ) = −ln p(Hₜ) → homeostatic drive = informational surprise
- Allostasis as shifting interoceptive priors in response to predicted future demands
- Precision γᵢ modulating each interoceptive channel (pathological weighting → anxiety, alexithymia)
- Viscero-motor hierarchy: brainstem → parabrachial → insular cortex → ACC → subgenual cortex
- Context-dependent setpoint shifting via learned associations in higher hierarchy levels
- Formal unification of IAI and HRL: both minimize the same objective via equivalent formulations

---

## 6. Predictive Coding
The brain minimizes prediction errors at every level of a hierarchical generative model by continuously generating top-down sensory predictions; only the residual prediction errors — not raw sensory data — are propagated upward, making perception a constructive, model-driven inference process rather than passive signal transduction.

**Key authors**: Rao & Ballard, Karl Friston, Stefan Kiebel, Frederike H. Petzschner
**Key concepts**:
- Hierarchical generative model with empirical priors
- Prediction error ε(l)(t) = actual input − top-down prediction (propagated upward)
- Top-down connections carry predictions (backward); bottom-up connections carry errors (forward)
- Precision Π(l) as dynamically adjustable gain on prediction errors (attention mechanism)
- Variational free energy F = KL[q‖p(ϑ|s̃)] − ln p(s̃|m) = Complexity − Accuracy
- Sensory attenuation: predicted inputs produce attenuated neural responses
- Mismatch negativity as empirical signature of prediction error in EEG
- Extended to interoception: interoceptive prediction errors drive body-regulatory actions
- Temporal extension (Friston & Kiebel, 2009): generalized motion coordinates for dynamic stimuli
- Hallucinations/delusions explained by pathological precision weighting or hyper-strong priors

---

## Cross-paradigm interaction map

Collecting all distinct neural substrates mentioned in the `## Primary Locus` sections across all deep reports:

| Paradigm | Hypothalamus | VTA / SNc (dopamine) | Nucleus Accumbens / Ventral Striatum | Dorsal Striatum / Basal Ganglia | Prefrontal Cortex | Orbitofrontal Cortex | Insula | Anterior Cingulate Cortex (ACC) | Subgenual Cortex | Brainstem Nuclei (NTS, PBN) | Thalamus | Primary Sensory Cortices (V1/S1/A1) | PAG / Parabrachial |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Homeostatic Regulation** | ✓ | ✓ | ✗ | ✓ | ✗ | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✗ | ✓ |
| **Homeostatic RL** | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| **Bayesian Brain Hypothesis** | ✗ | ✓ | ✗ | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ | ✓ | ✗ |
| **Active Inference** | ✓ | ✓ | ✗ | ✓ | ✓ | ✗ | ✓ | ✓ | ✗ | ✓ | ✓ | ✓ | ✗ |
| **Interoceptive Active Inference** | ✓ | ✓ | ✗ | ✓ | ✓ | ✗ | ✓ | ✓ | ✓ | ✓ | ✗ | ✗ | ✓ |
| **Predictive Coding** | ✓ | ✓ | ✗ | ✓ | ✓ | ✗ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ |

> **Reading the map**: The hypothalamus, dopaminergic VTA/SNc, basal ganglia, and prefrontal cortex are the most widely shared substrates — active in 4–6 of the 6 paradigms, confirming they are the critical convergence nodes for body-regulation and adaptive behavior. The insula and ACC are shared by all interoceptive paradigms (IAI, Predictive Coding, Homeostatic Regulation, Active Inference). Primary sensory cortices appear only in paradigms that explicitly model exteroceptive hierarchies (Bayesian Brain, Predictive Coding, Active Inference). PAG/Parabrachial nuclei are specific to the viscero-motor pathways (IAI, Homeostatic Regulation).

---

## References

- **Bernard, C. (1865/1957)** — *Introduction to the Study of Experimental Medicine* — [cited in Keramati & Gutkin (2014) as foundational *milieu intérieur* concept]
- **Cabanac, M. (1971)** — *Physiological role of pleasure* — Science — [cited in Keramati & Gutkin (2014) as empirical basis for alliesthesia/state-dependent valuation]
- **Cannon, W.B. (1929)** — *Organization for physiological homeostasis* — Physiological Reviews — [cited in Keramati & Gutkin (2014) as origin of homeostasis concept]
- **Conant, R.C. & Ashby, W.R. (1970)** — *Every good regulator of a system must be a model of that system* — International Journal of Systems Science — [cited in Keramati & Gutkin (2014) and Petzschner et al. (2021)]
- **Friston, K. (2010)** — *The free-energy principle: a unified brain theory?* — Nature Reviews Neuroscience — DOI: 10.1038/nrn2787
- **Friston, K. & Kiebel, S. (2009)** — *Predictive coding under the free-energy principle* — Philosophical Transactions of the Royal Society B: Biological Sciences, 364, 1211–1221 — [cited in Petzschner et al. (2021)]
- **Hull, C.L. (1943)** — *Principles of Behavior* — [drive-reduction theory; cited in Keramati & Gutkin (2014)]
- **Keramati, M. & Gutkin, B. (2014)** — *Homeostatic reinforcement learning for integrating reward collection and physiological stability* — eLife, 3, e04811 — DOI: 10.7554/eLife.04811
- **Petzschner, F.H., Garfinkel, S.N., Paulus, M.P., Koch, C. & Khalsa, S.S. (2021)** — *Computational Models of Interoception and Body Regulation* — Trends in Neurosciences, 44(1), 63–76 — DOI: 10.1016/j.tins.2020.09.012
- **Rao, R.P. & Ballard, D.H. (1999)** — *Predictive coding in the visual cortex: a functional interpretation of some extra-classical receptive field effects* — Nature Neuroscience, 2, 79–87 — [cited as foundational PC reference in Friston (2010) and Petzschner et al. (2021)]
- **Sutton, R.S. & Barto, A.G. (1998)** — *Reinforcement Learning: An Introduction* — MIT Press — [cited in Keramati & Gutkin (2014) as formal RL framework that HRL extends]

## Research Tree Map

```
Decision-making paradigms: Body regulation, homeostasis, interoception, active inference, and reinforcement learning in adaptive behavior
├── Homeostatic Regulation
│   ├── homeostatic-reinforcement-learning-hrl-with-drive-reduction-reward
│   ├── continuous-drive-dynamics-with-urgency-threshold-policy
│   └── interoceptive-active-inference-iai-with-free-energy-minimisation
├── Homeostatic Reinforcement Learning
│   ├── drive-reduction-td-q-learning-model-free
│   ├── continuous-drive-gradient-reactive-policy-algebraic-geometric
│   └── free-energy-minimizing-homeostatic-agent-probabilistic-bayesian
├── Interoceptive Active Inference
│   ├── continuous-free-energy-gradient-descent-with-precision-weighted-prediction-errors
│   ├── homeostatic-reinforcement-learning-with-drive-reduction-reward
│   └── expected-free-energy-policy-selection-with-allostatic-prior-shifting
└── Predictive Coding
    ├── hierarchical-precision-weighted-prediction-error-minimization-gradient-descent-ode
    ├── algebraic-precision-weighted-bayesian-filtering-single-step-conjugate-update
    └── active-inference-with-expected-free-energy-probabilistic-policy-selection
```
