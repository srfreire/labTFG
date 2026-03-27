# Hedonic Reward-Based Regulation of Food Intake — Mathematical Formulations

## Formulation 1: Dual-Process Algebraic Drive Model
**Approach**: Algebraic computation of a composite intake drive from separate homeostatic and hedonic signals with a multiplicative interaction term, used directly to threshold action selection.
**Based on**: Lutter & Nestler (2009); AJPH (2014); Toates (1986) incentive-motivation framework

### Variables
| Symbol | Name | Description | Type |
|--------|------|-------------|------|
| `H(t)` | Homeostatic hunger signal | Energy deficit proxy; increases each timestep without eating, resets upon eating | State (float in [0, 1]) |
| `R(t)` | Hedonic reward signal | Palatability-driven hedonic value of nearest visible food | Perception (float in [0, 1]) |
| `W(t)` | Wanting (incentive salience) | Motivational drive toward food; product of reward value and internal state | Derived (float >= 0) |
| `L(t)` | Liking (hedonic impact) | Anticipated pleasure of consumption at current hunger level | Derived (float >= 0) |
| `I(t)` | Total intake drive | Composite signal determining whether the agent seeks/consumes food | Derived (float >= 0) |
| `d_food` | Distance to nearest food | Manhattan distance on grid to nearest visible resource | Perception (int >= 0) |
| `p_food` | Palatability of nearest food | Intrinsic hedonic value of the nearest food item (0 = bland, 1 = highly palatable) | Perception (float in [0, 1]) |

### Parameters
| Symbol | Name | Default | Source |
|--------|------|---------|--------|
| `alpha` | Homeostatic weight | 0.4 | Derived from dual-process balance in Lutter & Nestler (2009): hedonic can override homeostatic, so `beta > alpha` |
| `beta` | Hedonic weight | 0.5 | Reflects hedonic dominance in palatable-food environments (Lutter & Nestler, 2009) |
| `gamma` | Interaction coefficient | 0.3 | Captures hunger-amplification of reward (AJPH, 2014) |
| `lambda_H` | Hunger growth rate | 0.05 per step | Biologically: hunger accumulates slowly; calibrated to ~20 steps to strong hunger |
| `theta_eat` | Eat threshold | 0.35 | Tuning parameter: agent eats when drive exceeds this |
| `theta_seek` | Seek threshold | 0.20 | Below eat threshold but above this: agent moves toward food |
| `H_reset` | Post-meal hunger reset | 0.05 | Small residual hunger after eating |

### Equations

**Eq. 1 — Hunger growth (no eating):**
`H(t+1) = min(1, H(t) + lambda_H)`
$$H(t+1) = \min\bigl(1,\; H(t) + \lambda_H\bigr) \quad \text{(if no eating at } t\text{)} \tag{1}$$

**Eq. 2 — Hunger reset (after eating):**
`H(t+1) = H_reset`
$$H(t+1) = H_{\text{reset}} \quad \text{(if eating at } t\text{)} \tag{2}$$

**Eq. 3 — Hedonic reward signal:**
`R(t) = p_food · exp(-0.3 · d_food)`
$$R(t) = p_{\text{food}} \cdot \exp\!\bigl(-0.3 \, d_{\text{food}}\bigr) \tag{3}$$

Equation (3) models sensory cue salience decaying with distance -- food cues (sight, smell) are stronger when proximal, consistent with sensory triggering of hedonic circuits (Kelley & Berridge, 2002).

**Eq. 4 — Wanting (incentive salience):**
`W(t) = R(t) × H(t)`
$$W(t) = R(t) \times H(t) \tag{4}$$

Equation (4) implements the Toates (1986) incentive-salience formula: wanting = reward value x motivational state (Berridge, 2004).

**Eq. 5 — Liking (hedonic impact):**
`L(t) = p_food · (0.6 + 0.4 · H(t))`
$$L(t) = p_{\text{food}} \cdot \bigl(0.6 + 0.4\,H(t)\bigr) \tag{5}$$

Liking is primarily driven by palatability but modulated upward by hunger (P4), with a floor ensuring palatable food is liked even when sated (P1).

**Eq. 6 — Total intake drive:**
`I(t) = alpha · H(t) + beta · L(t) + gamma · W(t)`
$$I(t) = \alpha \cdot H(t) + \beta \cdot L(t) + \gamma \cdot W(t) \tag{6}$$

This is the dual-process drive from AJPH (2014), where the three terms represent independent homeostatic drive, hedonic pleasure anticipation, and their multiplicative interaction (wanting).

### Decision logic
```
Given: perception = {position, nearby_food_positions, palatability_map, last_ate}
       internal  = {H(t)}

1. Update H(t) using Eq. (1) or (2) based on whether agent ate last step.
2. Identify nearest food item; compute d_food, p_food.
3. Compute R(t) via Eq. (3), W(t) via Eq. (4), L(t) via Eq. (5).
4. Compute I(t) via Eq. (6).

5. IF agent is adjacent to (or on) a food item AND I(t) >= theta_eat:
       -> Action = EAT
6. ELSE IF I(t) >= theta_seek AND food is visible:
       -> Action = MOVE toward nearest food (greedy Manhattan-distance reduction)
7. ELSE:
       -> Action = STAY (or random walk if no food visible)
```

---

## Formulation 2: Temporal-Difference Reward-Learning Agent
**Approach**: Reinforcement learning via temporal-difference (TD) value estimation with separate "liking" reward signals and dopaminergic "wanting" prediction errors driving action values.
**Based on**: Berridge & Robinson (1998) liking/wanting dissociation; Schultz reward-prediction-error framework as cited in deep report; Volkow et al. (2011) for tolerance dynamics

### Variables
| Symbol | Name | Description | Type |
|--------|------|-------------|------|
| `s_t` | State | Tuple: (agent position, hunger level `H_t`, relative food positions) | Perception |
| `a_t` | Action | One of {UP, DOWN, LEFT, RIGHT, STAY, EAT} | Decision |
| `Q(s,a)` | Action-value | Expected cumulative hedonic + homeostatic reward from taking `a` in `s` | Learned (float) |
| `r_like(t)` | Liking reward | Opioid-mediated hedonic pleasure upon eating; function of palatability | Signal (float) |
| `r_homeo(t)` | Homeostatic reward | Reward from reducing energy deficit | Signal (float) |
| `delta(t)` | Reward prediction error | Dopaminergic TD error; drives wanting updates | Derived (float) |
| `H_t` | Hunger level | Discretized energy deficit (0 = sated, `N_H` = starving) | State (int) |
| `D_2(t)` | D2 receptor availability | Reward sensitivity scalar; decreases with chronic overconsumption | State (float in (0, 1]) |

### Parameters
| Symbol | Name | Default | Source |
|--------|------|---------|--------|
| `alpha_Q` | Learning rate | 0.10 | Standard TD learning; moderate for non-stationary food environment |
| `gamma_TD` | Temporal discount factor | 0.90 | Agents prefer sooner rewards; consistent with impulsivity in hedonic eating (Volkow et al., 2011) |
| `epsilon` | Exploration rate | 0.10 | epsilon-greedy exploration |
| `kappa` | D2 downregulation rate | 0.02 | Slow tolerance; mirrors chronic D2 receptor loss in obesity (Volkow et al., 2011) |
| `kappa_r` | D2 recovery rate | 0.005 | Slower recovery than downregulation, asymmetric as in addiction literature |
| `w_like` | Liking reward weight | 0.6 | Hedonic component dominates reward signal (Berridge & Robinson, 1998) |
| `w_homeo` | Homeostatic reward weight | 0.4 | Homeostatic relief is rewarding but secondary in palatable contexts |
| `lambda_H` | Hunger growth rate | 0.05 per step | Same biological calibration as Formulation 1 |
| `p_max` | Maximum palatability reward | 1.0 | Normalized scale |

### Equations

**Composite reward upon eating:**

**Eq. 1 — Composite reward:**
`r(t) = D_2(t) · [w_like · r_like(t) + w_homeo · r_homeo(t)]`
$$r(t) = D_2(t) \cdot \bigl[\, w_{\text{like}} \cdot r_{\text{like}}(t) \;+\; w_{\text{homeo}} \cdot r_{\text{homeo}}(t) \,\bigr] \tag{1}$$

**Eq. 2 — Liking reward:**
`r_like(t) = p_food`
$$r_{\text{like}}(t) = p_{\text{food}} \tag{2}$$

**Eq. 3 — Homeostatic reward:**
`r_homeo(t) = H_t / N_H`
$$r_{\text{homeo}}(t) = H_t / N_H \tag{3}$$

Liking (Eq. 2) is purely palatability-driven, reflecting the opioid-mediated hedonic hotspot response (Berridge & Robinson, 1998; P6). Homeostatic reward (Eq. 3) is proportional to the deficit relieved. Both are gated by D2 receptor availability (Eq. 1), capturing blunted reward sensitivity in overconsumption states (Volkow et al., 2011; P5).

**Reward if not eating:**

**Eq. 4 — Non-eating reward:**
`r(t) = -0.01 · H_t`
$$r(t) = -0.01 \cdot H_t \tag{4}$$

A small negative signal proportional to hunger represents the aversive cost of unmet homeostatic need.

**TD prediction error (dopamine signal / wanting update):**

**Eq. 5 — TD prediction error:**
`delta(t) = r(t) + gamma_TD · max_a' Q(s_t+1, a') - Q(s_t, a_t)`
$$\delta(t) = r(t) + \gamma_{\text{TD}} \cdot \max_{a'} Q(s_{t+1}, a') - Q(s_t, a_t) \tag{5}$$

**Eq. 6 — Q-value update:**
`Q(s_t, a_t) <- Q(s_t, a_t) + alpha_Q · delta(t)`
$$Q(s_t, a_t) \leftarrow Q(s_t, a_t) + \alpha_Q \cdot \delta(t) \tag{6}$$

Equations (5-6) implement dopaminergic reward-prediction-error learning. Positive `delta` (reward better than expected) increases wanting for the chosen action; negative `delta` decreases it -- directly matching Berridge & Robinson's (1998) characterization of dopamine as mediating wanting, not liking.

**D2 receptor dynamics (tolerance):**

**Eq. 7 — D2 downregulation:**
`D_2(t+1) = D_2(t) - kappa · 1[ate palatable food at t] · p_food + kappa_r · (1 - D_2(t))`
$$D_2(t+1) = D_2(t) - \kappa \cdot \mathbb{1}[\text{ate palatable food at } t] \cdot p_{\text{food}} + \kappa_r \cdot (1 - D_2(t)) \tag{7}$$

**Eq. 8 — D2 clipping:**
`D_2(t+1) = clip(D_2(t+1), 0.2, 1.0)`
$$D_2(t+1) = \text{clip}\bigl(D_2(t+1),\; 0.2,\; 1.0\bigr) \tag{8}$$

Equation (7) models chronic D2 receptor downregulation from repeated palatable food intake (Volkow et al., 2011; P5) with slow recovery toward baseline. The floor of 0.2 in Eq. (8) prevents complete anhedonia.

**Hunger dynamics (same as Formulation 1):**

**Eq. 9 — Hunger dynamics:**
`H_t+1 = min(1, H_t + lambda_H) if no eat; H_t+1 = 0.05 if eat`
$$H_{t+1} = \min(1,\; H_t + \lambda_H) \quad \text{if no eat}; \quad H_{t+1} = 0.05 \quad \text{if eat} \tag{9}$$

### Decision logic
```
Given: perception = {position, nearby_food_positions, palatability_map, last_ate, reward_received}
       internal  = {Q-table, H_t, D2(t)}

1. Update H_t via Eq. (9).
2. Update D2(t) via Eq. (7)-(8).
3. Compute r(t) via Eq. (1)-(4) depending on whether agent ate.
4. Compute delta(t) via Eq. (5); update Q-table via Eq. (6).

5. With probability epsilon:
       -> Action = random choice from {UP, DOWN, LEFT, RIGHT, STAY, EAT}
6. Else:
       -> Enumerate feasible actions in current state s_t.
          (EAT is only feasible if on a food tile.)
       -> Action = argmax_a Q(s_t, a)

Note: State s_t is discretized as (relative_position_to_nearest_food, hunger_level_bin).
      Q-table is initialized to 0 for all entries.
```

---

## Formulation 3: ODE-Based Hedonic-Homeostatic Dynamical System
**Approach**: Continuous-time ordinary differential equations governing hunger, hedonic drive, and reward sensitivity, with action selection based on the instantaneous state of the dynamical system.
**Based on**: Lutter & Nestler (2009) dual-signal interaction; AJPH (2014) dynamic interplay model; Berridge (2004) incentive salience; exponential tolerance from Volkow et al. (2011)

### Variables
| Symbol | Name | Description | Type |
|--------|------|-------------|------|
| `h(t)` | Homeostatic deficit | Continuous hunger signal; rises without food, drops upon eating | State (float in [0, 1]) |
| `w(t)` | Wanting (incentive salience) | Dopaminergic motivational drive toward food; evolves dynamically | State (float >= 0) |
| `l(t)` | Liking (hedonic tone) | Opioid/endocannabinoid-mediated pleasure potential; modulated by recent consumption | State (float in [0, 1]) |
| `S(t)` | Sensory cue intensity | Strength of external food cues reaching the agent | Perception (float in [0, 1]) |
| `E(t)` | Eating event | Binary indicator: 1 if agent is eating at time `t`, 0 otherwise | Control (binary) |
| `Phi(t)` | Approach drive | Net behavioral drive combining wanting and hunger, determining movement | Derived (float) |

### Parameters
| Symbol | Name | Default | Source |
|--------|------|---------|--------|
| `tau_h` | Hunger time constant | 20 steps | ~20 steps to reach strong hunger; calibrated to grid-world timescale |
| `tau_w` | Wanting decay time constant | 8 steps | Wanting dissipates faster than hunger when cues vanish (Berridge, 2004) |
| `tau_l` | Liking recovery time constant | 15 steps | Hedonic capacity recovers moderately slowly (allosthetic satiety) |
| `mu` | Hunger-wanting coupling | 0.6 | Hunger amplifies wanting (P4); AJPH (2014) interaction |
| `sigma` | Sensory cue-wanting coupling | 0.8 | External cues are strong drivers of wanting (Kelley & Berridge, 2002) |
| `eta` | Palatability-liking coupling | 0.7 | Opioid hotspot response to taste (Berridge & Robinson, 1998) |
| `rho` | Satiation rate on liking | 0.4 | Eating temporarily reduces liking (sensory-specific satiety) |
| `k_h` | Hunger reduction upon eating | 0.5 | Partial hunger reset per eating event |
| `phi_eat` | Eat threshold on drive | 0.45 | Agent eats when combined drive is high enough and food is present |
| `phi_seek` | Seek threshold on drive | 0.25 | Agent approaches food above this drive |

### Equations

**Homeostatic deficit dynamics:**

**Eq. 1 — Homeostatic deficit dynamics:**
`dh/dt = (1 - h)/tau_h - k_h · E(t)`
$$\frac{dh}{dt} = \frac{1 - h}{\tau_h} - k_h \cdot E(t) \tag{1}$$

Hunger drifts toward maximum (1) with time constant `tau_h` and is reduced by eating events. This reflects continuous energy expenditure and meal-driven satiation (Lutter & Nestler, 2009).

**Sensory cue intensity (perception-derived):**

**Eq. 2 — Sensory cue intensity:**
`S(t) = p_food · exp(-0.3 · d_food)`
$$S(t) = p_{\text{food}} \cdot \exp\!\bigl(-0.3 \, d_{\text{food}}\bigr) \tag{2}$$

Same distance-decay model as Formulation 1; sensory cues trigger hedonic circuits at a distance (Kelley & Berridge, 2002).

**Wanting dynamics (dopaminergic incentive salience):**

**Eq. 3 — Wanting dynamics:**
`dw/dt = -w/tau_w + mu · h(t) · S(t) + sigma · S(t)`
$$\frac{dw}{dt} = -\frac{w}{\tau_w} + \mu \cdot h(t) \cdot S(t) + \sigma \cdot S(t) \tag{3}$$

Wanting decays in the absence of cues (first term), is driven by sensory cues (third term), and is amplified by hunger interacting with cues (second term). This captures the Toates (1986)/Berridge (2004) formulation: incentive salience = drive x stimulus, plus a direct cue-triggered component reflecting that wanting can occur even in sated states (P1).

**Liking dynamics (hedonic capacity):**

**Eq. 4 — Liking dynamics:**
`dl/dt = (1 - l)/tau_l - rho · E(t) · p_food + eta · p_food · E(t) · (1 - l)`
$$\frac{d\ell}{dt} = \frac{1 - \ell}{\tau_\ell} - \rho \cdot E(t) \cdot p_{\text{food}} + \eta \cdot p_{\text{food}} \cdot E(t) \cdot (1 - \ell) \tag{4}$$

Liking recovers toward baseline (first term), is reduced by eating (sensory-specific satiety; second term), but is also boosted by the hedonic impact of palatable food during consumption (third term), especially when liking is below ceiling. The net effect: eating highly palatable food initially sustains liking, but repeated consumption within a short window drives it down -- modeling the "dessert stomach" phenomenon followed by eventual satiation.

**Approach drive (behavioral output):**

**Eq. 5 — Approach drive:**
`Phi(t) = w(t) + 0.3 · h(t)`
$$\Phi(t) = w(t) + 0.3 \cdot h(t) \tag{5}$$

The behavioral drive is primarily wanting-driven (dopaminergic motivation), with a smaller direct homeostatic contribution ensuring that very hungry agents still seek food even without strong cues.

**Eat drive:**

**Eq. 6 — Eat drive:**
`Phi_eat(t) = w(t) · l(t) + 0.4 · h(t)`
$$\Phi_{\text{eat}}(t) = w(t) \cdot \ell(t) + 0.4 \cdot h(t) \tag{6}$$

The decision to consume requires both wanting and liking to be present (their product), plus homeostatic pressure. This ensures that an agent with high wanting but depleted liking (sensory-specific satiety) will not eat -- capturing the liking/wanting dissociation (P2, Berridge & Robinson, 1998).

### Decision logic
```
Given: perception = {position, nearby_food_positions, palatability_map, ate_last_step}
       internal  = {h, w, l} (continuous ODE state variables)

1. Compute S(t) via Eq. (2) from perception.
2. Set E(t) = 1 if agent ate last step, else E(t) = 0.
3. Integrate ODEs forward one timestep (Euler method, dt = 1):
       h(t+1) = h(t) + dt * [(1 - h(t)) / tau_h  -  k_h * E(t)]
       w(t+1) = w(t) + dt * [-w(t) / tau_w  +  mu * h(t) * S(t)  +  sigma * S(t)]
       l(t+1) = l(t) + dt * [(1 - l(t)) / tau_l  -  rho * E(t) * p_food  +  eta * p_food * E(t) * (1 - l(t))]
   Clip all to [0, 1].

4. Compute Phi(t) via Eq. (5), Phi_eat(t) via Eq. (6).

5. IF agent is on a food tile AND Phi_eat(t) >= phi_eat:
       -> Action = EAT
6. ELSE IF Phi(t) >= phi_seek AND food is visible:
       -> Action = MOVE toward nearest food (greedy step reducing Manhattan distance)
7. ELSE IF Phi(t) < phi_seek:
       -> Action = random walk (MOVE in random direction) or STAY
8. TIE-BREAKING: if multiple food items visible and equidistant, prefer higher palatability.
```

### Emergent Behaviors
- **Hedonic overeating (P1, P3):** When `p_food` is high, `S(t)` and thus `w(t)` remain elevated even at low `h`, driving consumption beyond homeostatic need.
- **Sensory-specific satiety:** Repeated eating of the same food depletes `l(t)` via the `-rho` term, eventually making `Phi_eat` fall below threshold even if wanting persists.
- **Hunger amplification (P4):** The `mu · h(t) · S(t)` term in Eq. (3) means hungry agents develop much stronger wanting in response to cues.
- **Cue-triggered wanting without hunger (P1):** The `sigma · S(t)` term drives wanting even when `h ~ 0`, modeling externally triggered hedonic eating.
