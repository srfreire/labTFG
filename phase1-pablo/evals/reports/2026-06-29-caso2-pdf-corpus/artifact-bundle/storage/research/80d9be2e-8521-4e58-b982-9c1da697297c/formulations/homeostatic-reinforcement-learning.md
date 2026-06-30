# Homeostatic Reinforcement Learning — Mathematical Formulations

## Formulation 1: Drive-Reduction TD Q-Learning (Model-Free)
**Approach**: Tabular Q-learning over a joint (position × internal-state) space where reward is algebraically defined as drive reduction and actions are selected via softmax over Q-values.
**Based on**: Keramati & Gutkin (2014), Sutton & Barto (1998); derived from postulates P1, P2, P4.

### Variables
| Symbol | Name | Description | Type |
|--------|------|-------------|------|
| h_t | Internal state (hunger level) | Scalar representing current deficit; 0 = sated, higher = hungrier | Continuous ∈ [0, h_max] |
| h* | Homeostatic setpoint | Ideal internal state the agent seeks to maintain | Constant scalar |
| D(h_t) | Drive | Scalar measure of deviation from setpoint | Continuous ∈ [0, ∞) |
| r_t | Homeostatic reward | Drive reduction from consuming a resource | Continuous ∈ ℝ |
| K | Outcome impact | Nutritive value of a consumed resource (reduction in h_t) | Continuous > 0 |
| Q(s, h, a) | Action-value function | Expected discounted homeostatic reward for taking action a in external state s with internal state h | Continuous ∈ ℝ |
| δ_t | Homeostatic RPE | Temporal-difference error for value update | Continuous ∈ ℝ |
| s_t | External state | Agent's grid position (x, y) | Discrete |
| a_t | Action | Chosen action: {up, down, left, right, stay, eat} | Discrete |

### Parameters
| Symbol | Name | Default | Source |
|--------|------|---------|--------|
| n | Drive exponent | 2 | Keramati & Gutkin (2014): quadratic drive penalizes large deviations superlinearly |
| m | Drive scaling | 1.0 | Keramati & Gutkin (2014): normalizing constant |
| γ | Discount factor | 0.95 | Keramati & Gutkin (2014): must be < 1 for homeostatic optimality (P3) |
| α | Learning rate | 0.1 | Standard TD-learning (Sutton & Barto, 1998) |
| β | Softmax inverse temperature | 5.0 | Controls exploration-exploitation; moderate value from prior pipeline runs |
| h* | Setpoint | 0.0 | Ideal: no deficit |
| h_max | Maximum internal state | 10.0 | Simulation bound |
| K | Resource nutritive value | 3.0 | Per-resource drive reduction |
| λ_drift | Metabolic drift rate | 0.1 | Per-timestep increase in hunger (metabolic cost) |
| h_bins | Internal state discretization bins | 10 | For tabular representation |

### Equations

**Eq. 1 — Drive function:**
`D(h_t) = m * |h_t - h*|^n`
$$D(h_t) = m \cdot |h_t - h^*|^n \tag{1}$$

**Eq. 2 — Internal state dynamics (metabolic drift + consumption):**
`h_{t+1} = clip(h_t + λ_drift - K * ate_t, 0, h_max)`
$$h_{t+1} = \text{clip}\!\left(h_t + \lambda_{\text{drift}} - K \cdot \mathbb{1}[\text{ate}_t],\; 0,\; h_{\max}\right) \tag{2}$$

**Eq. 3 — Homeostatic reward (drive reduction):**
`r_t = D(h_t) - D(h_{t+1})`
$$r_t = D(h_t) - D(h_{t+1}) \tag{3}$$

**Eq. 4 — Homeostatic reward prediction error (hRPE):**
`δ_t = r_t + γ * max_a' Q(s_{t+1}, h_{t+1}, a') - Q(s_t, h_t, a_t)`
$$\delta_t = r_t + \gamma \max_{a'} Q(s_{t+1}, h_{t+1}, a') - Q(s_t, h_t, a_t) \tag{4}$$

**Eq. 5 — Q-value update:**
`Q(s_t, h_t, a_t) ← Q(s_t, h_t, a_t) + α * δ_t`
$$Q(s_t, h_t, a_t) \leftarrow Q(s_t, h_t, a_t) + \alpha \cdot \delta_t \tag{5}$$

**Eq. 6 — Softmax action selection:**
`P(a | s_t, h_t) = exp(β * Q(s_t, h_t, a)) / Σ_j exp(β * Q(s_t, h_t, j))`
$$P(a \mid s_t, h_t) = \frac{\exp\!\big(\beta \, Q(s_t, h_t, a)\big)}{\sum_{j} \exp\!\big(\beta \, Q(s_t, h_t, j)\big)} \tag{6}$$

### Decision logic
1. **Perceive**: Read external state s_t (grid position), internal state h_t (hunger), and nearby resource locations from perception.
2. **Discretize**: Bin h_t into one of `h_bins` bins to form the joint state key (s_t, h_bin).
3. **Compute action probabilities**: For each action a ∈ {up, down, left, right, stay, eat}, look up Q(s_t, h_bin, a). Compute softmax probabilities via **Eq. 6**.
4. **Filter invalid actions**: Set P(eat) = 0 if no resource is at the agent's current position; renormalize.
5. **Sample action**: Draw a_t from the probability distribution P(a | s_t, h_t).
6. **Update (after outcome observed)**: Compute h_{t+1} via **Eq. 2**, r_t via **Eq. 3**, δ_t via **Eq. 4**, and update Q via **Eq. 5**.

---

## Formulation 2: Continuous Drive-Gradient Reactive Policy (Algebraic/Geometric)
**Approach**: A memoryless algebraic policy that selects actions by computing the immediate expected drive reduction for each candidate action using a gradient-descent-like heuristic over the drive landscape — no learned Q-table, purely reactive state-dependent valuation.
**Based on**: Keramati & Gutkin (2014) postulates P1, P4; Hull (1943) drive-reduction theory; Cabanac (1971) alliesthesia.

### Variables
| Symbol | Name | Description | Type |
|--------|------|-------------|------|
| h_t | Internal state (hunger) | Current deficit level | Continuous ∈ [0, h_max] |
| h* | Homeostatic setpoint | Target internal state | Constant |
| D(h_t) | Drive | Deviation cost | Continuous ∈ [0, ∞) |
| s_t | Position | Agent's (x, y) grid cell | Discrete |
| R | Resource map | Set of (x, y) positions containing food | Discrete set |
| d_Manhattan(s_t, r) | Distance to resource r | Manhattan distance on grid | Integer ≥ 0 |
| U(a) | Utility of action a | Expected one-step drive reduction + proximity reward | Continuous ∈ ℝ |
| a_t | Action | Chosen action | Discrete |

### Parameters
| Symbol | Name | Default | Source |
|--------|------|---------|--------|
| n | Drive exponent | 2 | Keramati & Gutkin (2014) |
| m | Drive scaling | 1.0 | Keramati & Gutkin (2014) |
| K | Resource nutritive value | 3.0 | Simulation design |
| λ_drift | Metabolic drift rate | 0.1 | Simulation design |
| h* | Setpoint | 0.0 | No-deficit ideal |
| h_max | Maximum hunger | 10.0 | Simulation bound |
| w_prox | Proximity weight | 0.5 | Tuned: weights approach vs. immediate reward |
| β | Softmax inverse temperature | 5.0 | Controls stochasticity |
| η | Satiation threshold | 0.5 | Below this drive, agent prefers to stay; prevents over-consumption |

### Equations

**Eq. 1 — Drive function:**
`D(h) = m * |h - h*|^n`
$$D(h) = m \cdot |h - h^*|^n \tag{1}$$

**Eq. 2 — Immediate drive reduction from eating (at a resource cell):**
`ΔD_eat = D(h_t) - D(clip(h_t + λ_drift - K, 0, h_max))`
$$\Delta D_{\text{eat}} = D(h_t) - D\!\big(\text{clip}(h_t + \lambda_{\text{drift}} - K,\; 0,\; h_{\max})\big) \tag{2}$$

**Eq. 3 — Proximity gain for movement action a:**
`Prox(a) = d_nearest(s_t) - d_nearest(s_t + Δ(a))`
$$\text{Prox}(a) = d_{\text{nearest}}(s_t) - d_{\text{nearest}}\!\big(s_t + \Delta(a)\big) \tag{3}$$

where d_nearest(s) = min_{r ∈ R} d_Manhattan(s, r) is the distance to the nearest resource.

**Eq. 4 — Drive-weighted proximity (alliesthesia modulation):**
`U_move(a) = w_prox * D(h_t) * Prox(a)`
$$U_{\text{move}}(a) = w_{\text{prox}} \cdot D(h_t) \cdot \text{Prox}(a) \tag{4}$$

**Eq. 5 — Utility of eating:**
`U_eat = ΔD_eat   (if resource present at s_t, else -∞)`
$$U_{\text{eat}} = \Delta D_{\text{eat}} \quad \text{if resource at } s_t, \;\text{else } -\infty \tag{5}$$

**Eq. 6 — Utility of staying:**
`U_stay = -D(h_t + λ_drift) + D(h_t)`
$$U_{\text{stay}} = -\big(D(h_t + \lambda_{\text{drift}}) - D(h_t)\big) \tag{6}$$

Note: U_stay is always ≤ 0 — staying incurs the metabolic drift cost in drive terms.

**Eq. 7 — Softmax action selection over utilities:**
`P(a) = exp(β * U(a)) / Σ_j exp(β * U(j))`
$$P(a) = \frac{\exp\!\big(\beta \, U(a)\big)}{\sum_{j} \exp\!\big(\beta \, U(j)\big)} \tag{7}$$

### Decision logic
1. **Perceive**: Read position s_t, hunger h_t, list of visible resource positions R.
2. **Compute drive**: Calculate D(h_t) via **Eq. 1**.
3. **Evaluate eat**: If resource at s_t and D(h_t) > η, compute U_eat via **Eq. 2** & **Eq. 5**. If D(h_t) ≤ η (near setpoint), set U_eat = −∞ (satiation gate prevents over-eating).
4. **Evaluate movement actions**: For each a ∈ {up, down, left, right}, compute Prox(a) via **Eq. 3** and U_move(a) via **Eq. 4**. Note: when D(h_t) ≈ 0, U_move ≈ 0, so the agent becomes indifferent to approaching food — this is alliesthesia (**P4**).
5. **Evaluate stay**: Compute U_stay via **Eq. 6**.
6. **Select action**: Compute softmax over all U values via **Eq. 7**; sample a_t.
7. **Update**: After action, update h_t via metabolic drift and consumption. No Q-table update needed (reactive policy). Optionally update resource map R from new perception.

---

## Formulation 3: Free-Energy Minimizing Homeostatic Agent (Probabilistic/Bayesian)
**Approach**: Active inference formulation where the agent maintains a probabilistic belief over its internal state and nearby resources, then selects actions by minimizing expected free energy — unifying homeostatic drive with epistemic exploration.
**Based on**: Friston (2010) Free Energy Principle; Keramati & Gutkin (2014) equivalence between drive and negative log-probability (P1, P2); Petzschner et al. (2021) computational interoception.

### Variables
| Symbol | Name | Description | Type |
|--------|------|-------------|------|
| h_t | Internal state (hunger) | Current deficit level | Continuous ∈ [0, h_max] |
| μ_h | Believed hunger mean | Agent's estimate of its hunger | Continuous |
| σ_h | Believed hunger uncertainty | Uncertainty in interoceptive estimate | Continuous > 0 |
| p(h) | Prior over internal state | Gaussian prior centered at setpoint h* encoding preferred state | Distribution |
| q(h_t) | Approximate posterior | Agent's belief about current internal state q(h_t) = N(μ_h, σ_h²) | Distribution |
| s_t | Position | Grid cell (x, y) | Discrete |
| o_t | Observation | Perceived hunger signal (noisy version of h_t) + resource visibility | Tuple |
| G(a) | Expected free energy of action a | Combines pragmatic (drive-reducing) and epistemic (uncertainty-reducing) value | Continuous ∈ ℝ |
| a_t | Action | Chosen action | Discrete |
| R_beliefs | Resource belief map | Per-cell probability of resource presence | Continuous ∈ [0,1] per cell |

### Parameters
| Symbol | Name | Default | Source |
|--------|------|---------|--------|
| h* | Setpoint (prior mean) | 0.0 | Keramati & Gutkin (2014) |
| σ_p | Prior precision (std dev of preferred state) | 1.0 | Friston (2010): tighter prior = stronger homeostatic regulation |
| σ_obs | Interoceptive observation noise | 0.5 | Petzschner et al. (2021): interoceptive uncertainty |
| K | Resource nutritive value | 3.0 | Simulation design |
| λ_drift | Metabolic drift | 0.1 | Simulation design |
| h_max | Maximum hunger | 10.0 | Simulation bound |
| β_G | Action selection inverse temperature | 5.0 | Controls policy determinism |
| w_e | Epistemic weight | 0.3 | Balances exploration vs. exploitation |
| κ | Resource belief decay | 0.05 | Rate at which unvisited cells lose believed resource probability |

### Equations

**Eq. 1 — Generative model (preferred internal state prior):**
`p(h) = N(h | h*, σ_p²)`
$$p(h) = \mathcal{N}(h \mid h^*, \sigma_p^2) \tag{1}$$

**Eq. 2 — Interoceptive observation model:**
`p(o_h | h_t) = N(o_h | h_t, σ_obs²)`
$$p(o_h \mid h_t) = \mathcal{N}(o_h \mid h_t, \sigma_{obs}^2) \tag{2}$$

**Eq. 3 — Bayesian belief update (posterior over internal state):**
`μ_h ← (σ_obs² * μ_h_prior + σ_prior² * o_h) / (σ_obs² + σ_prior²)`
`σ_h² ← (σ_obs² * σ_prior²) / (σ_obs² + σ_prior²)`
$$\mu_h \leftarrow \frac{\sigma_{obs}^2 \, \mu_{h}^{\text{prior}} + \sigma_{h}^{2,\text{prior}} \, o_h}{\sigma_{obs}^2 + \sigma_{h}^{2,\text{prior}}} \tag{3a}$$
$$\sigma_h^2 \leftarrow \frac{\sigma_{obs}^2 \cdot \sigma_{h}^{2,\text{prior}}}{\sigma_{obs}^2 + \sigma_{h}^{2,\text{prior}}} \tag{3b}$$

**Eq. 4 — Pragmatic value (negative expected drive under action a):**
`G_prag(a) = -E_q[ D(h_{t+1}(a)) ] ≈ -(μ_h + λ_drift - K * eats(a))² / σ_p²`
$$G_{\text{prag}}(a) = -\mathbb{E}_{q}\!\left[\frac{(h_{t+1}(a) - h^*)^2}{\sigma_p^2}\right] \approx -\frac{(\mu_h + \lambda_{\text{drift}} - K \cdot \mathbb{1}[\text{eats}(a)] - h^*)^2 + \sigma_h^2}{\sigma_p^2} \tag{4}$$

Here, the drive is the negative log-prior density (up to constants): D(h) = (h − h*)² / σ_p², connecting to Keramati & Gutkin (2014)'s equivalence with informational surprise per Friston (2010).

**Eq. 5 — Epistemic value (information gain about resources):**
`G_epist(a) = Σ_{cells c reachable by a} H[R_beliefs(c)]`
$$G_{\text{epist}}(a) = \sum_{c \in \text{reach}(a)} \mathcal{H}\!\big[R_{\text{beliefs}}(c)\big] \tag{5}$$

where $\mathcal{H}[p] = -p\ln p - (1-p)\ln(1-p)$ is the binary entropy of the resource belief for cell c. Actions that move toward uncertain cells have higher epistemic value.

**Eq. 6 — Expected free energy (combined):**
`G(a) = G_prag(a) + w_e * G_epist(a)`
$$G(a) = G_{\text{prag}}(a) + w_e \cdot G_{\text{epist}}(a) \tag{6}$$

**Eq. 7 — Action selection (softmax over negative free energy):**
`P(a) = exp(β_G * G(a)) / Σ_j exp(β_G * G(j))`
$$P(a) = \frac{\exp\!\big(\beta_G \, G(a)\big)}{\sum_j \exp\!\big(\beta_G \, G(j)\big)} \tag{7}$$

Note: G(a) is already defined so that *higher* G is better (pragmatic is negative cost, epistemic is positive entropy), so we maximize G.

**Eq. 8 — Internal state transition:**
`h_{t+1} = clip(h_t + λ_drift - K * ate_t, 0, h_max)`
$$h_{t+1} = \text{clip}(h_t + \lambda_{\text{drift}} - K \cdot \mathbb{1}[\text{ate}_t],\; 0,\; h_{\max}) \tag{8}$$

**Eq. 9 — Resource belief update:**
`R_beliefs(c) ← 1.0 if resource observed at c; R_beliefs(c) * (1 - κ) if c visited and empty; unchanged otherwise`
$$R_{\text{beliefs}}(c) \leftarrow \begin{cases} 1.0 & \text{resource observed at } c \\ R_{\text{beliefs}}(c)(1 - \kappa) & \text{visited, empty} \\ R_{\text{beliefs}}(c) & \text{otherwise} \end{cases} \tag{9}$$

### Decision logic
1. **Perceive**: Read position s_t, noisy hunger observation o_h, visible resource cells.
2. **Update internal belief**: Apply Bayesian update (**Eq. 3a, 3b**) to get posterior (μ_h, σ_h²). The prior for this step is the predicted state from last timestep: μ_h^prior = μ_h^prev + λ_drift, σ_h^{2,prior} = σ_h^{2,prev} + σ_process² (with σ_process² = 0.01).
3. **Update resource beliefs**: For all visible cells, apply **Eq. 9**.
4. **Evaluate each action**:
   - For **eat**: If resource present at s_t, compute G_prag(eat) via **Eq. 4** with eats = 1, G_epist(eat) = 0. If no resource, G(eat) = −∞.
   - For **movement** actions (up/down/left/right): Compute G_prag(a) via **Eq. 4** with eats = 0. Compute G_epist(a) via **Eq. 5** — sum entropy of beliefs for cells that would become visible after moving.
   - For **stay**: G_prag(stay) via **Eq. 4** with eats = 0, G_epist(stay) = 0.
5. **Combine**: G(a) = G_prag(a) + w_e · G_epist(a) for each action (**Eq. 6**).
6. **Select action**: Softmax over G(a) via **Eq. 7**; sample a_t.
7. **After outcome**: Update h_t via **Eq. 8**; propagate belief forward for next step.

---

## Cross-formulation comparison

| Aspect | Formulation 1: Drive-Reduction TD Q-Learning | Formulation 2: Drive-Gradient Reactive Policy | Formulation 3: Free-Energy Minimizing Agent |
|--------|----------------------------------------------|-----------------------------------------------|---------------------------------------------|
| Framework | Model-free RL (tabular Q-learning with TD updates) | Algebraic / geometric (one-step lookahead utility) | Probabilistic / Bayesian (active inference) |
| Key variables | Q(s, h, a), δ_t (hRPE), D(h_t) | U(a), Prox(a), D(h_t) | G(a), q(h_t) = N(μ_h, σ_h²), R_beliefs |
| Core equation | δ_t = r_t + γ·max Q(s', h', a') − Q(s, h, a) (Eq. 4) | U_move(a) = w_prox · D(h_t) · Prox(a) (Eq. 4) | G(a) = G_prag(a) + w_e · G_epist(a) (Eq. 6) |
| Decision mechanism | Softmax over *learned* Q-values that encode long-run discounted drive reduction | Softmax over *computed* one-step utilities combining immediate drive reduction & proximity | Softmax over *expected free energy* combining pragmatic (homeostatic) and epistemic (exploratory) terms |
| Internal state representation | Discretized hunger bins (exact h_t known) | Exact continuous hunger value (fully observable) | Probabilistic belief N(μ_h, σ_h²) over noisy hunger |
| Learning | Yes — Q-values updated every step via TD error; improves over time | No learning — policy is reactive/analytic; depends only on current state | Partial — resource beliefs updated; internal belief updated via Bayes; no value function learning |
| Handles uncertainty | No (assumes full observability of h_t and resources) | No (assumes known resource map and exact h_t) | Yes — models interoceptive noise and resource uncertainty; explores to reduce uncertainty |
| Anticipatory behavior (P5) | Yes — Q-values over joint state space learn to act before deficit arises | Limited — only reacts to current drive and distance; no multi-step planning | Partial — pragmatic term looks one step ahead; epistemic term drives exploration of unknown areas |
| Alliesthesia (P4) | Emergent — Q-values at low drive converge to ~0, so no food-seeking | Explicit — U_move is multiplicatively gated by D(h_t); also satiation threshold η | Explicit — G_prag(eat) ≈ 0 when μ_h ≈ h*, so eating yields no pragmatic benefit near setpoint |
| Strengths | Learns optimal long-horizon policies; handles delayed rewards; principled (TD convergence guarantees) | Simple, interpretable, no training needed; very fast computation; captures alliesthesia analytically | Handles partial observability of internal state; natural exploration via epistemic drive; theoretically grounded in FEP |
| Limitations | Large state space (position × hunger bins × actions); slow early learning; no exploration bonus | Myopic (one-step horizon); cannot learn from experience; no anticipatory behavior over multiple steps | Computationally heavier; approximations needed for pragmatic term; no long-horizon planning without tree search |
