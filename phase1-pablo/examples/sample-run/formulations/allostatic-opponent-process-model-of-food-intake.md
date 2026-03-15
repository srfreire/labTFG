# Allostatic Opponent-Process Model of Food Intake — Mathematical Formulations

## Formulation 1: Continuous Opponent-Process ODE with Allostatic Set-Point Drift

**Approach**: Coupled ordinary differential equations governing hedonic a-process, aversive b-process, and a slowly drifting allostatic reward set-point; action selection via gradient-based motivational drive.

**Based on**: Solomon & Corbit (1974) opponent-process dynamics; Koob & Le Moal (2001, 2008) allostatic extension.

### Variables

| Symbol | Name | Description | Type |
|--------|------|-------------|------|
| $a(t)$ | Primary hedonic process | Pleasure/reward response triggered by eating palatable food | Continuous, $\geq 0$ |
| $b(t)$ | Opponent aversive process | Counter-regulatory aversive state opposing $a(t)$ | Continuous, $\geq 0$ |
| $A(t)$ | Net affective state | Experienced hedonic tone: $A(t) = a(t) - b(t)$ | Continuous, $\in \mathbb{R}$ |
| $\theta(t)$ | Hedonic set-point | Allostatic reward baseline; drifts downward with chronic exposure | Continuous, $\leq \theta_0$ |
| $L(t)$ | Allostatic load | Cumulative dysregulatory burden on reward circuitry | Continuous, $\geq 0$ |
| $M(t)$ | Motivational drive to eat | Discrepancy between set-point and current affective state | Continuous, $\in \mathbb{R}$ |
| $S(t)$ | Food stimulus input | Binary or graded signal: 1 if agent eats palatable food, 0 otherwise | Binary / $\{0, 1\}$ |
| $\sigma(t)$ | Stress level | External uncontrollable stress impinging on the agent | Continuous, $\geq 0$ |
| $p$ | Food palatability | Intensity multiplier of the food reward stimulus | Continuous, $> 0$ |

### Parameters

| Symbol | Name | Default | Source |
|--------|------|---------|--------|
| $\alpha$ | Decay rate of a-process | 0.5 per time-step | Solomon & Corbit (1974): a-process is fast-decaying |
| $\beta$ | Decay rate of b-process | 0.1 per time-step | Solomon & Corbit (1974): b-process decays slowly ($\beta < \alpha$) |
| $\gamma_0$ | Initial coupling gain (a → b) | 0.3 | Solomon & Corbit (1974): opponent recruitment strength |
| $\delta$ | Coupling gain growth rate | 0.02 per eating episode | Koob & Le Moal (2001): b-process strengthens with repetition |
| $\lambda$ | Allostatic loading coefficient | 0.05 | Koob & Le Moal (2008): rate of set-point shift |
| $\rho$ | Set-point recovery rate | 0.005 per time-step | Koob & Le Moal (2008): slow, incomplete recovery |
| $\theta_0$ | Original homeostatic set-point | 1.0 | Normalised baseline |
| $\kappa$ | Stress amplification factor | 0.1 | Yau & Potenza (2013): stress accelerates allostatic load |
| $p_{\text{default}}$ | Default food palatability | 1.0 | Normalised |
| $M_{\text{thresh}}$ | Motivational threshold for eating | 0.3 | Derived from postulates P3–P4 |

### Equations

$$
\frac{da}{dt} = -\alpha \cdot a(t) + p \cdot S(t) \tag{1}
$$

$$
\frac{db}{dt} = -\beta \cdot b(t) + \gamma(t) \cdot a(t) \tag{2}
$$

$$
\gamma(t) = \gamma_0 + \delta \cdot N(t) \tag{3}
$$

where $N(t)$ is the cumulative number of eating episodes up to time $t$.

$$
A(t) = a(t) - b(t) \tag{4}
$$

$$
\frac{d\theta}{dt} = -\lambda \cdot b(t) + \rho \cdot (\theta_0 - \theta(t)) - \kappa \cdot \sigma(t) \tag{5}
$$

$$
L(t) = \theta_0 - \theta(t) \tag{6}
$$

$$
M(t) = \theta(t) - A(t) \tag{7}
$$

When $M(t) > 0$, the agent is in reward deficit relative to its (possibly shifted) set-point and is motivated to eat. As $\theta(t)$ drifts below $\theta_0$, eating is increasingly driven by negative reinforcement (restoring $A(t)$ to the lowered set-point) rather than hedonic pleasure above baseline (postulate P4).

### Decision Logic

Given the agent's current perception (position, nearby food locations, whether food is at current cell) and internal state $(a, b, \theta, N)$:

1. **Update internal dynamics** (Euler integration of Eqs. 1–2 with $S(t) = 0$ for the current step if not eating; Eq. 5 for set-point).
2. **Compute motivational drive** $M(t)$ via Eq. 7.
3. **If food is at current cell AND $M(t) > M_{\text{thresh}}$**:
   - Choose action = **EAT**.
   - (On the next `update` call, set $S = 1$ and re-integrate Eqs. 1–2.)
4. **Else if $M(t) > M_{\text{thresh}}$ AND food is visible in perception**:
   - Identify the nearest food cell.
   - Choose action = **MOVE** toward that food cell (up/down/left/right that minimises Manhattan distance).
5. **Else if $M(t) > M_{\text{thresh}}$ AND no food visible**:
   - Choose action = **MOVE** in a random exploratory direction.
6. **Else** ($M(t) \leq M_{\text{thresh}}$, drive is low):
   - Choose action = **STAY**.

After each action:
- On **EAT**: increment $N(t)$ by 1; set $S = 1$ for integration; update $\gamma$ via Eq. 3.
- On reward receipt (from environment): the reward signal is used as a proxy for palatability $p$ if variable.
- Integrate Eqs. 1, 2, 5 forward one time-step.

> **Key emergent behaviour**: Early on ($L \approx 0$), the agent eats when food is nearby and $M$ briefly exceeds threshold (positive reinforcement). Over many episodes, $\theta$ drifts down, $b$ grows stronger and slower to decay, and $M$ is chronically elevated — the agent compulsively seeks food to relieve persistent negative affect (negative reinforcement), consistent with postulates P3–P4.

---

## Formulation 2: Discrete Bayesian Belief-Utility Model with Affective Priors

**Approach**: Probabilistic decision-theoretic framework; the agent maintains Bayesian beliefs about its internal hedonic state and food availability, computing expected utility of each action under opponent-process-shaped utility functions that shift with allostatic load.

**Based on**: Solomon & Corbit (1974) for affective dynamics; Koob & Le Moal (2001, 2008) for allostatic reframing; Bayesian decision-theoretic formalisation derived from postulates P1–P4.

### Variables

| Symbol | Name | Description | Type |
|--------|------|-------------|------|
| $h_t$ | Hedonic state | Latent affective valence at discrete time $t$ | Continuous, $\in \mathbb{R}$ |
| $o_t$ | Opponent state | Latent aversive accumulator | Continuous, $\geq 0$ |
| $\theta_t$ | Allostatic set-point | Reward reference, updated via exponential moving average | Continuous, $\leq \theta_0$ |
| $r_t$ | Observed reward | Binary signal: 1 if agent ate and received food reward, 0 otherwise | $\{0, 1\}$ |
| $\mathbf{f}_t$ | Food belief vector | Probability of food existing at each visible cell | Vector, entries $\in [0,1]$ |
| $U_t(a)$ | Expected utility of action $a$ | Utility under current affective state and beliefs | Continuous |
| $D_t$ | Dysphoria index | $D_t = \max(0, \theta_t - h_t + o_t)$; drives negative-reinforcement motivation | Continuous, $\geq 0$ |

### Parameters

| Symbol | Name | Default | Source |
|--------|------|---------|--------|
| $\alpha_h$ | Hedonic decay rate | 0.6 | Solomon & Corbit (1974): fast a-process decay |
| $\alpha_o$ | Opponent decay rate | 0.15 | Solomon & Corbit (1974): slow b-process decay |
| $\gamma$ | Opponent recruitment gain | 0.4 | Solomon & Corbit (1974) |
| $\eta$ | Allostatic drift rate | 0.03 | Koob & Le Moal (2008) |
| $\theta_0$ | Baseline set-point | 1.0 | Normalised |
| $\phi$ | Palatability boost | 1.0 | Normalised stimulus intensity |
| $\xi$ | Stress-driven load increment | 0.05 | Yau & Potenza (2013) |
| $w_{\text{food}}$ | Utility weight for food-seeking | 2.0 | Derived from P3–P4: eating has high negative-reinforcement value |
| $w_{\text{explore}}$ | Utility weight for exploration | 0.5 | Baseline exploratory drive |
| $\tau$ | Softmax temperature | 0.2 | Controls stochasticity of action selection |
| $p_{\text{prior}}$ | Prior probability food exists in unseen cell | 0.1 | Environmental assumption |

### Equations

**Affective state update (discrete-time opponent process):**

$$
h_{t+1} = (1 - \alpha_h) \cdot h_t + \phi \cdot r_t \tag{1}
$$

$$
o_{t+1} = (1 - \alpha_o) \cdot o_t + \gamma \cdot h_t \tag{2}
$$

**Net affect and dysphoria:**

$$
A_t = h_t - o_t \tag{3}
$$

$$
D_t = \max\!\big(0,\; \theta_t - A_t\big) \tag{4}
$$

**Allostatic set-point drift:**

$$
\theta_{t+1} = \theta_t - \eta \cdot o_t + \rho \cdot (\theta_0 - \theta_t) - \xi \cdot \sigma_t \tag{5}
$$

where $\rho = 0.005$ is recovery and $\sigma_t$ is current stress.

**Bayesian food belief update:**

$$
P(F_c \mid \text{perception}_t) = \begin{cases} 1 & \text{if food observed at cell } c \\ 0 & \text{if cell } c \text{ observed empty} \\ p_{\text{prior}} & \text{if cell } c \text{ unobserved} \end{cases} \tag{6}
$$

**Expected utility of each action $a \in \{\text{up, down, left, right, stay, eat}\}$:**

$$
U_t(a) = w_{\text{food}} \cdot D_t \cdot \mathbb{E}\!\big[r_{t+1} \mid a, \mathbf{f}_t\big] + w_{\text{explore}} \cdot I(a) - c(a) \tag{7}
$$

where:
- $\mathbb{E}[r_{t+1} \mid a, \mathbf{f}_t]$ is the expected food reward if action $a$ is taken, computed from $\mathbf{f}_t$ (Eq. 6). For **EAT** at current cell with food: this equals 1. For a **MOVE** toward a cell $c$: this equals $P(F_c \mid \text{perception}_t)$ discounted by distance.
- $I(a)$ = information gain of action $a$ (number of new cells revealed by moving; 0 for STAY/EAT).
- $c(a)$ = action cost (0.01 for MOVE, 0 for STAY/EAT).

**Softmax action selection:**

$$
P(a \mid \text{state}_t) = \frac{\exp\!\big(U_t(a) / \tau\big)}{\sum_{a'} \exp\!\big(U_t(a') / \tau\big)} \tag{8}
$$

### Decision Logic

At each time-step:

1. **Perceive** environment: update $\mathbf{f}_t$ via Eq. 6 using visible cells.
2. **Update internal affective state**: compute $h_t, o_t$ via Eqs. 1–2 (using $r_t$ from previous step).
3. **Compute dysphoria** $D_t$ via Eq. 4. This is the core motivational driver.
4. **Compute expected utility** $U_t(a)$ for each of the 6 actions via Eq. 7:
   - If on a food cell: $U_t(\text{EAT}) = w_{\text{food}} \cdot D_t \cdot 1.0$, which is high when $D_t$ is large.
   - For each MOVE direction: expected reward is the food probability of the target cell discounted by distance, weighted by $D_t$.
   - STAY: $U_t = 0$ (no food reward, no exploration gain, no cost).
5. **Sample action** from softmax distribution (Eq. 8).
6. **After action and reward**: update allostatic set-point via Eq. 5.

> **Key distinction from Formulation 1**: Actions are selected *probabilistically* via softmax over expected utilities rather than deterministically via threshold comparison. The agent explicitly represents *uncertainty about food locations* and integrates it with affective drive. As allostatic load increases ($\theta_t$ drops), $D_t$ grows, causing the $w_{\text{food}} \cdot D_t$ term to dominate — the agent becomes increasingly food-focused and less exploratory, modelling the narrowing of the motivational repertoire seen in compulsive eating (P4).

---

## Formulation 3: Reinforcement-Learning Temporal-Difference Model with Opponent-Process Reward Shaping

**Approach**: Model-free temporal-difference (TD) reinforcement learning where the agent's *internal reward signal* is shaped by opponent-process dynamics and an allostatic baseline; the agent learns state-action values (Q-values) under a reward function that itself degrades with chronic consumption.

**Based on**: Solomon & Corbit (1974) for reward shaping; Koob & Le Moal (2001, 2008) for allostatic reward degradation; standard TD(0)/Q-learning framework applied with biologically-motivated internal reward (cf. Keramati & Gutkin, 2014, who model homeostatic RL; adapted here to allostatic opponent-process setting per Koob & Le Moal's framework).

### Variables

| Symbol | Name | Description | Type |
|--------|------|-------------|------|
| $Q(s, a)$ | Action-value function | Estimated long-run shaped reward for taking action $a$ in state $s$ | Table / continuous |
| $s_t$ | State | Agent's position + local food map + discretised internal state $(h_t^{\text{bin}}, o_t^{\text{bin}})$ | Discrete tuple |
| $\tilde{r}_t$ | Shaped internal reward | Opponent-process-modulated reward signal the agent actually experiences | Continuous |
| $r_t^{\text{ext}}$ | External reward | Raw environment reward (1 if ate food, 0 otherwise) | $\{0, 1\}$ |
| $h_t$ | Hedonic trace | Decaying trace of recent food rewards (a-process proxy) | Continuous, $\geq 0$ |
| $o_t$ | Opponent trace | Decaying aversive accumulator (b-process proxy) | Continuous, $\geq 0$ |
| $\theta_t$ | Allostatic baseline | Shifting reference for reward; degrades with chronic intake | Continuous |
| $N_t$ | Cumulative eating count | Total food consumption episodes to date | Integer, $\geq 0$ |

### Parameters

| Symbol | Name | Default | Source |
|--------|------|---------|--------|
| $\alpha_Q$ | Q-learning rate | 0.1 | Standard RL default |
| $\gamma_{\text{rl}}$ | Discount factor | 0.95 | Standard RL default |
| $\epsilon_0$ | Initial exploration rate | 0.2 | Epsilon-greedy baseline |
| $\alpha_h$ | Hedonic trace decay | 0.5 | Solomon & Corbit (1974) |
| $\alpha_o$ | Opponent trace decay | 0.1 | Solomon & Corbit (1974) |
| $g_0$ | Initial opponent gain | 0.3 | Solomon & Corbit (1974) |
| $\delta_g$ | Gain growth per episode | 0.01 | Koob & Le Moal (2001): b-process sensitisation |
| $\lambda$ | Allostatic drift rate | 0.02 | Koob & Le Moal (2008) |
| $\rho$ | Set-point recovery rate | 0.003 | Koob & Le Moal (2008): slow recovery |
| $\theta_0$ | Initial hedonic baseline | 0.0 | Normalised zero-baseline |
| $\kappa$ | Stress loading factor | 0.05 | Yau & Potenza (2013) |

### Equations

**Hedonic and opponent trace updates:**

$$
h_{t+1} = (1 - \alpha_h) \cdot h_t + r_t^{\text{ext}} \tag{1}
$$

$$
o_{t+1} = (1 - \alpha_o) \cdot o_t + g(N_t) \cdot h_t \tag{2}
$$

$$
g(N_t) = g_0 + \delta_g \cdot N_t \tag{3}
$$

**Allostatic baseline drift:**

$$
\theta_{t+1} = \theta_t - \lambda \cdot o_t + \rho \cdot (\theta_0 - \theta_t) - \kappa \cdot \sigma_t \tag{4}
$$

**Shaped internal reward (what the agent "feels"):**

$$
\tilde{r}_t = \big(r_t^{\text{ext}} + h_t - o_t\big) - \theta_t \tag{5}
$$

This reward signal captures three key dynamics:
- **Early regime** ($N_t$ small, $\theta_t \approx 0$, $o_t$ small): $\tilde{r}_t \approx r_t^{\text{ext}} + h_t > 0$ when eating → positive reinforcement.
- **Chronic regime** ($N_t$ large, $\theta_t \ll 0$, $o_t$ large): even without eating, $\tilde{r}_t = (0 + h_t - o_t) - \theta_t$. Since $o_t$ is large and $\theta_t$ is very negative, the agent experiences $\tilde{r}_t < 0$ during abstinence (aversive) and $\tilde{r}_t > 0$ when eating (relief) → negative reinforcement (P4).

**Q-learning update:**

$$
Q(s_t, a_t) \leftarrow Q(s_t, a_t) + \alpha_Q \Big[\tilde{r}_t + \gamma_{\text{rl}} \cdot \max_{a'} Q(s_{t+1}, a') - Q(s_t, a_t)\Big] \tag{6}
$$

**Exploration rate decay (modulated by dysphoria):**

$$
\epsilon_t = \epsilon_0 \cdot \exp\!\big(-0.01 \cdot N_t\big) \cdot \frac{1}{1 + |D_t|} \tag{7}
$$

where $D_t = \max(0, \theta_t - (h_t - o_t))$ is dysphoria. High dysphoria reduces exploration, modelling the motivational narrowing of compulsive eating.

### Decision Logic

At each time-step:

1. **Observe** perception: agent position, food locations in visible range → construct state $s_t$ as (position, local food bitmap, discretised $h_t$, discretised $o_t$).
2. **Update internal traces** $h_t, o_t$ via Eqs. 1–2 using previous step's $r_t^{\text{ext}}$.
3. **Update allostatic baseline** $\theta_t$ via Eq. 4.
4. **Compute shaped reward** $\tilde{r}_t$ from Eq. 5 for the last transition.
5. **Update Q-table** via Eq. 6.
6. **Select action** using $\epsilon$-greedy policy:
   - With probability $\epsilon_t$ (Eq. 7): choose a **random action** from {up, down, left, right, stay, eat}.
   - With probability $1 - \epsilon_t$: choose $a^* = \arg\max_a Q(s_t, a)$.
   - **Constraint**: EAT is only valid if food is at the current cell; otherwise the greedy selection is over the remaining 5 actions.
7. **Execute action**, receive $r_{t+1}^{\text{ext}}$ from environment.
8. **Increment** $N_t$ if action was EAT and food was consumed.

> **Key distinction from Formulations 1 & 2**: The agent *learns* its policy through experience rather than following a fixed motivational rule or computing expected utilities analytically. The opponent process and allostatic shift are embedded in the *reward function itself* (Eq. 5), not in the action-selection mechanism. This means the same Q-learning algorithm produces qualitatively different behaviour over time — initially learning to eat for pleasure, later learning to eat to avoid the aversive state — purely because the shaped reward landscape changes. This captures the insight from Koob & Le Moal (2008) that the *motivational substrate itself* is transformed by allostatic neuroadaptation. The discretisation of $(h_t, o_t)$ into bins for state representation allows tractable tabular RL while preserving the continuous opponent dynamics internally.
