# Pavlovian Control of Food Approach — Mathematical Formulations

## Formulation 1: Rescorla–Wagner Cached-Value Agent with Softmax Action Selection
**Approach**: Algebraic stimulus–value learning via prediction-error update (Rescorla–Wagner / TD(0)) with probabilistic softmax action selection over a fixed Pavlovian repertoire.
**Based on**: Rangel, Camerer & Montague (2008), postulates P1–P3; Rescorla & Wagner (1972) learning rule as cited in Rangel (2013); retrieved knowledge on TD-0 and softmax action selection.

### Variables
| Symbol | Name | Description | Type |
|--------|------|-------------|------|
| V(s) | Pavlovian state value | Cached expected reward associated with grid cell s (CS value) | Continuous ∈ [0, R_max] |
| δ_t | Reward prediction error | Signed difference between received reward and predicted value at time t | Continuous ∈ (−R_max, R_max) |
| h_t | Hunger level | Internal deprivation state at time t, normalized | Continuous ∈ [0, 1] |
| r_t | Reward received | Scalar food reward obtained at time t (0 if no food eaten) | Continuous ∈ {0, r_food} |
| Q_Pav(a) | Pavlovian action value | Effective value of action a under Pavlovian control | Continuous |
| P(a) | Action probability | Probability of selecting action a | Continuous ∈ [0, 1] |
| d(s, s_food) | Distance to food | Manhattan distance from current cell s to nearest visible food | Discrete ≥ 0 |

### Parameters
| Symbol | Name | Default | Source |
|--------|------|---------|--------|
| α | Learning rate | 0.15 | Empirically validated range 0.01–0.5 for Pavlovian conditioning; Rescorla & Wagner (1972) as cited in Rangel (2013) |
| β | Inverse temperature | 5.0 | Standard softmax exploration parameter; retrieved knowledge from prior formulation runs |
| r_food | Food reward magnitude | 1.0 | Normalized reward unit |
| α_h | Hunger increment rate | 0.02 | Per-step hunger growth reflecting metabolic demand |
| γ_sat | Satiation decrement | 0.20 | Hunger reduction upon eating; calibrated to ~5 meals for full satiation |
| μ | Hunger–value gain | 1.5 | Wanting–hunger coupling; Berridge & Robinson (2003) as cited in Rangel (2013) |
| c_step | Movement cost | 0.01 | Small energetic cost of locomotion |
| R_max | Maximum value | 2.0 | Upper bound on V(s) for numerical stability |

### Equations

**Eq. 1 — Reward prediction error:**
`δ_t = r_t − V(s_t)`
$$\delta_t = r_t - V(s_t) \tag{1}$$

**Eq. 2 — Pavlovian value update (Rescorla–Wagner rule):**
`V(s_t) ← V(s_t) + α · δ_t`
$$V(s_t) \leftarrow V(s_t) + \alpha \cdot \delta_t \tag{2}$$

**Eq. 3 — Hunger dynamics:**
`h_{t+1} = clip(h_t + α_h − γ_sat · ate_t, 0, 1)`
$$h_{t+1} = \text{clip}\!\Big(h_t + \alpha_h - \gamma_{\text{sat}} \cdot \mathbb{1}[\text{ate}_t],\; 0,\; 1\Big) \tag{3}$$

**Eq. 4 — Hunger-modulated Pavlovian action value:**
`Q_Pav(a) = μ · h_t · V(s_a) − c_step · 𝟙[a ∈ moves]`
$$Q_{\text{Pav}}(a) = \mu \cdot h_t \cdot V(s_a) - c_{\text{step}} \cdot \mathbb{1}[a \in \text{moves}] \tag{4}$$

where s_a is the state that would result from action a. For the "eat" action, s_a = s_t and V(s_a) is the value of the current cell (food is consumed in place). For "stay", Q_Pav(stay) = μ · h_t · V(s_t). For movement actions, s_a is the adjacent cell.

**Eq. 5 — Softmax action selection:**
`P(a) = exp(β · Q_Pav(a)) / Σ_j exp(β · Q_Pav(j))`
$$P(a) = \frac{\exp\!\big(\beta \cdot Q_{\text{Pav}}(a)\big)}{\sum_{j} \exp\!\big(\beta \cdot Q_{\text{Pav}}(j)\big)} \tag{5}$$

### Decision logic

1. **Perceive**: Observe current position s_t, list of visible food positions, whether food is at current cell, current hunger h_t.
2. **Compute action values**: For each action a ∈ {up, down, left, right, stay, eat}:
   - If a = eat and food is present at s_t: Q_Pav(eat) = μ · h_t · V(s_t) (Eq. 4 with no movement cost).
   - If a = eat and no food present: Q_Pav(eat) = −∞ (action unavailable).
   - If a is a movement to valid cell s_a: Q_Pav(a) = μ · h_t · V(s_a) − c_step (Eq. 4).
   - If a = stay: Q_Pav(stay) = μ · h_t · V(s_t).
   - If a is a movement to invalid cell (wall/boundary): Q_Pav(a) = −∞.
3. **Select action**: Sample action from probability distribution P(a) computed via softmax (Eq. 5).
4. **Execute action**: Perform selected action; observe reward r_t and whether agent ate.
5. **Update value**: Compute δ_t (Eq. 1) and update V(s_t) (Eq. 2).
6. **Update hunger**: Update h_{t+1} via Eq. 3.

**Key Pavlovian property**: The agent does *not* learn action–outcome mappings (no Q(s, a) table). It learns only state values V(s), and approach is hardwired — action values are derived from the Pavlovian values of destination states (P3). The agent cannot learn to avoid a food-predictive cue; it is compelled to approach high-V states (P1).

---

## Formulation 2: Incentive Salience Dual-Process Agent (Wanting–Liking Dissociation)
**Approach**: Dual signal-processing model with separate "wanting" (dopamine-mediated incentive salience) and "liking" (opioid-mediated hedonic value) channels, each with independent learning dynamics, combined for action selection via weighted summation.
**Based on**: Rangel (2013) on wanting/liking dissociation; Berridge's incentive salience theory as cited in Rangel, Camerer & Montague (2008); postulates P1, P3, P4.

### Variables
| Symbol | Name | Description | Type |
|--------|------|-------------|------|
| W(s) | Wanting value | Incentive salience of state s, dopamine-mediated | Continuous ∈ [0, W_max] |
| L(s) | Liking value | Hedonic value of state s, opioid-mediated | Continuous ∈ [0, L_max] |
| δ_W | Wanting prediction error | RPE driving wanting update | Continuous |
| δ_L | Liking prediction error | Hedonic surprise driving liking update | Continuous |
| h_t | Hunger level | Internal deprivation state | Continuous ∈ [0, 1] |
| r_t | Reward received | Food reward at time t | Continuous ∈ {0, r_food} |
| Q_total(a) | Combined action value | Wanting + liking-derived action value for action a | Continuous |
| P(a) | Action probability | Probability of selecting action a | Continuous ∈ [0, 1] |

### Parameters
| Symbol | Name | Default | Source |
|--------|------|---------|--------|
| α_W | Wanting learning rate | 0.12 | Faster plasticity for dopamine-mediated learning; retrieved knowledge |
| α_L | Liking learning rate | 0.05 | Slower adaptation for opioid-mediated hedonic signal; retrieved knowledge |
| β | Inverse temperature | 5.0 | Softmax exploration–exploitation tradeoff |
| μ | Hunger–wanting gain | 1.5 | Multiplicative gating of wanting by hunger; Berridge & Robinson (2003) as cited in Rangel (2013) |
| λ | Alliesthesia coefficient | 1.0 | Hunger modulation of liking (pleasantness decreases with satiety); Rangel (2013) |
| w_W | Wanting weight | 0.6 | Relative contribution of wanting to combined value |
| w_L | Liking weight | 0.4 | Relative contribution of liking to combined value; w_W + w_L = 1 |
| r_food | Food reward magnitude | 1.0 | Normalized reward |
| α_h | Hunger increment | 0.02 | Per-step hunger growth |
| γ_sat | Satiation decrement | 0.20 | Hunger reduction upon eating |
| c_step | Movement cost | 0.01 | Energetic cost of movement |
| W_max | Max wanting | 2.0 | Upper bound for wanting values |
| L_max | Max liking | 2.0 | Upper bound for liking values |

### Equations

**Eq. 1 — Wanting prediction error:**
`δ_W = r_t − W(s_t)`
$$\delta_{W} = r_t - W(s_t) \tag{1}$$

**Eq. 2 — Wanting value update:**
`W(s_t) ← clip(W(s_t) + α_W · δ_W, 0, W_max)`
$$W(s_t) \leftarrow \text{clip}\!\Big(W(s_t) + \alpha_W \cdot \delta_W,\; 0,\; W_{\max}\Big) \tag{2}$$

**Eq. 3 — Liking prediction error (hedonic surprise):**
`δ_L = r_t · h_t^λ − L(s_t)`
$$\delta_{L} = r_t \cdot h_t^{\lambda} - L(s_t) \tag{3}$$

The liking target is modulated by hunger via alliesthesia: food is more pleasant when hungry (h_t close to 1) and less pleasant when sated (h_t close to 0). The exponent λ controls the curvature of this modulation.

**Eq. 4 — Liking value update:**
`L(s_t) ← clip(L(s_t) + α_L · δ_L, 0, L_max)`
$$L(s_t) \leftarrow \text{clip}\!\Big(L(s_t) + \alpha_L \cdot \delta_L,\; 0,\; L_{\max}\Big) \tag{4}$$

**Eq. 5 — Hunger dynamics:**
`h_{t+1} = clip(h_t + α_h − γ_sat · ate_t, 0, 1)`
$$h_{t+1} = \text{clip}\!\Big(h_t + \alpha_h - \gamma_{\text{sat}} \cdot \mathbb{1}[\text{ate}_t],\; 0,\; 1\Big) \tag{5}$$

**Eq. 6 — Hunger-modulated wanting contribution:**
`Q_W(a) = μ · h_t · W(s_a)`
$$Q_W(a) = \mu \cdot h_t \cdot W(s_a) \tag{6}$$

**Eq. 7 — Liking contribution (state-dependent hedonic value):**
`Q_L(a) = h_t^λ · L(s_a)`
$$Q_L(a) = h_t^{\lambda} \cdot L(s_a) \tag{7}$$

**Eq. 8 — Combined Pavlovian action value:**
`Q_total(a) = w_W · Q_W(a) + w_L · Q_L(a) − c_step · 𝟙[a ∈ moves]`
$$Q_{\text{total}}(a) = w_W \cdot Q_W(a) + w_L \cdot Q_L(a) - c_{\text{step}} \cdot \mathbb{1}[a \in \text{moves}] \tag{8}$$

**Eq. 9 — Softmax action selection:**
`P(a) = exp(β · Q_total(a)) / Σ_j exp(β · Q_total(j))`
$$P(a) = \frac{\exp\!\big(\beta \cdot Q_{\text{total}}(a)\big)}{\sum_{j} \exp\!\big(\beta \cdot Q_{\text{total}}(j)\big)} \tag{9}$$

### Decision logic

1. **Perceive**: Observe current position s_t, list of visible food positions, whether food is at current cell, current hunger h_t.
2. **Compute wanting contribution**: For each action a, compute Q_W(a) = μ · h_t · W(s_a) via Eq. 6. The wanting channel drives approach proportional to hunger × learned wanting.
3. **Compute liking contribution**: For each action a, compute Q_L(a) = h_t^λ · L(s_a) via Eq. 7. The liking channel drives approach toward states with positive hedonic associations, modulated by alliesthesia.
4. **Combine channels**: Compute Q_total(a) via Eq. 8 for all available actions.
   - If a = eat and food is at s_t: s_a = s_t (no movement cost).
   - If a = eat and no food at s_t: action unavailable (Q_total = −∞).
   - If a is movement to invalid cell: action unavailable (Q_total = −∞).
5. **Select action**: Sample from P(a) via softmax (Eq. 9).
6. **Execute and observe**: Perform action; observe r_t and whether agent ate.
7. **Update wanting**: Compute δ_W (Eq. 1), update W(s_t) (Eq. 2).
8. **Update liking**: Compute δ_L (Eq. 3), update L(s_t) (Eq. 4).
9. **Update hunger**: Update h_{t+1} via Eq. 5.

**Key Pavlovian property**: Wanting and liking are dissociable — an agent can have high wanting (strong approach) with low liking (low hedonic experience), or vice versa. Wanting drives approach vigor while liking tracks hedonic experience. In satiated states (h_t → 0), wanting is suppressed (μ · h_t → 0) even if W(s) remains high, capturing the observation that cue-triggered approach diminishes with satiety (P4). Liking's slower learning rate means hedonic expectations lag behind changes in wanting, matching empirical dissociation.

---

## Formulation 3: ODE-Based Continuous Drive Dynamics with Deterministic Threshold Policy
**Approach**: Continuous-time ordinary differential equations governing hunger drive and Pavlovian associative strength, with a deterministic threshold-based action policy (approach when effective drive exceeds threshold).
**Based on**: Rangel (2013) on homeostatic modulation of Pavlovian value; postulates P1, P2, P4; continuous-time dynamical systems treatment of drive theory.

### Variables
| Symbol | Name | Description | Type |
|--------|------|-------------|------|
| H(t) | Hunger drive | Continuous internal energy-deficit signal | Continuous ∈ [0, 1] |
| V(s, t) | Associative strength | Learned CS–US association for state s at time t | Continuous ∈ [0, V_max] |
| E(t) | Effective drive | Combined motivational signal = hunger × associative strength | Continuous ∈ [0, E_max] |
| r_t | Reward received | Food reward at time t | Continuous ∈ {0, r_food} |
| d_min | Nearest food distance | Manhattan distance to closest visible food source | Discrete ≥ 0 |

### Parameters
| Symbol | Name | Default | Source |
|--------|------|---------|--------|
| α_V | Associative learning rate | 0.10 | Within Rescorla–Wagner validated range; Rangel (2013) |
| c_H | Hunger growth rate | 0.02 | Metabolic hunger accrual per time step |
| k_sat | Satiation rate | 0.25 | Hunger reduction rate upon food intake |
| μ | Drive coupling constant | 1.5 | Hunger × value multiplicative gain; Berridge as cited in Rangel (2013) |
| θ_approach | Approach threshold | 0.3 | Effective drive above which approach is triggered; calibrated |
| θ_eat | Eat threshold | 0.5 | Effective drive above which eating is triggered when food available; calibrated |
| η | Extinction decay rate | 0.01 | Rate of V(s) decay during unreinforced CS presentations |
| r_food | Food reward magnitude | 1.0 | Normalized reward |
| V_max | Maximum associative strength | 2.0 | Asymptote of conditioning |
| dt | Integration time step | 1.0 | Discrete approximation of continuous dynamics (1 simulation tick) |

### Equations

**Eq. 1 — Hunger drive dynamics (ODE):**
`dH/dt = c_H · (1 − H) − k_sat · intake(t)`
$$\frac{dH}{dt} = c_H \cdot (1 - H) - k_{\text{sat}} \cdot \text{intake}(t) \tag{1}$$

Hunger grows logistically toward 1 when not eating and drops sharply upon food intake. The (1 − H) term creates a natural ceiling at H = 1.

**Eq. 1a — Discrete Euler approximation:**
`H_{t+1} = H_t + dt · [c_H · (1 − H_t) − k_sat · ate_t]`
$$H_{t+1} = H_t + dt \cdot \Big[c_H \cdot (1 - H_t) - k_{\text{sat}} \cdot \mathbb{1}[\text{ate}_t]\Big] \tag{1a}$$

**Eq. 2 — Associative strength dynamics (ODE):**
`dV(s)/dt = α_V · (r(t) − V(s)) · 𝟙[at state s] − η · V(s) · 𝟙[no reward at s]`
$$\frac{dV(s)}{dt} = \alpha_V \cdot \big(r(t) - V(s)\big) \cdot \mathbb{1}[\text{at } s] - \eta \cdot V(s) \cdot \mathbb{1}[\text{no reward at } s] \tag{2}$$

When the agent occupies state s and receives reward, V(s) is driven toward r(t). When the agent occupies s and receives no reward, V(s) decays (extinction). When the agent is elsewhere, V(s) is unchanged.

**Eq. 2a — Discrete update:**
`V(s_t) ← clip(V(s_t) + α_V · (r_t − V(s_t)) − η · V(s_t) · (1 − 𝟙[r_t > 0]), 0, V_max)`
$$V(s_t) \leftarrow \text{clip}\!\Big(V(s_t) + \alpha_V \cdot (r_t - V(s_t)) - \eta \cdot V(s_t) \cdot \mathbb{1}[r_t = 0],\; 0,\; V_{\max}\Big) \tag{2a}$$

**Eq. 3 — Effective motivational drive:**
`E(t) = μ · H(t) · V_perceived(t)`
$$E(t) = \mu \cdot H(t) \cdot V_{\text{perceived}}(t) \tag{3}$$

where V_perceived(t) is the maximum learned Pavlovian value among all visible cells (perceived food cues):

`V_perceived(t) = max_{s ∈ visible} V(s)`
$$V_{\text{perceived}}(t) = \max_{s \in \text{visible}} V(s) \tag{3a}$$

**Eq. 4 — Approach direction (gradient ascent on V):**
`a* = argmax_{a ∈ moves} V(s_a)`
$$a^* = \arg\max_{a \in \text{moves}} V(s_a) \tag{4}$$

The Pavlovian approach is a stereotyped movement toward the highest-valued neighboring cell — a gradient ascent on the cached value landscape. This implements the "prepared behavior" constraint (P3): the agent cannot learn arbitrary action mappings, only approach the most salient cue.

### Decision logic

1. **Perceive**: Observe current position s_t, visible cells and their food status, nearest food distance d_min, whether food is at current cell, current hunger H_t.
2. **Compute effective drive**: Evaluate E(t) = μ · H_t · V_perceived(t) via Eq. 3.
3. **Decision rules** (deterministic, threshold-based):
   - **Rule A — Eat**: IF food is present at s_t AND E(t) ≥ θ_eat → action = **eat**.
   - **Rule B — Approach**: IF E(t) ≥ θ_approach AND NOT (Rule A triggered) → action = **move toward argmax V(s_a)** (Eq. 4). If multiple neighbors are tied, break ties randomly.
   - **Rule C — Stay**: IF E(t) < θ_approach → action = **stay**. (Insufficient motivational drive to initiate approach.)
   - **Rule D — Eat override**: IF food is present at s_t AND H_t > 0.8 → action = **eat** regardless of E(t). (Very high hunger triggers consummatory response even with weak CS association, reflecting unconditioned eating; P1.)
4. **Execute action**: Perform selected action; observe r_t and whether agent ate.
5. **Update associative strength**: Apply Eq. 2a to V(s_t).
6. **Update hunger drive**: Apply Eq. 1a.

**Key Pavlovian properties**: 
- The approach direction is entirely determined by the value gradient (Eq. 4), not by learned action–outcome mappings — this is model-free, stimulus-bound (P3).
- The threshold mechanism produces binary approach/no-approach behavior that transitions sharply as hunger or CS value change, capturing the observation that Pavlovian responses are "released" rather than graded (P1).
- Explicit extinction dynamics (η term in Eq. 2) allow V(s) to decay when CS is presented without food, but slowly — capturing outcome insensitivity of Pavlovian conditioning.
- The ODE framework naturally models continuous temporal dynamics (time since last meal affecting hunger, gradual conditioning over trials).

---

## Cross-formulation comparison

| Aspect | Formulation 1: Rescorla–Wagner Cached-Value | Formulation 2: Incentive Salience Dual-Process | Formulation 3: ODE Drive Dynamics + Threshold |
|--------|----------------------------------------------|------------------------------------------------|-----------------------------------------------|
| Framework | Algebraic (discrete update rule + softmax) | Algebraic dual-channel (two learning rules + weighted softmax) | ODE-based continuous dynamics + deterministic threshold policy |
| Key variables | V(s), δ_t, h_t | W(s), L(s), h_t | H(t), V(s,t), E(t) |
| Core equation | V(s) ← V(s) + α·(r − V(s)) (Eq. 2) | Q_total = w_W·μ·h·W(s_a) + w_L·h^λ·L(s_a) (Eq. 8) | dH/dt = c_H·(1−H) − k_sat·intake (Eq. 1) |
| Decision mechanism | Stochastic softmax over hunger-modulated state values | Stochastic softmax over weighted wanting + liking channels | Deterministic threshold on effective drive E(t); gradient ascent on V landscape |
| Hunger modulation | Multiplicative gain μ·h on V(s) | Multiplicative gain μ·h on wanting; power-law h^λ on liking (alliesthesia) | Continuous ODE with logistic growth; multiplicative coupling in effective drive |
| Number of learned value maps | 1 (V) | 2 (W, L with different learning rates) | 1 (V) with explicit extinction decay term |
| Captures wanting–liking dissociation | No (single value signal) | Yes (core feature: W and L are separate) | No (single associative strength) |
| Action selection noise | Stochastic (softmax β) | Stochastic (softmax β) | Deterministic (threshold-based, no randomness except tie-breaking) |
| Extinction dynamics | Implicit (δ < 0 drives V down) | Implicit in both channels (δ_W, δ_L < 0) | Explicit decay term η·V (continuous exponential extinction) |
| Strengths | Simplest; directly implements Rescorla–Wagner; easy to calibrate; well-studied | Captures empirical wanting/liking dissociation; richer behavioral repertoire (e.g., high wanting + low liking); differential learning rates match neuropharmacological data | Continuous dynamics natural for modeling temporal processes (hunger accumulation, gradual conditioning); deterministic policy is computationally cheap; explicit extinction rate |
| Limitations | Cannot distinguish wanting from liking; single learning rate oversimplifies | More parameters to calibrate; dual channels add complexity without always being needed; still uses discrete approximation | Threshold-based policy loses graded probabilistic behavior; less robust to noise; binary approach/no-approach may be too rigid for some environments |
