# Homeostatic Regulation — Mathematical formulations

## Formulation 1: Proportional-Integral (PI) Negative-Feedback Controller
**Approach**: Continuous-time ODE-based control where the agent maintains an internal energy variable via proportional and integral error correction, selecting actions that maximize the effector control signal's alignment with the error.
**Based on**: Gross et al. (2024), Drengstig et al. (2012), npj Digital Medicine (2020); derived from postulates P1, P2, P3

### Variables
| Symbol | Name | Description | Type |
|--------|------|-------------|------|
| $A(t)$ | Regulated variable (energy) | Internal energy level of the agent | Continuous, $A \in [0, A_{\max}]$ |
| $s$ | Set point | Target energy level the agent seeks to maintain | Constant scalar |
| $e(t)$ | Error signal | Deviation from set point: $e(t) = s - A(t)$ | Signed scalar |
| $c_P(t)$ | Proportional control term | Instantaneous corrective drive proportional to error | Scalar |
| $c_I(t)$ | Integral control term | Accumulated error over time (integral memory) | Scalar |
| $c(t)$ | Total control signal | Combined drive: $c(t) = c_P(t) + c_I(t)$ | Scalar $\geq 0$ |
| $\mathbf{p}(t)$ | Agent position | $(x, y)$ coordinates on the grid | Discrete 2D |
| $\mathbf{R}$ | Perceived resources | Set of $(x_r, y_r)$ positions of nearby food items | Set of 2D coords |

### Parameters
| Symbol | Name | Default | Source |
|--------|------|---------|--------|
| $s$ | Energy set point | 80.0 (on a 0–100 scale) | Keramati & Gutkin (2011): mid-to-high satiety target |
| $k_P$ | Proportional gain | 0.5 | Tuned; consistent with PI models in npj Digital Medicine (2020) |
| $k_I$ | Integral gain | 0.05 | Tuned; lower than $k_P$ to prevent oscillation (Drengstig et al., 2012) |
| $d$ | Passive energy decay rate per tick | 1.0 | Models basal metabolic cost; Gross et al. (2024) |
| $\Delta_{\text{eat}}$ | Energy gained from eating one resource | 15.0 | Arbitrary but tuned to interaction with $d$ |
| $A_{\max}$ | Maximum energy | 100.0 | Normalization ceiling |
| $c_{I,\max}$ | Integral windup cap | 50.0 | Prevents runaway integral; standard engineering practice |

### Equations

$$
e(t) = s - A(t) \tag{1}
$$

$$
c_P(t) = k_P \cdot e(t) \tag{2}
$$

$$
c_I(t+1) = \mathrm{clamp}\!\bigl(c_I(t) + k_I \cdot e(t),\; -c_{I,\max},\; c_{I,\max}\bigr) \tag{3}
$$

$$
c(t) = c_P(t) + c_I(t) \tag{4}
$$

$$
A(t+1) = \mathrm{clamp}\!\bigl(A(t) - d + \Delta_{\text{eat}} \cdot \mathbf{1}[\text{ate}],\; 0,\; A_{\max}\bigr) \tag{5}
$$

$$
U_{\text{eat}} = c(t) \cdot \mathbf{1}[\text{food at } \mathbf{p}(t)] \tag{6}
$$

$$
U_{\text{move}}(\mathbf{p}') = c(t) \cdot \frac{1}{1 + \min_{r \in \mathbf{R}} \|\mathbf{p}' - r\|_1} \tag{7}
$$

$$
U_{\text{stay}} = -|e(t)| \cdot 0.1 \tag{8}
$$

### Decision logic

1. **Sense**: Read current energy $A(t)$, position $\mathbf{p}(t)$, nearby resource positions $\mathbf{R}$, and whether the agent ate last tick.
2. **Update internal state**: Compute $A(t)$ via Eq. (5). Compute error $e(t)$ via Eq. (1). Update proportional term via Eq. (2) and integral term via Eq. (3). Compute total control signal $c(t)$ via Eq. (4).
3. **If $e(t) \leq 0$** (energy at or above set point):
   - The agent has low drive. Select action **stay** (no foraging needed). If energy is significantly above set point ($e(t) < -10$), also prefer stay to avoid overshoot.
4. **If $e(t) > 0$** (energy below set point):
   a. **If food is at current position**: Compute $U_{\text{eat}}$ via Eq. (6). If $U_{\text{eat}} > 0$, select **eat**.
   b. **If food is visible but not at current position**: For each adjacent cell $\mathbf{p}'$ (up/down/left/right), compute $U_{\text{move}}(\mathbf{p}')$ via Eq. (7). Select the **move** action toward the cell with the highest utility.
   c. **If no food is visible**: Select a **random move** direction (exploration driven by nonzero $c(t)$).
5. **Tie-breaking**: Among equal-utility actions, choose uniformly at random.

---

## Formulation 2: Homeostatic Reinforcement Learning (Drive-Reduction MDP)
**Approach**: Probabilistic action selection via softmax over Q-values in a Markov Decision Process where reward is defined as reduction in a quadratic homeostatic drive function; Q-values are learned online via temporal-difference (TD) updates.
**Based on**: Keramati & Gutkin (2011); Yin (2025); derived from postulates P1, P2, P6

### Variables
| Symbol | Name | Description | Type |
|--------|------|-------------|------|
| $x(t)$ | Internal state (energy) | Current energy level of the agent | Continuous, $x \in [0, x_{\max}]$ |
| $s$ | Set point | Target energy level | Constant scalar |
| $D(x)$ | Drive function | Scalar discomfort/cost of being away from set point | Continuous $\geq 0$ |
| $r(t)$ | Reward | Drive reduction achieved by last action | Signed scalar |
| $Q(z, a)$ | Action-value function | Expected cumulative discounted drive reduction for taking action $a$ in discretized state $z$ | Tabular matrix |
| $z(t)$ | Discretized state | Tuple encoding binned energy and relative resource direction | Finite set |
| $\mathbf{p}(t)$ | Agent position | Grid coordinates | Discrete 2D |
| $\mathbf{R}$ | Perceived resources | Nearby food positions | Set of 2D coords |
| $\pi(a \mid z)$ | Policy | Probability of selecting action $a$ in state $z$ | Probability distribution |

### Parameters
| Symbol | Name | Default | Source |
|--------|------|---------|--------|
| $s$ | Energy set point | 80.0 | Keramati & Gutkin (2011) |
| $\phi$ | Drive weight | 1.0 | Single resource; Keramati & Gutkin (2011) use per-variable weights |
| $x_{\max}$ | Maximum energy | 100.0 | Normalization |
| $d$ | Passive energy decay per tick | 1.0 | Basal metabolism |
| $\Delta_{\text{eat}}$ | Energy from eating | 15.0 | Tuned |
| $\alpha$ | TD learning rate | 0.1 | Standard RL default; Sutton & Barto convention |
| $\gamma$ | Discount factor | 0.95 | Keramati & Gutkin (2011) use values in [0.9, 0.99] |
| $\beta$ | Softmax inverse temperature | 5.0 | Controls exploration–exploitation; moderate value |
| $n_{\text{bins}}$ | Energy discretization bins | 10 | Practical for tabular Q-learning |

### Equations

$$
D(x) = \phi \cdot (x - s)^2 \tag{1}
$$

$$
r(t) = D\bigl(x(t)\bigr) - D\bigl(x(t+1)\bigr) \tag{2}
$$

$$
x(t+1) = \mathrm{clamp}\!\bigl(x(t) - d + \Delta_{\text{eat}} \cdot \mathbf{1}[\text{ate}],\; 0,\; x_{\max}\bigr) \tag{3}
$$

$$
\delta(t) = r(t) + \gamma \max_{a'} Q\bigl(z(t+1), a'\bigr) - Q\bigl(z(t), a(t)\bigr) \tag{4}
$$

$$
Q\bigl(z(t), a(t)\bigr) \leftarrow Q\bigl(z(t), a(t)\bigr) + \alpha \cdot \delta(t) \tag{5}
$$

$$
\pi(a \mid z) = \frac{\exp\!\bigl(\beta \cdot Q(z, a)\bigr)}{\sum_{a'} \exp\!\bigl(\beta \cdot Q(z, a')\bigr)} \tag{6}
$$

State discretization:

$$
z(t) = \Bigl(\bigl\lfloor x(t) \cdot n_{\text{bins}} / x_{\max} \bigr\rfloor,\; \mathrm{dir}(\mathbf{p}(t), \mathbf{R})\Bigr) \tag{7}
$$

where $\mathrm{dir}(\mathbf{p}, \mathbf{R})$ encodes the relative direction to the nearest resource (one of 9 values: 8 compass directions + "none visible").

### Decision logic

1. **Sense**: Read current energy $x(t)$, position $\mathbf{p}(t)$, nearby resources $\mathbf{R}$, whether the agent ate last tick.
2. **Update energy**: Apply Eq. (3) to get $x(t+1)$ (or equivalently treat perception's energy as already updated).
3. **Compute reward**: Calculate $r(t)$ via Eqs. (1)–(2) using the energy before and after the last action.
4. **Compute discretized state**: Encode $z(t)$ via Eq. (7).
5. **TD update**: Compute TD error $\delta(t)$ via Eq. (4) and update Q-table via Eq. (5).
6. **Action selection**: Compute softmax probabilities $\pi(a \mid z(t))$ over all six actions {up, down, left, right, stay, eat} via Eq. (6). Sample action $a(t)$ from $\pi$.
   - **Constraint**: If no food is at the current position, set $Q(z, \text{eat}) = -\infty$ before computing softmax (eat is not feasible).
7. **Execute** the sampled action.

*Note*: Early in learning the agent explores broadly; as Q-values converge, the agent reliably moves toward food when $x < s$ and stays put when $x \approx s$, reproducing the drive-reduction prediction of Keramati & Gutkin (2011).

---

## Formulation 3: Multiplicative Homeostatic Scaling with Urgency Threshold
**Approach**: Algebraic rule-based agent inspired by homeostatic synaptic scaling; the agent maintains a multiplicative gain that scales action utilities, combined with a threshold-based urgency mechanism that switches between exploration and exploitation modes.
**Based on**: Turrigiano et al. (1998) — multiplicative scaling rule; Cannon (1932) — proportional response; derived from postulates P1, P2, P4, P5

### Variables
| Symbol | Name | Description | Type |
|--------|------|-------------|------|
| $A(t)$ | Regulated variable (energy) | Internal energy level | Continuous, $A \in [0, A_{\max}]$ |
| $s$ | Set point | Target energy level | Constant scalar |
| $g(t)$ | Homeostatic gain | Multiplicative scaling factor for behavioral activation | Continuous $> 0$ |
| $\bar{A}(t)$ | Smoothed energy (running average) | Exponential moving average of recent energy levels | Continuous |
| $u$ | Urgency | Binary mode indicator: foraging (urgent) vs. resting | $\{0, 1\}$ |
| $\mathbf{p}(t)$ | Agent position | Grid coordinates | Discrete 2D |
| $\mathbf{R}$ | Perceived resources | Nearby food positions | Set of 2D coords |

### Parameters
| Symbol | Name | Default | Source |
|--------|------|---------|--------|
| $s$ | Energy set point | 80.0 | Consistent with Formulations 1 & 2 |
| $A_{\max}$ | Maximum energy | 100.0 | Normalization |
| $d$ | Passive energy decay per tick | 1.0 | Basal metabolism |
| $\Delta_{\text{eat}}$ | Energy from eating | 15.0 | Tuned |
| $\tau$ | EMA smoothing constant | 0.2 | Controls memory of recent energy; inspired by firing-rate averaging in Turrigiano et al. (1998) |
| $\theta_{\text{low}}$ | Low urgency threshold | 0.6 · $s$ = 48.0 | Critical depletion level; triggers urgent foraging |
| $\theta_{\text{high}}$ | High satiety threshold | 0.95 · $s$ = 76.0 | Near set point; triggers resting |
| $g_{\min}$ | Minimum gain | 0.1 | Prevents complete behavioral shutdown |
| $g_{\max}$ | Maximum gain | 5.0 | Caps maximum behavioral activation |

### Equations

Energy dynamics:

$$
A(t+1) = \mathrm{clamp}\!\bigl(A(t) - d + \Delta_{\text{eat}} \cdot \mathbf{1}[\text{ate}],\; 0,\; A_{\max}\bigr) \tag{1}
$$

Smoothed energy (exponential moving average):

$$
\bar{A}(t+1) = (1 - \tau) \cdot \bar{A}(t) + \tau \cdot A(t+1) \tag{2}
$$

Multiplicative homeostatic gain (analogous to synaptic scaling):

$$
g(t) = \mathrm{clamp}\!\left(\frac{s}{\bar{A}(t) + \epsilon},\; g_{\min},\; g_{\max}\right) \tag{3}
$$

where $\epsilon = 1.0$ prevents division by zero. When $\bar{A}(t) < s$, gain $g > 1$ (upscaling, increased behavioral drive). When $\bar{A}(t) > s$, gain $g < 1$ (downscaling, reduced drive). This mirrors the multiplicative rule $w_i \leftarrow w_i \cdot \langle r^* \rangle / \langle r(t) \rangle$ from Turrigiano et al. (1998).

Urgency mode (hysteresis-based switching for anticipatory/reactive regulation per P5):

$$
u(t) = \begin{cases} 1 & \text{if } \bar{A}(t) < \theta_{\text{low}} \\ 0 & \text{if } \bar{A}(t) > \theta_{\text{high}} \\ u(t-1) & \text{otherwise (hysteresis)} \end{cases} \tag{4}
$$

Directional utility for moving toward nearest food:

$$
V(\mathbf{p}') = g(t) \cdot \frac{1}{1 + \min_{r \in \mathbf{R}} \|\mathbf{p}' - r\|_1} \tag{5}
$$

### Decision logic

1. **Sense**: Read current energy $A(t)$, position $\mathbf{p}(t)$, nearby resources $\mathbf{R}$, whether the agent ate last tick.
2. **Update internal state**: Compute energy via Eq. (1), smoothed energy via Eq. (2), gain via Eq. (3), urgency mode via Eq. (4).
3. **If $u(t) = 0$** (resting / satiated mode):
   - If food is at current position **and** $A(t) < s$: select **eat** (opportunistic feeding even in rest mode, since energy is still below set point).
   - Otherwise: select **stay**. The agent conserves energy and does not forage.
4. **If $u(t) = 1$** (urgent / foraging mode):
   a. **If food is at current position**: select **eat**.
   b. **If food is visible (R is non-empty)**:
      - Compute $V(\mathbf{p}')$ via Eq. (5) for each adjacent cell corresponding to actions {up, down, left, right}.
      - Select the **move** action with the highest $V(\mathbf{p}')$.
   c. **If no food is visible**:
      - Select a **random move** direction. The gain $g(t)$ does not affect direction choice here but ensures the agent is in active foraging mode rather than staying still.
5. **Tie-breaking**: Among equal-utility actions, choose uniformly at random.

*Key behavioral property*: The hysteresis in Eq. (4) produces **anticipatory regulation** (P5) — the agent keeps foraging past the low threshold until it reaches the high threshold, preventing oscillatory start-stop behavior. The multiplicative gain from Eq. (3) ensures that a severely depleted agent prioritizes the nearest food source more strongly (higher $g$), while a nearly-satiated agent in foraging mode is less aggressive in its approach — mirroring the proportional-response prediction (P2) and the multiplicative scaling biology of Turrigiano et al. (1998).
