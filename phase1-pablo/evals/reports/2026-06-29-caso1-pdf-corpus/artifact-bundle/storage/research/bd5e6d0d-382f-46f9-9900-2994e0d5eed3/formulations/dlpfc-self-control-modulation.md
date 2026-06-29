# dlPFC Self-Control Modulation — Mathematical Formulations

## Formulation 1: Attribute-Reweighting Algebraic Model
**Approach**: Algebraic weighted-sum valuation where dlPFC dynamically modulates attribute weights, with softmax action selection over composite chosen values.
**Based on**: Rangel (2013) postulates P1, P3; Rangel et al. (2008) value-based decision framework.

### Variables
| Symbol | Name | Description | Type |
|--------|------|-------------|------|
| $\text{CCV}(a)$ | Composite Chosen Value | Weighted sum of attribute values for action $a$ | Continuous, ℝ |
| $w_h(t)$ | Health attribute weight | Current weight of abstract/delayed attribute in vmPFC value computation | Continuous, [0, 1] |
| $w_\tau(t)$ | Taste attribute weight | Current weight of immediate/hedonic attribute in vmPFC value computation | Continuous, [0, 1] |
| $C(t)$ | dlPFC coupling strength | Degree of top-down modulation exerted by dlPFC on vmPFC | Continuous, [0, 1] |
| $K(t)$ | Conflict signal | Discrepancy between immediate-best and long-term-best action values | Continuous, [0, ∞) |
| $G(t)$ | Goal activation | Strength of active long-term goal representation | Continuous, [0, 1] |
| $D(t)$ | Depletion level | Current depletion of dlPFC resources (0 = fresh, 1 = exhausted) | Continuous, [0, 1] |
| $P(a)$ | Action probability | Probability of selecting action $a$ | Continuous, [0, 1] |

### Parameters
| Symbol | Name | Default | Source |
|--------|------|---------|--------|
| $w_{h,0}$ | Baseline health weight | 0.2 | Rangel (2013): vmPFC encodes primarily taste unless dlPFC engaged |
| $w_{\tau,0}$ | Baseline taste weight | 0.8 | Rangel (2013): hedonic attribute dominates without top-down control |
| $\gamma_C$ | Coupling gain on health weight | 0.6 | Derived from P1: dlPFC amplifies abstract attribute weight |
| $\beta$ | Softmax inverse temperature | 5.0 | Standard value-based decision-making literature; knowledge backbone |
| $\alpha_D$ | Depletion rate per control event | 0.08 | Approximation from cognitive depletion assumption |
| $\beta_D$ | Passive recovery rate | 0.04 | Knowledge backbone: recovery ≈ half depletion speed |
| $\lambda_K$ | Conflict sensitivity for dlPFC engagement | 1.5 | Derived from P4: conflict triggers dlPFC |
| $\eta_G$ | Goal decay rate | 0.05 | Assumption: goal activation decays without reinforcement |
| $\text{Health}(o)$ | Health rating of resource $o$ | varies per resource | Rangel (2013): subjective rating scale |
| $\text{Taste}(o)$ | Taste rating of resource $o$ | varies per resource | Rangel (2013): subjective rating scale |

### Equations

**Eq. 1 — Conflict signal:**
`K(t) = |max_a V_taste(a) - max_a V_health(a)| (action-level disagreement)`
$$K(t) = \left| \arg\max_a \text{Taste}(a) \neq \arg\max_a \text{Health}(a) \right| \cdot \left| \max_a \text{Taste}(a) - \text{Taste}(a^*_h) \right| \tag{1}$$

where $a^*_h = \arg\max_a \text{Health}(a)$. In the grid agent, if the tastiest nearby resource differs from the healthiest, $K(t)$ equals the taste advantage of the temptation; otherwise $K(t) = 0$.

**Eq. 2 — dlPFC coupling strength:**
`C(t) = sigmoid(λ_K · K(t)) · G(t) · (1 − D(t))`
$$C(t) = \sigma\!\bigl(\lambda_K \cdot K(t)\bigr) \cdot G(t) \cdot \bigl(1 - D(t)\bigr), \qquad \sigma(x) = \frac{1}{1 + e^{-x}} \tag{2}$$

**Eq. 3 — Attribute weight modulation:**
`w_h(t) = w_h0 + γ_C · C(t);  w_τ(t) = 1 − w_h(t)`
$$w_h(t) = w_{h,0} + \gamma_C \cdot C(t), \qquad w_\tau(t) = 1 - w_h(t) \tag{3}$$

**Eq. 4 — Composite Chosen Value:**
`CCV(a) = w_τ(t) · Taste(a) + w_h(t) · Health(a)`
$$\text{CCV}(a) = w_\tau(t) \cdot \text{Taste}(a) + w_h(t) \cdot \text{Health}(a) \tag{4}$$

**Eq. 5 — Softmax action selection:**
`P(a) = exp(β · CCV(a)) / Σ_j exp(β · CCV(j))`
$$P(a) = \frac{\exp\bigl(\beta \cdot \text{CCV}(a)\bigr)}{\sum_j \exp\bigl(\beta \cdot \text{CCV}(j)\bigr)} \tag{5}$$

**Eq. 6 — Depletion dynamics (discrete update):**
`D(t+1) = clamp(D(t) + α_D · C(t) − β_D · (1 − C(t)), 0, 1)`
$$D(t{+}1) = \text{clamp}\!\Bigl(D(t) + \alpha_D \cdot C(t) - \beta_D \cdot \bigl(1 - C(t)\bigr),\; 0,\; 1\Bigr) \tag{6}$$

**Eq. 7 — Goal activation decay/boost:**
`G(t+1) = G(t) · (1 − η_G) + boost(t)`
$$G(t{+}1) = G(t) \cdot (1 - \eta_G) + \text{boost}(t) \tag{7}$$

where $\text{boost}(t) = 0.3$ if the agent successfully chose the healthy option on trial $t$ (positive reinforcement of goal), 0 otherwise.

### Decision logic

1. **Perceive** the agent's grid position, list of nearby resources with their `Taste(o)` and `Health(o)` ratings, and whether a resource is at the current cell.
2. **Compute conflict** $K(t)$ using Eq. 1: compare the tastiest and healthiest options among visible resources.
3. **Compute dlPFC coupling** $C(t)$ using Eq. 2, given current goal activation $G(t)$ and depletion $D(t)$.
4. **Compute attribute weights** $w_h(t), w_\tau(t)$ using Eq. 3.
5. **Compute CCV** for each candidate action using Eq. 4:
   - For `eat` (if resource at current cell): CCV uses the resource's attributes.
   - For `move_up/down/left/right`: CCV uses the attributes of the best resource reachable one step in that direction (discounted by distance = 0.9), or 0 if no resource is visible in that direction.
   - For `stay`: CCV = 0 (no value change).
6. **Select action** by sampling from the softmax distribution $P(a)$ (Eq. 5).
7. **Update** depletion $D(t+1)$ via Eq. 6 and goal activation $G(t+1)$ via Eq. 7.

---

## Formulation 2: Executive Resource ODE with Dual-Value Arbitration
**Approach**: Continuous-time ODE governing executive (dlPFC) resource dynamics, with a dual-system arbitration weight that determines the mixture of impulsive vs. goal-directed action values, then greedy action selection with stochastic override.
**Based on**: Rangel et al. (2008) three-controller architecture; Rangel (2013) postulates P2, P4; knowledge backbone (dE/dt depletion–recovery ODE pattern).

### Variables
| Symbol | Name | Description | Type |
|--------|------|-------------|------|
| $E(t)$ | Executive capacity | Depletable dlPFC resource level (1 = full, 0 = exhausted) | Continuous, [0, 1] |
| $V_I(a,s)$ | Impulsive value | Value of action $a$ in state $s$ from Pavlovian/habitual controller (taste-driven) | Continuous, ℝ |
| $V_G(a,s)$ | Goal-directed value | Value of action $a$ in state $s$ from model-based controller (health-integrated) | Continuous, ℝ |
| $V(a,s)$ | Integrated value | Arbitrated mixture of impulsive and goal-directed values | Continuous, ℝ |
| $\omega(t)$ | Arbitration weight | Proportion of goal-directed influence (0 = fully impulsive, 1 = fully goal-directed) | Continuous, [0, 1] |
| $\text{ctrl}(t)$ | Control exertion flag | Whether dlPFC is actively overriding the impulsive system this step | Binary, {0, 1} |

### Parameters
| Symbol | Name | Default | Source |
|--------|------|---------|--------|
| $\alpha_E$ | Depletion rate | 0.08 | Knowledge backbone; cognitive depletion assumption |
| $\beta_E$ | Recovery rate | 0.04 | Knowledge backbone: ≈ half depletion rate |
| $\theta$ | Override threshold | 0.3 | Derived from P4: minimum E needed for conflict override |
| $\epsilon$ | Stochastic lapse rate | 0.1 | Exploration / noise in motor execution |
| $\alpha_Q$ | Learning rate for habit values | 0.1 | Standard RL literature |
| $\gamma$ | Temporal discount for approach values | 0.9 | Standard RL temporal discounting |
| $w_h^G$ | Health weight in goal-directed value | 0.6 | Rangel (2013): goal-directed system weights health when engaged |
| $w_\tau^G$ | Taste weight in goal-directed value | 0.4 | Complement of $w_h^G$ |

### Equations

**Eq. 1 — Executive capacity dynamics (Euler-discretized ODE):**
`dE/dt = β_E · (1 − E) − α_E · ctrl(t)`
$$\frac{dE}{dt} = \beta_E \cdot (1 - E) - \alpha_E \cdot \text{ctrl}(t) \tag{1}$$

Discrete update: $E(t{+}1) = \text{clamp}\bigl(E(t) + \beta_E \cdot (1 - E(t)) - \alpha_E \cdot \text{ctrl}(t),\; 0,\; 1\bigr)$

**Eq. 2 — Impulsive action value (habit/Pavlovian):**
`V_I(a, s) = Taste(resource toward a) · proximity_discount`
$$V_I(a, s) = \text{Taste}\!\bigl(\text{resource}(a)\bigr) \cdot \gamma^{d(a)} \tag{2}$$

where $d(a)$ is the Manhattan distance to the targeted resource via action $a$.

**Eq. 3 — Goal-directed action value:**
`V_G(a, s) = w_τ^G · Taste(resource toward a) + w_h^G · Health(resource toward a)`
$$V_G(a, s) = w_\tau^G \cdot \text{Taste}\!\bigl(\text{resource}(a)\bigr) + w_h^G \cdot \text{Health}\!\bigl(\text{resource}(a)\bigr) \tag{3}$$

discounted by $\gamma^{d(a)}$ as in Eq. 2.

**Eq. 4 — Arbitration weight (sigmoid of executive capacity):**
`ω(t) = E(t)^2`
$$\omega(t) = E(t)^2 \tag{4}$$

The squaring ensures that moderate depletion has only small effects but severe depletion collapses self-control rapidly (consistent with the nonlinear depletion effects described in the assumptions).

**Eq. 5 — Integrated value:**
`V(a, s) = ω(t) · V_G(a, s) + (1 − ω(t)) · V_I(a, s)`
$$V(a, s) = \omega(t) \cdot V_G(a, s) + \bigl(1 - \omega(t)\bigr) \cdot V_I(a, s) \tag{5}$$

**Eq. 6 — Control exertion detection:**
`ctrl(t) = 1 if argmax V_G ≠ argmax V_I, else 0`
$$\text{ctrl}(t) = \mathbb{1}\!\left[\arg\max_a V_G(a,s) \neq \arg\max_a V_I(a,s)\right] \tag{6}$$

**Eq. 7 — Habit value update (model-free TD):**
`V_I(a,s) ← V_I(a,s) + α_Q · (r_received − V_I(a,s))`
$$V_I(a,s) \leftarrow V_I(a,s) + \alpha_Q \cdot \bigl(r_{\text{received}} - V_I(a,s)\bigr) \tag{7}$$

where $r_{\text{received}} = \text{Taste}(\text{eaten resource})$ if the agent ate, else 0.

### Decision logic

1. **Perceive** grid position, nearby resources (with Taste, Health ratings), and whether the agent ate last step.
2. **Update** habit values $V_I$ using Eq. 7 if the agent ate on the previous step.
3. **Compute** impulsive values $V_I(a,s)$ for all actions using Eq. 2 (or cached habit values if available).
4. **Compute** goal-directed values $V_G(a,s)$ for all actions using Eq. 3.
5. **Detect conflict** via Eq. 6: if the impulsive-best action differs from the goal-directed-best action, set $\text{ctrl}(t) = 1$.
6. **Update** executive capacity $E(t)$ via Eq. 1 (depletion if ctrl = 1, recovery if ctrl = 0).
7. **Compute** arbitration weight $\omega(t)$ via Eq. 4.
8. **Compute** integrated values $V(a,s)$ via Eq. 5.
9. **Select action**: with probability $(1 - \epsilon)$, choose $a^* = \arg\max_a V(a,s)$; with probability $\epsilon$, choose a random action (ε-greedy; accounts for motor noise and lapses).
10. If $E(t) < \theta$ and $\text{ctrl}(t) = 1$: the agent cannot override the impulse; forced to select $\arg\max_a V_I(a,s)$ regardless of step 9 (complete self-control failure, per P3).

---

## Formulation 3: Bayesian Conflict-Gated Stochastic Control
**Approach**: Probabilistic/Bayesian framework where the agent maintains a posterior belief over whether self-control is needed (conflict state), uses this to gate dlPFC engagement, and selects actions via a mixture policy whose mixing probability is updated via Bayesian inference.
**Based on**: Rangel et al. (2008) multi-system framework; Rangel (2013) postulates P1, P4 (conflict-triggered engagement); dual-system arbitration knowledge backbone pattern.

### Variables
| Symbol | Name | Description | Type |
|--------|------|-------------|------|
| $b(t)$ | Conflict belief | Posterior probability that the current situation involves a goal–impulse conflict | Continuous, [0, 1] |
| $\pi_I(a \mid s)$ | Impulsive policy | Probability of action $a$ under the Pavlovian/habitual controller | Continuous, [0, 1] |
| $\pi_G(a \mid s)$ | Goal-directed policy | Probability of action $a$ under the goal-directed controller | Continuous, [0, 1] |
| $\pi(a \mid s)$ | Mixture policy | Final action probability as mixture of impulsive and goal-directed policies | Continuous, [0, 1] |
| $E(t)$ | Executive capacity | dlPFC resource level | Continuous, [0, 1] |
| $\ell(t)$ | Conflict likelihood | Likelihood of observing current perceptual evidence given conflict state | Continuous, [0, 1] |
| $r_\text{eff}(t)$ | Effective reward | Reward signal combining immediate and long-term components | Continuous, ℝ |

### Parameters
| Symbol | Name | Default | Source |
|--------|------|---------|--------|
| $b_0$ | Prior conflict probability | 0.3 | Calibrated: ~30% of choices involve goal–impulse disagreement (Rangel, 2013) |
| $\beta_I$ | Impulsive softmax temperature | 8.0 | Higher temperature = more exploitation of taste |
| $\beta_G$ | Goal-directed softmax temperature | 4.0 | Lower temperature = more exploratory / prudent |
| $\alpha_E$ | Executive depletion rate | 0.06 | Knowledge backbone; slightly lower for probabilistic gating |
| $\beta_E$ | Executive recovery rate | 0.04 | Knowledge backbone |
| $\kappa$ | Control cost per unit engagement | 0.02 | Rangel (2013): dlPFC engagement is metabolically costly |
| $\phi$ | Bayesian update rate (learning rate analog) | 0.3 | Moderate integration of new evidence |
| $w_h$ | Health weight in goal-directed reward | 0.5 | Rangel (2013) |
| $w_\tau$ | Taste weight in impulsive reward | 1.0 | Pavlovian system responds only to hedonic attribute |

### Equations

**Eq. 1 — Impulsive policy (taste-only softmax):**
`π_I(a|s) = exp(β_I · Taste(a)) / Σ_j exp(β_I · Taste(j))`
$$\pi_I(a \mid s) = \frac{\exp\bigl(\beta_I \cdot \text{Taste}(a) \cdot \gamma^{d(a)}\bigr)}{\sum_j \exp\bigl(\beta_I \cdot \text{Taste}(j) \cdot \gamma^{d(j)}\bigr)} \tag{1}$$

**Eq. 2 — Goal-directed policy (health+taste softmax):**
`π_G(a|s) = exp(β_G · [w_τ·Taste(a) + w_h·Health(a)]) / Σ_j exp(β_G · [w_τ·Taste(j) + w_h·Health(j)])`
$$\pi_G(a \mid s) = \frac{\exp\Bigl(\beta_G \cdot \bigl[w_\tau \cdot \text{Taste}(a) + w_h \cdot \text{Health}(a)\bigr] \cdot \gamma^{d(a)}\Bigr)}{\sum_j \exp\Bigl(\beta_G \cdot \bigl[w_\tau \cdot \text{Taste}(j) + w_h \cdot \text{Health}(j)\bigr] \cdot \gamma^{d(j)}\Bigr)} \tag{2}$$

**Eq. 3 — Conflict likelihood:**
`ℓ(t) = |argmax π_I − argmax π_G| > 0 ? 0.9 : 0.1`
$$\ell(t) = \begin{cases} 0.9 & \text{if } \arg\max_a \pi_I(a|s) \neq \arg\max_a \pi_G(a|s) \\ 0.1 & \text{otherwise} \end{cases} \tag{3}$$

**Eq. 4 — Bayesian conflict belief update:**
`b(t) = [ℓ(t) · b(t−1)] / [ℓ(t) · b(t−1) + (1 − ℓ(t)) · (1 − b(t−1))]`
$$b(t) = \frac{\ell(t) \cdot b(t{-}1)}{\ell(t) \cdot b(t{-}1) + \bigl(1 - \ell(t)\bigr) \cdot \bigl(1 - b(t{-}1)\bigr)} \tag{4}$$

Smoothed with learning rate: $b(t) \leftarrow (1 - \phi) \cdot b(t{-}1) + \phi \cdot b_{\text{Bayes}}(t)$

**Eq. 5 — Effective engagement probability (gated by capacity):**
`p_engage(t) = b(t) · E(t)`
$$p_{\text{engage}}(t) = b(t) \cdot E(t) \tag{5}$$

**Eq. 6 — Mixture policy:**
`π(a|s) = p_engage(t) · π_G(a|s) + (1 − p_engage(t)) · π_I(a|s)`
$$\pi(a \mid s) = p_{\text{engage}}(t) \cdot \pi_G(a \mid s) + \bigl(1 - p_{\text{engage}}(t)\bigr) \cdot \pi_I(a \mid s) \tag{6}$$

**Eq. 7 — Executive capacity update:**
`E(t+1) = clamp(E(t) + β_E · (1 − E(t)) − α_E · p_engage(t), 0, 1)`
$$E(t{+}1) = \text{clamp}\!\Bigl(E(t) + \beta_E \cdot (1 - E(t)) - \alpha_E \cdot p_{\text{engage}}(t),\; 0,\; 1\Bigr) \tag{7}$$

**Eq. 8 — Effective reward (for belief updating from outcomes):**
`r_eff(t) = Taste(eaten) + w_h · Health(eaten) − κ · p_engage(t)`
$$r_{\text{eff}}(t) = \text{Taste}(\text{eaten}) + w_h \cdot \text{Health}(\text{eaten}) - \kappa \cdot p_{\text{engage}}(t) \tag{8}$$

### Decision logic

1. **Perceive** grid position, nearby resources (Taste, Health ratings), and previous reward.
2. **Compute impulsive policy** $\pi_I(a|s)$ via Eq. 1 for all candidate actions: move toward tastiest resource, eat if at resource, or stay.
3. **Compute goal-directed policy** $\pi_G(a|s)$ via Eq. 2, incorporating both taste and health.
4. **Assess conflict** by computing the conflict likelihood $\ell(t)$ via Eq. 3.
5. **Update conflict belief** $b(t)$ via Bayesian update (Eq. 4), smoothed with learning rate $\phi$.
6. **Compute engagement probability** $p_{\text{engage}}(t)$ via Eq. 5: the agent probabilistically recruits the goal-directed controller when conflict is believed to be present AND executive resources are available.
7. **Form mixture policy** $\pi(a|s)$ via Eq. 6.
8. **Sample action** $a \sim \pi(a|s)$.
9. **Update** executive capacity $E(t+1)$ via Eq. 7: engagement drains resources proportionally.
10. **After outcome**: compute $r_{\text{eff}}(t)$ via Eq. 8; use reward prediction error to mildly adjust $b_0$ prior toward environments that are more/less conflict-prone (meta-learning over episodes).

---

## Cross-formulation comparison

| Aspect | Formulation 1: Attribute-Reweighting Algebraic | Formulation 2: Executive Resource ODE Dual-Value | Formulation 3: Bayesian Conflict-Gated Stochastic |
|--------|-----------------------------------------------|------------------------------------------------|--------------------------------------------------|
| Framework | Algebraic (weighted-sum + softmax) | ODE-based resource dynamics + ε-greedy | Probabilistic (Bayesian belief update + mixture policy) |
| Key variables | $w_h(t)$, $C(t)$, $\text{CCV}(a)$ | $E(t)$, $\omega(t)$, $V(a,s)$ | $b(t)$, $p_{\text{engage}}(t)$, $\pi(a \mid s)$ |
| Core equation | $\text{CCV}(a) = w_\tau \cdot \text{Taste} + w_h \cdot \text{Health}$ (Eq. 4) | $\frac{dE}{dt} = \beta_E(1-E) - \alpha_E \cdot \text{ctrl}$ (Eq. 1) | $\pi(a \mid s) = p_{\text{engage}} \cdot \pi_G + (1-p_{\text{engage}}) \cdot \pi_I$ (Eq. 6) |
| Decision mechanism | Softmax over modulated composite values | ε-greedy over arbitrated integrated value; hard failure below threshold | Sampling from a Bayesian-gated mixture of two stochastic policies |
| How dlPFC modulates choice | Continuously shifts attribute weights within a single value function | Controls an arbitration weight between two separate value systems | Determines the probability of recruiting the goal-directed policy |
| Self-control failure mode | Low $C(t)$→ health weight collapses to baseline; taste dominates CCV | $E(t) < \theta$→ forced impulsive action; no override possible | Low $b(t) \cdot E(t)$→ mixture dominated by impulsive policy; gradual degradation |
| Strengths | Directly models the attribute-reweighting mechanism from Rangel (2013); interpretable weights map to fMRI PPI measures; goal reinforcement loop | Rich depletion dynamics with asymptotic recovery; hard self-control failure captures "ego depletion" threshold effects; habit learning via TD | Principled uncertainty handling; graceful degradation (no hard threshold); conflict belief naturally adapts to environment statistics |
| Limitations | No learning of habit values; attribute weights do not interact nonlinearly; depletion model is simple | Binary conflict detection (no graded conflict); ε-greedy loses nuance of value differences; no Bayesian uncertainty | More complex; conflict likelihood is a discretized heuristic; may over-commit to conflict belief in stable environments |
