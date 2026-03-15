# Gut-Brain Axis Signaling in Food Intake Regulation — Mathematical Formulations

## Formulation 1: ODE-Based Neuroendocrine Dynamics with Hypothalamic Integration
**Approach**: Continuous-time ordinary differential equations model hormone kinetics and a hypothalamic feeding-drive integrator, discretized at each simulation tick for action selection.
**Based on**: Yoo & Park (2021), Berthoud (2011), PMC11483575 (2024)

### Variables
| Symbol | Name | Description | Type |
|--------|------|-------------|------|
| $H_{CCK}(t)$ | CCK level | Plasma cholecystokinin concentration (short-acting satiety signal) | Continuous, ≥ 0 |
| $H_{GLP1}(t)$ | GLP-1 level | Plasma GLP-1 concentration (medium-acting satiety signal) | Continuous, ≥ 0 |
| $H_{PYY}(t)$ | PYY level | Plasma Peptide YY concentration (longer-acting satiety signal) | Continuous, ≥ 0 |
| $G(t)$ | Ghrelin level | Plasma ghrelin concentration (orexigenic hunger signal) | Continuous, ≥ 0 |
| $S(t)$ | Stomach fill | Gastric nutrient content representing recent food intake | Continuous, [0, 1] |
| $F(t)$ | Feeding drive | Net hypothalamic drive to eat (positive = hungry, negative = sated) | Continuous, ℝ |
| $E(t)$ | Energy reserve | Internal energy store (analogue of adiposity / leptin-signaled reserve) | Continuous, ≥ 0 |
| $\mathbf{p}(t)$ | Position | Agent's (x, y) grid position | Discrete |
| $r_i$ | Resource locations | Positions and values of nearby food items (from perception) | Discrete set |

### Parameters
| Symbol | Name | Default | Source |
|--------|------|---------|--------|
| $k_{sec}^{CCK}$ | CCK secretion rate | 0.8 per meal-unit | Berthoud (2011): CCK is rapidly released by fat/protein |
| $k_{sec}^{GLP1}$ | GLP-1 secretion rate | 0.5 per meal-unit | Yoo & Park (2021): GLP-1 rises proportionally to caloric load |
| $k_{sec}^{PYY}$ | PYY secretion rate | 0.3 per meal-unit | PMC11483575 (2024): PYY release proportional to calories |
| $k_{cl}^{CCK}$ | CCK clearance rate | 0.6 per tick | Half-life ~minutes; fastest of satiety peptides (Berthoud, 2011) |
| $k_{cl}^{GLP1}$ | GLP-1 clearance rate | 0.3 per tick | Half-life ~2 min active but sustained by DPP-4 dynamics (Yoo & Park, 2021) |
| $k_{cl}^{PYY}$ | PYY clearance rate | 0.15 per tick | Longer half-life than CCK (PMC11483575, 2024) |
| $k_G^{rise}$ | Ghrelin rise rate | 0.1 per tick | Ghrelin rises tonically during fasting (MDPI Nutrients, 2023) |
| $k_G^{sup}$ | Ghrelin suppression factor | 0.7 per meal-unit | Post-prandial ghrelin suppression (Yoo & Park, 2021) |
| $\alpha$ | Ghrelin sensitivity | 1.5 | Orexigenic drive weight (PMC11483575, 2024) |
| $\beta_1$ | CCK sensitivity | 1.0 | Short-term satiety weight (Berthoud, 2011) |
| $\beta_2$ | GLP-1 sensitivity | 1.2 | Medium-term satiety weight (Yoo & Park, 2021) |
| $\beta_3$ | PYY sensitivity | 0.8 | Longer-term satiety weight (PMC11483575, 2024) |
| $\gamma$ | Energy-deficit drive | 0.4 | Leptin-analogue homeostatic correction |
| $E_{set}$ | Energy setpoint | 5.0 | Target energy reserve (homeostatic setpoint concept from Berthoud, 2011) |
| $E_{cost}$ | Movement energy cost | 0.05 per tick | Metabolic cost of movement |
| $E_{gain}$ | Eating energy gain | 1.0 per resource | Energy from consuming one food item |
| $\delta$ | Stomach decay | 0.2 per tick | Gastric emptying rate |

### Equations

**Hormone kinetics** (discretized Euler step, $\Delta t = 1$ tick):

$$
H_{CCK}(t+1) = H_{CCK}(t) + k_{sec}^{CCK} \cdot \mathbb{1}_{ate}(t) - k_{cl}^{CCK} \cdot H_{CCK}(t) \tag{1}
$$

$$
H_{GLP1}(t+1) = H_{GLP1}(t) + k_{sec}^{GLP1} \cdot S(t) \cdot \mathbb{1}_{ate}(t) - k_{cl}^{GLP1} \cdot H_{GLP1}(t) \tag{2}
$$

$$
H_{PYY}(t+1) = H_{PYY}(t) + k_{sec}^{PYY} \cdot S(t) - k_{cl}^{PYY} \cdot H_{PYY}(t) \tag{3}
$$

**Ghrelin dynamics** (rises when fasting, suppressed by eating):

$$
G(t+1) = G(t) + k_G^{rise} \cdot (1 - S(t)) - k_G^{sup} \cdot \mathbb{1}_{ate}(t) \cdot G(t) \tag{4}
$$

$$
G(t+1) = \max(G(t+1),\; 0) \tag{4b}
$$

**Stomach fill** (decays via gastric emptying, increased by eating):

$$
S(t+1) = S(t) - \delta \cdot S(t) + \mathbb{1}_{ate}(t) \cdot (1 - S(t)) \cdot 0.5 \tag{5}
$$

**Energy reserve**:

$$
E(t+1) = E(t) - E_{cost} + E_{gain} \cdot \mathbb{1}_{ate}(t) \tag{6}
$$

**Hypothalamic feeding drive** (net integration of orexigenic vs. anorexigenic signals):

$$
F(t) = \alpha \cdot G(t) - \beta_1 \cdot H_{CCK}(t) - \beta_2 \cdot H_{GLP1}(t) - \beta_3 \cdot H_{PYY}(t) + \gamma \cdot (E_{set} - E(t)) \tag{7}
$$

### Decision Logic

1. **Update internal state**: Compute Eqs. (1)–(6) using previous state and whether the agent ate last tick ($\mathbb{1}_{ate}$).
2. **Compute feeding drive** $F(t)$ via Eq. (7).
3. **If food is at the agent's current position AND $F(t) > 0$**: choose **EAT**. The agent is hungry enough and food is available.
4. **Else if $F(t) > 0$ (hungry) AND food is visible in perception**:
   - Identify the nearest food resource $r^*$ from the perception.
   - Choose the movement action (UP / DOWN / LEFT / RIGHT) that minimizes Manhattan distance to $r^*$.
5. **Else if $F(t) \leq 0$ (sated)**:
   - Choose **STAY** (no motivation to seek food).
6. **Tie-breaking**: If multiple directions equally reduce distance, pick randomly among them.

---

## Formulation 2: Bayesian Belief-Based Foraging with Gut Signals as Priors
**Approach**: Probabilistic (Bayesian) decision framework where gut-derived hormonal signals shape prior beliefs about internal energy state and expected reward from eating, updated by observations.
**Based on**: Mayer (2011), MDPI Nutrients (2023), PMC11483575 (2024); draws on active inference / interoceptive predictive processing ideas consistent with Mayer's "gut feelings" framework

### Variables
| Symbol | Name | Description | Type |
|--------|------|-------------|------|
| $b_H(t)$ | Hunger belief | Agent's Bayesian posterior belief that it is in a "hungry" state, $b_H \in [0,1]$ | Continuous |
| $\mu_E(t)$ | Expected energy | Estimated internal energy level (mean of belief distribution) | Continuous, ≥ 0 |
| $\sigma_E(t)$ | Energy uncertainty | Uncertainty (std dev) of internal energy estimate | Continuous, > 0 |
| $V_{eat}(t)$ | Expected value of eating | Predicted reward from eating at current position | Continuous, ℝ |
| $V_{move,d}(t)$ | Expected value of moving | Predicted reward from moving in direction $d$ | Continuous, ℝ |
| $V_{stay}(t)$ | Expected value of staying | Predicted reward from staying in place | Continuous, ℝ |
| $o_{ate}(t)$ | Ate observation | Binary: did the agent eat last tick? | Binary |
| $o_{food}(t)$ | Food proximity signal | Number of food items visible in perception | Discrete, ≥ 0 |
| $h_{gut}(t)$ | Gut hormone composite | Aggregated anorexigenic gut signal (GLP-1 + PYY + CCK analogue) | Continuous, ≥ 0 |
| $g(t)$ | Ghrelin signal | Orexigenic interoceptive signal | Continuous, ≥ 0 |

### Parameters
| Symbol | Name | Default | Source |
|--------|------|---------|--------|
| $\lambda_{hunger}$ | Hunger drift rate | 0.08 per tick | Tonic ghrelin rise rate (Yoo & Park, 2021) |
| $\lambda_{satiety}$ | Satiety impulse | 0.6 | Post-meal satiety peptide surge magnitude (Berthoud, 2011) |
| $\tau_{gut}$ | Gut signal decay | 0.25 per tick | Hormone half-life composite (PMC11483575, 2024) |
| $\sigma_{intero}$ | Interoceptive noise | 0.15 | Uncertainty in gut-to-brain signaling (Mayer, 2011: interoceptive variability) |
| $\omega_{homeo}$ | Homeostatic weight | 0.7 | Weight of homeostatic vs hedonic evaluation |
| $\omega_{hedon}$ | Hedonic weight | 0.3 | Reward system contribution (PMC11483575, 2024: hedonic override) |
| $R_{food}$ | Food reward value | 1.0 | Reward per food item consumed |
| $C_{move}$ | Movement cost | 0.02 | Energy cost per step |
| $\eta$ | Learning rate | 0.2 | Bayesian update step size (approximate) |
| $\epsilon$ | Exploration rate | 0.1 | Probability of random action (softmax temperature proxy) |
| $d_{max}$ | Max perception distance | 5 | Visible grid radius |

### Equations

**Gut hormone composite update** (decays, boosted by eating):

$$
h_{gut}(t+1) = (1 - \tau_{gut}) \cdot h_{gut}(t) + \lambda_{satiety} \cdot o_{ate}(t) \tag{1}
$$

**Ghrelin signal update** (rises with time since last meal, suppressed by eating):

$$
g(t+1) = g(t) + \lambda_{hunger} \cdot (1 - o_{ate}(t)) - 0.5 \cdot g(t) \cdot o_{ate}(t) \tag{2}
$$

**Bayesian hunger belief update** — The agent treats hunger as a latent state. The "likelihood" of observing its current gut signals given hunger/satiety is Gaussian:

$$
\ell_H = \frac{1}{\sqrt{2\pi}\sigma_{intero}} \exp\!\left(-\frac{(g(t) - g_{exp}^{hungry})^2}{2\sigma_{intero}^2}\right) \tag{3a}
$$

$$
\ell_S = \frac{1}{\sqrt{2\pi}\sigma_{intero}} \exp\!\left(-\frac{(h_{gut}(t) - h_{exp}^{sated})^2}{2\sigma_{intero}^2}\right) \tag{3b}
$$

where $g_{exp}^{hungry} = 1.0$ (expected ghrelin when hungry) and $h_{exp}^{sated} = 1.0$ (expected satiety hormone when sated).

$$
b_H(t) = \frac{\ell_H \cdot b_H(t-1)}{\ell_H \cdot b_H(t-1) + \ell_S \cdot (1 - b_H(t-1))} \tag{4}
$$

**Action-value computation** — values blend homeostatic need and hedonic reward:

$$
V_{eat}(t) = \omega_{homeo} \cdot b_H(t) \cdot R_{food} + \omega_{hedon} \cdot R_{food} \cdot \frac{1}{1 + h_{gut}(t)} \tag{5}
$$

$$
V_{move,d}(t) = b_H(t) \cdot \frac{\text{food\_proximity}(d)}{d_{max}} \cdot R_{food} - C_{move} \tag{6}
$$

where $\text{food\_proximity}(d)$ is the inverse distance to the nearest food in direction $d$ (0 if no food visible in that direction).

$$
V_{stay}(t) = (1 - b_H(t)) \cdot 0.1 \tag{7}
$$

**Action selection** via softmax over action values:

$$
P(a) = \frac{\exp(V_a / T)}{\sum_{a'} \exp(V_{a'} / T)} \tag{8}
$$

where $T = \epsilon + 0.05$ is a temperature parameter.

### Decision Logic

1. **Update gut signals**: Compute $h_{gut}(t+1)$ (Eq. 1) and $g(t+1)$ (Eq. 2) from the previous tick's eat observation.
2. **Update hunger belief**: Compute likelihoods (Eqs. 3a, 3b) and posterior $b_H(t)$ (Eq. 4).
3. **Compute action values**:
   - If food is at the agent's current cell, compute $V_{eat}$ (Eq. 5).
   - For each direction $d \in \{$UP, DOWN, LEFT, RIGHT$\}$, compute $V_{move,d}$ (Eq. 6).
   - Compute $V_{stay}$ (Eq. 7).
4. **Select action** by sampling from the softmax distribution over all action values (Eq. 8).
5. **After receiving reward**: Update $o_{ate}(t)$ for the next tick. If reward > 0, set $o_{ate} = 1$; else $o_{ate} = 0$.

---

## Formulation 3: Reinforcement-Learning Agent with Microbiota-Modulated Reward Shaping
**Approach**: Tabular Q-learning where the reward signal is shaped by a dynamic gut microbiota state that modulates SCFA production and GLP-1 secretion, altering the effective reward the agent perceives from eating.
**Based on**: MDPI Nutrients (2023), Nature Signal Transduction and Targeted Therapy (2022), Frontiers (2023); microbiota–SCFA–GLP-1 cascade from the deep report

### Variables
| Symbol | Name | Description | Type |
|--------|------|-------------|------|
| $Q(s, a)$ | Action-value function | Expected cumulative reward for state $s$, action $a$ | Continuous, ℝ |
| $s(t)$ | State | Discretized tuple: (hunger_level, food_nearby, microbiota_health) | Discrete |
| $M(t)$ | Microbiota health | Index of gut microbiome diversity/health, $M \in [0, 1]$ | Continuous |
| $SCFA(t)$ | SCFA production | Short-chain fatty acid level produced by microbiota | Continuous, ≥ 0 |
| $H_{GLP1}(t)$ | GLP-1 level | Plasma GLP-1 driven by SCFA stimulation and direct nutrient sensing | Continuous, ≥ 0 |
| $R_{shaped}(t)$ | Shaped reward | Internal reward signal as perceived by the agent (modulated by gut state) | Continuous, ℝ |
| $E(t)$ | Energy reserve | Internal energy level | Continuous, ≥ 0 |
| $D(t)$ | Diet diversity score | Rolling measure of variety in recently consumed food types | Continuous, [0, 1] |

### Parameters
| Symbol | Name | Default | Source |
|--------|------|---------|--------|
| $\alpha_{lr}$ | Q-learning rate | 0.1 | Standard RL parameter |
| $\gamma_{disc}$ | Discount factor | 0.95 | Standard RL parameter |
| $\epsilon_{greedy}$ | Exploration rate | 0.15 | ε-greedy exploration |
| $k_{SCFA}$ | SCFA production rate | 0.4 | Proportional to microbiota health (Nature Signal Transduction, 2022) |
| $k_{SCFA\_decay}$ | SCFA clearance | 0.2 per tick | Metabolic clearance |
| $k_{GLP1\_SCFA}$ | SCFA→GLP-1 coupling | 0.5 | SCFAs stimulate L-cell GLP-1 secretion (MDPI Nutrients, 2023) |
| $k_{GLP1\_decay}$ | GLP-1 decay rate | 0.3 per tick | DPP-4 mediated clearance (Yoo & Park, 2021) |
| $\mu_{adapt}$ | Microbiota adaptation rate | 0.05 per tick | Slow diet-driven microbiome remodeling (Frontiers, 2023) |
| $M_{baseline}$ | Baseline microbiota health | 0.5 | Moderate diversity starting point |
| $\phi_{sat}$ | Satiety reward shaping coefficient | 0.5 | How much GLP-1 shapes the reward negatively post-meal |
| $\phi_{energy}$ | Energy depletion penalty | -0.3 | Starvation penalty per tick below threshold |
| $E_{threshold}$ | Low energy threshold | 1.0 | Below this, starvation penalty kicks in |
| $E_{cost}$ | Per-tick energy cost | 0.05 | Basal metabolic drain |

### Equations

**Microbiota dynamics** (slowly adapts based on diet diversity):

$$
M(t+1) = M(t) + \mu_{adapt} \cdot (D(t) - M(t)) \tag{1}
$$

**Diet diversity** (rolling exponential average of whether agent consumed food):

$$
D(t+1) = 0.9 \cdot D(t) + 0.1 \cdot \mathbb{1}_{ate}(t) \tag{2}
$$

**SCFA production** (microbiota-dependent, decays metabolically):

$$
SCFA(t+1) = (1 - k_{SCFA\_decay}) \cdot SCFA(t) + k_{SCFA} \cdot M(t) \cdot \mathbb{1}_{ate}(t) \tag{3}
$$

**GLP-1 from SCFA cascade** (the microbiota → EEC → peptide pathway):

$$
H_{GLP1}(t+1) = (1 - k_{GLP1\_decay}) \cdot H_{GLP1}(t) + k_{GLP1\_SCFA} \cdot SCFA(t) \cdot \mathbb{1}_{ate}(t) \tag{4}
$$

**Energy dynamics**:

$$
E(t+1) = E(t) - E_{cost} + \mathbb{1}_{ate}(t) \cdot 1.0 \tag{5}
$$

**Shaped reward** (the agent's subjective reward, modulated by gut-brain signals):

$$
R_{shaped}(t) = R_{env}(t) \cdot \underbrace{\left(1 - \phi_{sat} \cdot H_{GLP1}(t)\right)}_{\text{satiety attenuation}} + \phi_{energy} \cdot \max(0, E_{threshold} - E(t)) \tag{6}
$$

Here $R_{env}(t)$ is the raw environment reward (e.g., +1 for eating). When GLP-1 is high (sated), the perceived reward of eating is diminished — modeling how satiety peptides reduce the hedonic value of food (PMC11483575, 2024). When energy is critically low, the penalty drives urgent foraging.

**Q-learning update**:

$$
Q(s_t, a_t) \leftarrow Q(s_t, a_t) + \alpha_{lr} \left[ R_{shaped}(t) + \gamma_{disc} \cdot \max_{a'} Q(s_{t+1}, a') - Q(s_t, a_t) \right] \tag{7}
$$

**State discretization**: $s = (h_{bin}, f_{near}, m_{bin})$ where:
- $h_{bin} \in \{0,1,2\}$: hunger level = $\lfloor \min(2, \max(0, 3 \cdot (1 - H_{GLP1}(t)))) \rfloor$ (high GLP-1 → low hunger bin)
- $f_{near} \in \{0,1\}$: 1 if food is adjacent or at current position, else 0
- $m_{bin} \in \{0,1\}$: 1 if $M(t) > 0.5$ (healthy microbiota), else 0

This yields $3 \times 2 \times 2 = 12$ discrete states.

### Decision Logic

1. **Update gut-microbiota cascade**: Compute $M(t+1)$ (Eq. 1), $D(t+1)$ (Eq. 2), $SCFA(t+1)$ (Eq. 3), $H_{GLP1}(t+1)$ (Eq. 4), $E(t+1)$ (Eq. 5).
2. **Compute shaped reward** $R_{shaped}(t)$ for the previous action via Eq. (6).
3. **Q-update**: Apply Eq. (7) to update $Q(s_t, a_t)$.
4. **Discretize current state** $s_{t+1}$ into $(h_{bin}, f_{near}, m_{bin})$.
5. **Action selection** (ε-greedy):
   - With probability $\epsilon_{greedy}$: choose a uniformly random action from {UP, DOWN, LEFT, RIGHT, STAY, EAT}.
   - Otherwise: choose $a^* = \arg\max_a Q(s_{t+1}, a)$.
   - **Constraint**: EAT is only selectable if food is at the agent's current position; if $a^* =$ EAT but no food is present, fall back to the next-best action.
6. **Emergent behavior**: Over many episodes, the agent learns that:
   - Eating when GLP-1 is already high yields diminished reward (satiety attenuation in Eq. 6), so it avoids overeating.
   - Letting energy drop too low yields penalties, so it forages proactively.
   - Maintaining microbiota health (regular eating) amplifies the SCFA→GLP-1 cascade, creating more reliable satiety signals and better reward calibration.
