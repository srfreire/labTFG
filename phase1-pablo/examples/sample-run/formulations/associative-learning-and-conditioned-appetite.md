# Associative Learning and Conditioned Appetite — Mathematical Formulations

## Formulation 1: Rescorla–Wagner Prediction-Error Agent
**Approach**: Discrete trial-by-trial algebraic update of associative strengths with softmax action selection over cue-driven appetitive values.
**Based on**: Rescorla & Wagner (1972); postulates P1, P2, P3, P5

### Variables
| Symbol | Name | Description | Type |
|--------|------|-------------|------|
| $V_{ij}$ | Associative strength | Learned associative weight from cue $i$ (grid feature at a location) to outcome $j$ (food/no-food) | State (internal, real) |
| $\delta$ | Prediction error | Discrepancy between actual outcome $\lambda$ and summed prediction $\hat{V}$ | Computed signal |
| $\hat{V}(s)$ | Predicted appetitive value at location $s$ | $\sum_i V_{i,\text{food}}$ for all cues $i$ present at location $s$ | Computed |
| $\lambda$ | Outcome magnitude | 1 if food is consumed (US present), 0 otherwise | Observation |
| $H$ | Hunger level | Internal drive state representing caloric deficit; decays after eating, rises over time | State (internal, real ∈ [0,1]) |
| $p(a)$ | Action probability | Probability of selecting action $a$ given current appetitive landscape | Computed |

### Parameters
| Symbol | Name | Default | Source |
|--------|------|---------|--------|
| $\alpha$ | CS salience (learning rate for cues) | 0.15 | Rescorla & Wagner (1972); typical range 0.05–0.30 |
| $\beta^+$ | US learning rate (reward present) | 0.20 | Rescorla & Wagner (1972) |
| $\beta^-$ | US learning rate (reward absent / extinction) | 0.10 | Rescorla & Wagner (1972); extinction is typically slower |
| $\tau$ | Softmax temperature | 0.3 | Free parameter; controls exploration |
| $\kappa$ | Hunger recovery rate | 0.05 per step | Derived from postulate P6 |
| $\phi$ | Hunger modulation exponent | 1.5 | Researchgate (2017); motivational gating of δ |
| $\eta_{\text{sat}}$ | Satiation decrement per meal | 0.4 | Normalised assumption |

### Equations

**Eq. 1 — Prediction error (per trial/step when outcome observed):**
$$
\delta = H^{\phi} \cdot \lambda - \hat{V}(s) \quad \text{where } \hat{V}(s) = \sum_{i \in \text{cues}(s)} V_{i,\text{food}} \tag{1}
$$

**Eq. 2 — Associative strength update (Rescorla–Wagner rule, motivationally gated):**
$$
\Delta V_{i,\text{food}} = \alpha \cdot \beta_{\pm} \cdot \delta, \quad \beta_{\pm} = \begin{cases} \beta^+ & \text{if } \lambda = 1 \\ \beta^- & \text{if } \lambda = 0 \end{cases} \tag{2}
$$

**Eq. 3 — Hunger dynamics:**
$$
H(t+1) = \min\!\Big(1,\; H(t) + \kappa - \eta_{\text{sat}} \cdot \mathbb{1}[\text{ate at } t]\Big) \tag{3}
$$

**Eq. 4 — Appetitive value of a neighbouring location $s'$:**
$$
Q(s') = H(t)^{\phi} \cdot \hat{V}(s') \tag{4}
$$

**Eq. 5 — Softmax action selection:**
$$
p(a) = \frac{\exp\!\big(Q(s'_a) / \tau\big)}{\sum_{a'} \exp\!\big(Q(s'_{a'}) / \tau\big)} \tag{5}
$$

### Decision logic

1. **Perceive** current position, list of cues at the current cell and each adjacent cell, and whether food is present at the current cell.
2. **Compute** $\hat{V}(s')$ for every reachable cell $s'$ (the 4 neighbours + current cell) using Eq. 1's inner sum.
3. **Compute** appetitive action-values $Q(s')$ for each candidate action using Eq. 4. For the "eat" action: $Q_{\text{eat}} = H(t)^{\phi} \cdot \hat{V}(s_{\text{current}})$ **only if food is perceived at the current cell**; otherwise $Q_{\text{eat}} = -\infty$.
4. **Select action** by sampling from the softmax distribution over $Q$ values (Eq. 5).
5. **After action execution**, observe outcome $\lambda$ (1 if ate, else 0).
6. **Update** associative strengths for all cues present at the cell where outcome was observed using Eq. 2 with prediction error from Eq. 1.
7. **Update** hunger via Eq. 3.

---

## Formulation 2: Temporal-Difference (TD) Learning Agent with Eligibility Traces
**Approach**: Multi-step temporal-difference reinforcement learning (TD(λ)) with continuous value estimation over grid states, modelling the temporal transfer of dopamine-like prediction-error signals from US time to CS time.
**Based on**: Sutton & Barto (1998); Schultz et al. (Frontiers in Neuroscience, 2023); postulates P2, P4, P6, P7

### Variables
| Symbol | Name | Description | Type |
|--------|------|-------------|------|
| $V(s)$ | State value | Expected discounted future reward from state (grid cell) $s$ | State (internal, real) |
| $\delta(t)$ | TD error | Temporal-difference reward prediction error at step $t$ | Computed signal |
| $e(s)$ | Eligibility trace | Decaying memory trace for state $s$ visited recently; allows credit assignment back to the CS | State (internal, real ≥ 0) |
| $r(t)$ | Reward | Immediate reward at step $t$; driven by eating food | Observation |
| $H(t)$ | Hunger | Internal drive / motivational state | State (internal, real ∈ [0,1]) |
| $\pi(a|s)$ | Policy | Action probabilities given state $s$ | Computed |

### Parameters
| Symbol | Name | Default | Source |
|--------|------|---------|--------|
| $\gamma$ | Temporal discount factor | 0.90 | Sutton & Barto (1998); models delay-of-gratification |
| $\alpha_{\text{TD}}$ | TD learning rate | 0.10 | Standard RL; Schultz et al. implicitly assume moderate rates |
| $\lambda_{\text{trace}}$ | Eligibility trace decay | 0.70 | Sutton & Barto (1998); λ in TD(λ) |
| $\tau$ | Softmax temperature | 0.25 | Free parameter |
| $\kappa$ | Hunger recovery rate | 0.05 | Same as Formulation 1 |
| $\phi$ | Hunger modulation exponent | 1.5 | Researchgate (2017) |
| $\eta_{\text{sat}}$ | Satiation per meal | 0.4 | Normalised assumption |
| $\epsilon$ | Exploration probability (ε-greedy fallback) | 0.05 | Standard RL |

### Equations

**Eq. 1 — Reward signal (motivationally gated):**
$$
r(t) = H(t)^{\phi} \cdot \mathbb{1}[\text{ate at } t] \tag{1}
$$

**Eq. 2 — Temporal-difference prediction error:**
$$
\delta(t) = r(t) + \gamma \cdot V\!\big(s(t+1)\big) - V\!\big(s(t)\big) \tag{2}
$$

**Eq. 3 — Eligibility trace update (for every state $s$):**
$$
e_s(t) = \begin{cases} \gamma \cdot \lambda_{\text{trace}} \cdot e_s(t-1) + 1 & \text{if } s = s(t) \\ \gamma \cdot \lambda_{\text{trace}} \cdot e_s(t-1) & \text{otherwise} \end{cases} \tag{3}
$$

**Eq. 4 — Value update (for every state $s$):**
$$
V(s) \leftarrow V(s) + \alpha_{\text{TD}} \cdot \delta(t) \cdot e_s(t) \tag{4}
$$

**Eq. 5 — Hunger dynamics:**
$$
H(t+1) = \min\!\Big(1,\; H(t) + \kappa - \eta_{\text{sat}} \cdot \mathbb{1}[\text{ate at } t]\Big) \tag{5}
$$

**Eq. 6 — Action-value approximation from state values:**
$$
Q(s, a) = r_{\text{imm}}(s, a) + \gamma \cdot V(s'_a) \tag{6}
$$
where $r_{\text{imm}}(s,a)$ equals $H(t)^{\phi}$ if action $a$ is "eat" and food is present at $s$, else 0; and $s'_a$ is the state reached by action $a$.

**Eq. 7 — ε-softmax action selection:**
$$
\pi(a|s) = (1 - \epsilon) \cdot \frac{\exp\!\big(Q(s,a)/\tau\big)}{\sum_{a'}\exp\!\big(Q(s,a')/\tau\big)} + \frac{\epsilon}{|\mathcal{A}|} \tag{7}
$$

### Decision logic

1. **Perceive** current grid cell $s(t)$, neighbouring cells, and whether food is present at $s(t)$.
2. **For each action** $a \in \{\text{up, down, left, right, stay, eat}\}$:
   - Determine successor state $s'_a$.
   - Compute $Q(s, a)$ via Eq. 6. If $a$ = "eat" but no food at current cell, set $Q(s, a) = -\infty$.
3. **Select action** from policy $\pi(a|s)$ using Eq. 7.
4. **Execute action**, observe reward $r(t)$ (Eq. 1) and new state $s(t+1)$.
5. **Compute** TD error $\delta(t)$ via Eq. 2.
6. **Update** eligibility traces for all visited states via Eq. 3; then **update** all state values via Eq. 4. (In practice, maintain a dictionary of non-zero traces and prune near-zero entries.)
7. **Update** hunger via Eq. 5.

*Note*: The eligibility trace mechanism (Eq. 3–4) is the key differentiator from Formulation 1. It propagates the prediction error backwards in time through recently visited states, reproducing the empirical finding (postulate P4, Schultz et al.) that dopamine signals transfer from US delivery time to the CS (earlier spatial locations that reliably precede food).

---

## Formulation 3: Bayesian Cue-Belief Agent with Motivational Gating
**Approach**: Probabilistic (Bayesian) belief updating over cue–food contingencies, with a decision rule based on expected utility maximization and motivational modulation. Fundamentally different from error-correction models: the agent maintains posterior distributions rather than point-estimate associative weights.
**Based on**: Ghirlanda (2020, Psychonomic Bulletin & Review); Oxford/Cerebral Cortex (2008) dual-role for prediction error; postulates P1, P2, P6; Bayesian brain hypothesis as bridge

### Variables
| Symbol | Name | Description | Type |
|--------|------|-------------|------|
| $\theta_i$ | Food probability given cue $i$ | Latent probability that cue $i$ leads to food being available at a cell | Latent (real ∈ [0,1]) |
| $a_i, b_i$ | Beta distribution parameters for cue $i$ | Parameterise $\text{Beta}(a_i, b_i)$ posterior over $\theta_i$ | State (internal, real > 0) |
| $\hat{\theta}_i$ | Posterior mean of $\theta_i$ | $\hat{\theta}_i = a_i / (a_i + b_i)$ | Computed |
| $U_i$ | Uncertainty (variance) of $\theta_i$ | $U_i = a_i b_i / [(a_i+b_i)^2(a_i+b_i+1)]$ | Computed |
| $P_{\text{food}}(s)$ | Estimated probability of food at cell $s$ | Combined from cue posteriors | Computed |
| $H(t)$ | Hunger level | Internal motivational drive | State (internal, real ∈ [0,1]) |
| $\text{EU}(a)$ | Expected utility of action $a$ | Combines food probability, hunger, and exploration bonus | Computed |

### Parameters
| Symbol | Name | Default | Source |
|--------|------|---------|--------|
| $a_0$ | Prior pseudo-count (hits) | 1.0 | Uniform Beta(1,1) prior — maximum ignorance |
| $b_0$ | Prior pseudo-count (misses) | 1.0 | Uniform Beta(1,1) prior |
| $w_{\text{explore}}$ | Exploration bonus weight | 0.3 | Free parameter; reflects information-seeking drive |
| $\phi$ | Hunger modulation exponent | 1.5 | Researchgate (2017) |
| $\kappa$ | Hunger recovery rate | 0.05 | Same as Formulations 1 & 2 |
| $\eta_{\text{sat}}$ | Satiation per meal | 0.4 | Normalised assumption |
| $d_{\text{max}}$ | Maximum perception radius | 2 cells | Grid-world constraint |
| $\omega$ | Prior decay rate (recency weighting) | 0.995 | Ensures non-stationarity adaptation; cf. Nature Communications (2025) |

### Equations

**Eq. 1 — Bayesian posterior update for cue $i$ after observing outcome $o \in \{0,1\}$ at a cell containing cue $i$:**
$$
a_i \leftarrow \omega \cdot a_i + o, \qquad b_i \leftarrow \omega \cdot b_i + (1 - o) \tag{1}
$$
The decay factor $\omega < 1$ implements a "leaky" Bayesian update, down-weighting old evidence so the agent can track non-stationary food distributions (cf. Nature Communications, 2025, reconciling timing and prediction error).

**Eq. 2 — Posterior mean (point estimate of food probability for cue $i$):**
$$
\hat{\theta}_i = \frac{a_i}{a_i + b_i} \tag{2}
$$

**Eq. 3 — Posterior uncertainty (variance of Beta distribution):**
$$
U_i = \frac{a_i \, b_i}{(a_i + b_i)^2 (a_i + b_i + 1)} \tag{3}
$$

**Eq. 4 — Estimated food probability at cell $s$ with cue set $C(s)$:**
$$
P_{\text{food}}(s) = 1 - \prod_{i \in C(s)} (1 - \hat{\theta}_i) \tag{4}
$$
(Noisy-OR combination: food is present if *any* cue predicts it.)

**Eq. 5 — Expected utility of moving to cell $s'$ (or staying/eating):**
$$
\text{EU}(a) = \begin{cases}
H(t)^{\phi} \cdot P_{\text{food}}(s_{\text{curr}}) & \text{if } a = \text{eat and food perceived} \\[4pt]
H(t)^{\phi} \cdot P_{\text{food}}(s'_a) + w_{\text{explore}} \cdot \displaystyle\max_{i \in C(s'_a)} \sqrt{U_i} & \text{if } a \in \{\text{move, stay}\}
\end{cases} \tag{5}
$$
The exploration bonus ($w_{\text{explore}} \cdot \sqrt{U_i}$) encourages visits to cells with uncertain cue–food associations, implementing an "information foraging" drive analogous to latent inhibition dynamics (postulate P7; pre-exposed but un-reinforced cues have high uncertainty but low mean).

**Eq. 6 — Hunger dynamics (identical across formulations):**
$$
H(t+1) = \min\!\Big(1,\; H(t) + \kappa - \eta_{\text{sat}} \cdot \mathbb{1}[\text{ate at } t]\Big) \tag{6}
$$

**Eq. 7 — Greedy action selection with tie-breaking:**
$$
a^* = \arg\max_a \; \text{EU}(a) \tag{7}
$$

### Decision logic

1. **Perceive** current cell $s_{\text{curr}}$, visible cues at all cells within radius $d_{\text{max}}$, and whether food is directly at the current cell.
2. **For each visible cell** $s'$, identify its cue set $C(s')$ and compute $P_{\text{food}}(s')$ via Eq. 4.
3. **Evaluate candidate actions:**
   - For each movement direction and "stay": compute $\text{EU}(a)$ via Eq. 5 (exploitation + exploration).
   - For "eat": if food is perceived at current cell, compute $\text{EU}(\text{eat}) = H(t)^{\phi} \cdot P_{\text{food}}(s_{\text{curr}})$; otherwise $\text{EU}(\text{eat}) = -\infty$.
4. **Select action** $a^* = \arg\max_a \text{EU}(a)$ (Eq. 7). Break ties uniformly at random.
5. **Execute action**, observe outcome $o$: 1 if food was eaten, 0 otherwise.
6. **Update posteriors** for every cue $i$ present at the cell where the outcome was observed using Eq. 1. Apply decay $\omega$ to *all* cue parameters (even unvisited) to implement recency weighting.
7. **Update hunger** via Eq. 6.

*Key differences from Formulations 1 & 2*: (a) The agent maintains full posterior distributions rather than point-estimate associative weights, enabling principled uncertainty quantification. (b) Exploration is driven by epistemic uncertainty (Eq. 5 bonus term) rather than random noise. (c) The noisy-OR combination (Eq. 4) allows cue interactions without assuming linear summation, contrasting with the Rescorla–Wagner linearity assumption. (d) The leaky prior decay (Eq. 1, $\omega$) naturally produces extinction and spontaneous recovery phenomena without a separate extinction mechanism — after many unrewarded trials, pseudo-counts shrink and the posterior reverts toward the prior.
