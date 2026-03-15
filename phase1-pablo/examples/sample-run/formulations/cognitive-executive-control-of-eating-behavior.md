# Cognitive Executive Control of Eating Behavior — Mathematical Formulations

## Formulation 1: Triadic Drift-Diffusion Model of Eat/Restrain Decisions
**Approach**: Stochastic evidence-accumulation (drift-diffusion) where a decision variable integrating reward drive, executive control, and valuation drifts toward an "eat" or "restrain" boundary over deliberation time.
**Based on**: Triadic brain-systems model (ScienceDirect / Current Opinion in Behavioral Sciences, 2022; APA PsycNet, 2023), inhibitory-control threshold concept (CORE / Frontiers in Psychology, 2016), and drift-diffusion decision modeling tradition applied to food choice.

### Variables
| Symbol | Name | Description | Type |
|--------|------|-------------|------|
| $x(t)$ | Decision variable | Accumulated evidence favoring eating (+) vs. restraint (−) at deliberation time $t$ | State (continuous) |
| $R$ | Reward drive | Hedonic/reward activation elicited by current food cue (striatum, OFC) | Perception-derived (continuous, ≥ 0) |
| $C$ | Executive control signal | Current effective cognitive control capacity (DLPFC-mediated) | Internal state (continuous, ≥ 0) |
| $V$ | Valuation bias | Net goal-congruent valuation: positive = long-term health goal active, negative = immediate gratification bias | Internal state (continuous) |
| $H$ | Homeostatic hunger | Physiological hunger/energy-deficit signal | Internal state (continuous, 0–1) |
| $\sigma$ | Noise intensity | Stochastic variability in the evidence accumulation (captures moment-to-moment fluctuation) | Parameter |
| $a_{eat}$ | Eat boundary | Threshold for committing to eat action | Parameter |
| $a_{restrain}$ | Restrain boundary | Threshold for committing to restrain (negative boundary) | Parameter |
| $A$ | Action | Chosen action: eat, move toward food, move away, or stay | Output (discrete) |

### Parameters
| Symbol | Name | Default | Source |
|--------|------|---------|--------|
| $\alpha$ | Reward weight | 1.0 | Triadic model (ScienceDirect, 2022) — reward system weighting |
| $\beta$ | Control weight | 1.2 | Set > $\alpha$ reflecting effective top-down regulation in healthy individuals (Springer, 2021) |
| $\gamma$ | Valuation weight | 0.5 | Intermediate weighting (ScienceDirect, 2022) |
| $\eta$ | Hunger amplification | 0.8 | Homeostatic drive scaling; moderate baseline (Springer, 2021) |
| $\sigma$ | Noise intensity | 0.3 | Standard DDM noise range |
| $a_{eat}$ | Eat boundary | 1.0 | Normalized threshold |
| $a_{restrain}$ | Restrain boundary | −1.0 | Symmetric boundary |
| $\delta_C$ | Control depletion rate | 0.05 | Per-timestep depletion of $C$ under cognitive load (ScienceDirect / Appetite, 2017) |
| $\rho_C$ | Control recovery rate | 0.03 | Per-timestep recovery of $C$ when not engaged with food cues |
| $C_{max}$ | Max control capacity | 1.0 | Normalized ceiling |
| $C_0$ | Initial control capacity | 0.8 | Trait-level baseline for healthy individual (PMC, 2017) |

### Equations

**Drift rate (deterministic component):**
$$
\nu = \alpha \cdot R + \eta \cdot H - \beta \cdot C + \gamma \cdot V \tag{1}
$$

Positive $\nu$ drifts toward eating; negative $\nu$ drifts toward restraint.

**Evidence accumulation (per deliberation micro-step $\Delta t$):**
$$
x(t + \Delta t) = x(t) + \nu \cdot \Delta t + \sigma \cdot \sqrt{\Delta t} \cdot \xi, \quad \xi \sim \mathcal{N}(0,1) \tag{2}
$$

**Decision rule:**
$$
A =
\begin{cases}
\text{eat} & \text{if } x(t) \geq a_{eat} \\
\text{restrain (stay/move away)} & \text{if } x(t) \leq a_{restrain}
\end{cases} \tag{3}
$$

**Executive control dynamics (across simulation timesteps):**
$$
C_{t+1} = \min\!\Big(C_{max},\ C_t - \delta_C \cdot \mathbb{1}[\text{food cue present}] + \rho_C \cdot \mathbb{1}[\text{no food cue}]\Big) \tag{4}
$$

**Valuation update (reward-learning):**
$$
V_{t+1} = V_t + \lambda_V \cdot (r_t^{health} - r_t^{hedonic}) \tag{5}
$$
where $r_t^{health}$ is the health-goal reward signal and $r_t^{hedonic}$ is the hedonic reward from eating, and $\lambda_V = 0.1$ is a learning rate.

**Hunger dynamics:**
$$
H_{t+1} = \min\!\Big(1,\ H_t + \delta_H - \phi \cdot \mathbb{1}[\text{ate at } t]\Big) \tag{6}
$$
with $\delta_H = 0.02$ (hunger increase per step) and $\phi = 0.4$ (hunger reduction from eating).

### Decision logic

```
At each simulation timestep:

1. PERCEIVE: Observe position, nearby food items (food_cue_present, food_distance),
   hunger H, whether ate last step.

2. COMPUTE REWARD DRIVE R:
   R = food_cue_salience / (1 + food_distance)
   # food_cue_salience ∈ {0.3 (low-cal), 1.0 (high-cal)}

3. UPDATE CONTROL C using Eq. (4).

4. UPDATE HUNGER H using Eq. (6).

5. COMPUTE DRIFT RATE ν using Eq. (1).

6. RUN EVIDENCE ACCUMULATION (Eq. 2) for N_micro = 10 micro-steps:
   x = 0  # start at neutral
   for i in 1..N_micro:
       x += ν * Δt + σ * sqrt(Δt) * random_normal()
       if x >= a_eat:  → decision = EAT; break
       if x <= a_restrain: → decision = RESTRAIN; break
   if no boundary reached: decision = UNDECIDED

7. SELECT ACTION:
   if decision == EAT:
       if adjacent_to_food: action = EAT
       else: action = MOVE toward nearest food
   elif decision == RESTRAIN:
       if food_distance < 2: action = MOVE away from food
       else: action = STAY
   else (UNDECIDED):
       action = STAY  # deliberation continues

8. AFTER ACTION: Update V using Eq. (5) based on reward received.
```

---

## Formulation 2: Inhibitory Control Threshold Model with Resource Depletion (Algebraic/Threshold)
**Approach**: Deterministic threshold comparison where eating occurs when food-cue salience exceeds a dynamically depleting inhibitory control resource, with separate modular contributions from each executive function component (inhibiting, updating, shifting).
**Based on**: Inhibitory control failure threshold (CORE / Frontiers in Psychology, 2016), unity/diversity EF model applied to eating (ScienceDirect / Appetite, 2017), ego-depletion-adjacent resource concept (MDPI / Nutrients, 2024), DLPFC hypoactivity (Springer, 2021).

### Variables
| Symbol | Name | Description | Type |
|--------|------|-------------|------|
| $IC$ | Inhibitory control resource | Current available inhibitory capacity (depletes with use, recovers with rest) | Internal state (continuous, 0–1) |
| $WM$ | Working memory load | Current working memory occupation (higher = fewer resources for dietary goals) | Internal state (continuous, 0–1) |
| $CF$ | Cognitive flexibility | Ability to shift eating strategy in response to context changes | Internal state (continuous, 0–1) |
| $S$ | Food-cue salience | Perceptual salience of nearby food cue | Perception-derived (continuous, ≥ 0) |
| $H$ | Hunger | Homeostatic hunger drive | Internal state (continuous, 0–1) |
| $E_{aff}$ | Affective state | Emotional valence; negative values represent stress/negative affect | Internal state (continuous, −1 to 1) |
| $G$ | Goal activation | Strength of active dietary goal in working memory | Internal state (continuous, 0–1) |
| $\Theta$ | Effective threshold | Net self-regulation threshold that salience must exceed to trigger eating | Computed (continuous) |

### Parameters
| Symbol | Name | Default | Source |
|--------|------|---------|--------|
| $IC_0$ | Baseline inhibitory capacity | 0.75 | Healthy-weight norm (CORE, 2016) |
| $\delta_{IC}$ | IC depletion per food encounter | 0.08 | Estimated from repeated inhibition cost (ScienceDirect / Appetite, 2017) |
| $\rho_{IC}$ | IC recovery rate (per no-food step) | 0.04 | Half the depletion rate; asymmetric recovery (MDPI / Nutrients, 2024) |
| $w_{IC}$ | Weight of IC in threshold | 0.5 | Primary EF component for eating (Wiley, 2023) |
| $w_{WM}$ | Weight of WM-supported goal | 0.25 | Secondary contribution (PMC, 2017) |
| $w_{CF}$ | Weight of cognitive flexibility | 0.15 | Tertiary contribution (ScienceDirect / Appetite, 2017) |
| $w_{aff}$ | Affective modulation weight | 0.10 | Stress/affect reduces threshold (MDPI / Nutrients, 2024) |
| $\kappa$ | Hunger amplification of salience | 0.6 | Hunger boosts effective salience (Springer, 2021) |
| $S_{high}$ | High-calorie food salience | 1.0 | Maximum salience (normalized) |
| $S_{low}$ | Low-calorie food salience | 0.4 | Lower hedonic value |
| $G_0$ | Baseline goal activation | 0.6 | Moderate dietary restraint intention |

### Equations

**Effective food-cue salience (hunger-modulated):**
$$
S_{eff} = S \cdot (1 + \kappa \cdot H) \tag{1}
$$

**Goal activation (maintained by working memory):**
$$
G_t = G_0 \cdot (1 - WM_t) \tag{2}
$$
When working memory is loaded ($WM$ high), dietary goal activation $G$ drops.

**Effective self-regulation threshold:**
$$
\Theta = w_{IC} \cdot IC_t + w_{WM} \cdot G_t + w_{CF} \cdot CF_t + w_{aff} \cdot \max(0, E_{aff,t}) \tag{3}
$$

Note: positive $E_{aff}$ contributes to threshold (better regulation); negative affect contributes 0 and instead amplifies salience:

**Affect-adjusted salience:**
$$
S^* = S_{eff} \cdot (1 + |\min(0, E_{aff,t})|) \tag{4}
$$

**Eat/restrain decision:**
$$
\text{Decision} =
\begin{cases}
\text{EAT} & \text{if } S^* > \Theta \text{ and adjacent to food} \\
\text{APPROACH} & \text{if } S^* > \Theta \text{ and not adjacent} \\
\text{RESTRAIN} & \text{if } S^* \leq \Theta
\end{cases} \tag{5}
$$

**Inhibitory control depletion/recovery:**
$$
IC_{t+1} = \text{clip}\!\Big(IC_t - \delta_{IC} \cdot \mathbb{1}[S > 0] + \rho_{IC} \cdot \mathbb{1}[S = 0],\ 0,\ 1\Big) \tag{6}
$$

**Hunger dynamics:**
$$
H_{t+1} = \text{clip}\!\Big(H_t + 0.02 - 0.5 \cdot \mathbb{1}[\text{ate}],\ 0,\ 1\Big) \tag{7}
$$

**Affective state dynamics (simplified):**
$$
E_{aff,t+1} = E_{aff,t} + 0.05 \cdot (\mathbb{1}[\text{ate healthy}] - \mathbb{1}[\text{ate unhealthy}]) + 0.01 \cdot \text{noise} \tag{8}
$$

**Cognitive flexibility adaptation:**
$$
CF_{t+1} =
\begin{cases}
CF_t + 0.05 & \text{if context changed and agent adapted (chose differently)} \\
CF_t - 0.03 & \text{if context changed and agent perseverated} \\
CF_t & \text{otherwise}
\end{cases} \tag{9}
$$

### Decision logic

```
At each simulation timestep:

1. PERCEIVE: Observe position, nearby food items with types (high-cal/low-cal),
   distances, whether ate last step and what type.

2. COMPUTE SALIENCE:
   For nearest food item:
     S = S_high if high-calorie else S_low
     S = S / (1 + distance_to_food)   # decays with distance
   If no food visible: S = 0

3. COMPUTE S_eff using Eq. (1) with current H.

4. COMPUTE S* using Eq. (4) with current E_aff.

5. COMPUTE GOAL ACTIVATION G using Eq. (2) with current WM.
   WM increases by 0.1 if multiple food types visible (load from choice conflict),
   otherwise decays by 0.05 toward 0.

6. COMPUTE THRESHOLD Θ using Eq. (3).

7. COMPARE S* vs Θ using Eq. (5):
   if S* > Θ:
       if adjacent to food: action = EAT
       else: action = MOVE toward nearest food
   else:
       if food within distance 2 and S* > 0.8 * Θ:
           action = STAY  # borderline, deliberating
       else:
           action = MOVE toward exploration / away from food

8. UPDATE INTERNAL STATES:
   - IC via Eq. (6)
   - H via Eq. (7)
   - E_aff via Eq. (8)
   - CF via Eq. (9): track if food layout changed and whether agent
     switched strategy (e.g., previously approached, now restrained)

9. RECORD: Log action and reward for learning.
```

---

## Formulation 3: Bayesian Goal-Inference Model with Executive Capacity Prior
**Approach**: Probabilistic (Bayesian) framework where the agent maintains a posterior belief over whether to pursue a "hedonic eating" goal vs. a "dietary restraint" goal, with executive function capacity encoded as a prior favoring restraint and sensory evidence (food cues, hunger) updating beliefs toward eating.
**Based on**: Valuation integration in the triadic model (ScienceDirect, 2022; APA PsycNet, 2023), EF as goal-maintenance mechanism (ScienceDirect / Appetite, 2017), working-memory-supported dietary goals (PMC, 2017), Bayesian brain hypothesis applied to decision-making.

### Variables
| Symbol | Name | Description | Type |
|--------|------|-------------|------|
| $p_{eat,t}$ | Posterior probability of eating goal | Agent's current belief that eating is the correct action | Internal state (continuous, 0–1) |
| $p_{restrain,t}$ | Posterior probability of restraint goal | $1 - p_{eat,t}$ | Internal state (continuous, 0–1) |
| $\pi_0$ | Prior toward restraint | Executive-control-derived prior favoring dietary restraint | Internal state (continuous, 0–1) |
| $L_{eat}$ | Likelihood of evidence given eat-goal | How well current sensory evidence (food cues, hunger) fits the eating goal | Computed (continuous) |
| $L_{restrain}$ | Likelihood of evidence given restrain-goal | How well current state fits restraint goal | Computed (continuous) |
| $H$ | Hunger | Homeostatic hunger signal | Internal state (continuous, 0–1) |
| $S$ | Food-cue salience | Perceived food salience | Perception-derived (continuous, ≥ 0) |
| $IC$ | Inhibitory control | Current inhibitory capacity, shapes prior | Internal state (continuous, 0–1) |
| $WM$ | Working memory | Current WM availability, supports goal maintenance | Internal state (continuous, 0–1) |
| $Q_{eat}$ | Expected value of eating | Learned expected reward from eating | Internal state (continuous) |
| $Q_{restrain}$ | Expected value of restraining | Learned expected reward from restraining | Internal state (continuous) |

### Parameters
| Symbol | Name | Default | Source |
|--------|------|---------|--------|
| $IC_0$ | Baseline inhibitory control | 0.75 | Healthy norm (CORE, 2016) |
| $WM_0$ | Baseline working memory | 0.70 | Moderate capacity (PMC, 2017) |
| $\tau$ | Softmax temperature | 0.2 | Controls action stochasticity |
| $\alpha_{learn}$ | Q-value learning rate | 0.1 | Standard RL learning rate |
| $\lambda_{hunger}$ | Hunger weight in likelihood | 1.5 | Hunger strongly signals eat-goal (Springer, 2021) |
| $\lambda_{cue}$ | Cue salience weight in likelihood | 1.0 | Food cue contribution |
| $\lambda_{IC}$ | IC weight in prior | 2.0 | Strong effect of IC on prior (Wiley, 2023; CORE, 2016) |
| $\lambda_{WM}$ | WM weight in prior | 1.0 | WM supports goal maintenance (ScienceDirect / Appetite, 2017) |
| $\delta_{IC}$ | IC depletion rate | 0.06 | Per food-encounter depletion |
| $\rho_{IC}$ | IC recovery rate | 0.03 | Recovery when not encountering food |
| $p_{eat,0}$ | Initial eating probability | 0.3 | Prior starts favoring restraint |

### Equations

**Prior (executive control shapes prior toward restraint):**
$$
\pi_{restrain,t} = \sigma\!\Big(\lambda_{IC} \cdot IC_t + \lambda_{WM} \cdot WM_t\Big) \tag{1}
$$
$$
\pi_{eat,t} = 1 - \pi_{restrain,t} \tag{2}
$$
where $\sigma(\cdot)$ is the logistic sigmoid function $\sigma(z) = 1/(1+e^{-z})$.

**Likelihood (sensory evidence favors eating when food cues and hunger are high):**
$$
L_{eat,t} = \sigma\!\Big(\lambda_{hunger} \cdot H_t + \lambda_{cue} \cdot S_t\Big) \tag{3}
$$
$$
L_{restrain,t} = 1 - L_{eat,t} \tag{4}
$$

**Posterior (Bayes' rule):**
$$
p_{eat,t} = \frac{\pi_{eat,t} \cdot L_{eat,t}}{\pi_{eat,t} \cdot L_{eat,t} + \pi_{restrain,t} \cdot L_{restrain,t}} \tag{5}
$$

**Value-modulated action probability (posterior weighted by learned values):**
$$
U_{eat,t} = p_{eat,t} \cdot Q_{eat,t} \tag{6}
$$
$$
U_{restrain,t} = (1 - p_{eat,t}) \cdot Q_{restrain,t} \tag{7}
$$

**Softmax action selection:**
$$
P(\text{choose eat}) = \frac{e^{U_{eat,t}/\tau}}{e^{U_{eat,t}/\tau} + e^{U_{restrain,t}/\tau}} \tag{8}
$$

**Q-value updates (after observing reward $r_t$):**
$$
Q_{eat,t+1} = Q_{eat,t} + \alpha_{learn} \cdot \mathbb{1}[\text{ate}] \cdot (r_t - Q_{eat,t}) \tag{9}
$$
$$
Q_{restrain,t+1} = Q_{restrain,t} + \alpha_{learn} \cdot \mathbb{1}[\text{restrained}] \cdot (r_t - Q_{restrain,t}) \tag{10}
$$

**IC dynamics:**
$$
IC_{t+1} = \text{clip}\!\Big(IC_t - \delta_{IC} \cdot \mathbb{1}[\text{food cue present}] + \rho_{IC} \cdot \mathbb{1}[\text{no food cue}],\ 0,\ 1\Big) \tag{11}
$$

**WM dynamics (loaded by environmental complexity):**
$$
WM_{t+1} = \text{clip}\!\Big(WM_t - 0.05 \cdot n_{food\_types} + 0.03 \cdot \mathbb{1}[\text{no food visible}],\ 0.1,\ 1\Big) \tag{12}
$$
where $n_{food\_types}$ is the number of distinct food types visible (more types = more WM load from choice conflict).

**Hunger dynamics:**
$$
H_{t+1} = \text{clip}\!\Big(H_t + 0.02 - 0.45 \cdot \mathbb{1}[\text{ate}],\ 0,\ 1\Big) \tag{13}
$$

### Decision logic

```
At each simulation timestep:

1. PERCEIVE: Observe position, nearby food items (types, distances),
   hunger H, whether ate last step, reward received.

2. COMPUTE FOOD-CUE SALIENCE:
   S = max over visible food items of:
       food_hedonic_value / (1 + distance)
   # food_hedonic_value: 1.0 for high-cal, 0.4 for low-cal
   If no food visible: S = 0

3. COMPUTE PRIOR using Eqs. (1)-(2) with current IC and WM.

4. COMPUTE LIKELIHOOD using Eqs. (3)-(4) with current H and S.

5. COMPUTE POSTERIOR p_eat using Eq. (5).

6. COMPUTE UTILITIES U_eat and U_restrain using Eqs. (6)-(7).

7. SAMPLE ACTION using softmax Eq. (8):
   Draw random u ~ Uniform(0,1)
   if u < P(choose eat):
       goal = EAT
   else:
       goal = RESTRAIN

8. TRANSLATE GOAL TO GRID ACTION:
   if goal == EAT:
       if adjacent to food: action = EAT
       else: action = MOVE toward highest-salience food
   elif goal == RESTRAIN:
       if food is nearby (distance ≤ 3): action = MOVE away from food
       else: action = STAY or MOVE randomly (exploration)

9. RECEIVE REWARD r_t:
   # Reward structure: eating when hungry gives positive r,
   # eating high-cal when not hungry gives small hedonic r but
   #   negative health r; restraining when hungry gives negative r;
   #   restraining when not hungry gives positive r.

10. UPDATE Q-VALUES using Eqs. (9)-(10).

11. UPDATE INTERNAL STATES:
    - IC via Eq. (11)
    - WM via Eq. (12)
    - H via Eq. (13)
```
