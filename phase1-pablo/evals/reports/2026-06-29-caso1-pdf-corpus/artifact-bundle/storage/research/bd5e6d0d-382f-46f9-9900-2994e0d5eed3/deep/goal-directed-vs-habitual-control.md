# Goal-Directed vs. Habitual Control — Deep Research

## Foundations

The goal-directed vs. habitual control paradigm emerged from the animal learning and behavioral neuroscience traditions of the late 20th century, pioneered principally by **Anthony Dickinson** and **Bernard Balleine** through decades of rodent instrumental conditioning experiments. Their foundational insight was that instrumental behavior is not monolithic: actions can be governed either by flexible, prospective action–outcome reasoning (goal-directed) or by rigid, retrospective stimulus–response associations (habitual). The computational formalization of the distinction — mapping it onto the **model-based** vs. **model-free reinforcement learning** dichotomy — was carried forward prominently by **Nathaniel Daw**, **Peter Dayan**, and **Read Montague**, and has been extensively synthesized in the neuroeconomics framework of **Antonio Rangel**, **Colin Camerer**, and **P. Read Montague** (Rangel et al., 2008). A parallel synthesis applied specifically to feeding decisions was provided by Rangel (2013). The paradigm draws on three intellectual lineages: (1) behavioral psychology (Thorndike's law of effect, Tolman's cognitive maps); (2) computational reinforcement learning theory (temporal-difference learning, Bellman equations); and (3) systems neuroscience (basal ganglia–cortex circuit dissection).

---

## Postulates

**P1.** Behavior is controlled by at least two dissociable valuation systems — a goal-directed (model-based) system and a habitual (model-free) system — that compete and/or cooperate for action selection at any given moment. *(Rangel, Camerer & Montague, 2008)*

**P2.** The goal-directed system computes action value prospectively as: **V_GD(a|s) = Σ_o p(o|a,s) · r^D(o|s)**, where **p(o|a,s)** is a learned internal model of action–outcome contingencies and **r^D(o|s)** is the current desirability of outcome **o**; this value updates immediately when either the contingency or the outcome desirability changes. *(Rangel, 2013)*

**P3.** The habitual system computes action value retrospectively as a discounted average of historically experienced rewards, **V_H(a|s)**, without encoding an explicit model of what outcomes actions produce; this value does not update when outcome desirability changes unless the action is re-experienced under the new conditions. *(Rangel, 2013)*

**P4.** Goal-directed control predominates early in training and in novel environments; habitual control predominates after extensive, stable training — i.e., the balance of control shifts as a function of training history and environmental stability. *(Rangel, Camerer & Montague, 2008)*

**P5.** The behavioral signature of goal-directed control is **outcome devaluation sensitivity**: reducing the value of a rewarded outcome leads to an immediate reduction in the associated action's emission; habit-controlled behavior is insensitive to outcome devaluation. *(Rangel, Camerer & Montague, 2008)*

---

## Assumptions

- **Dual-system architecture**: There exist (at minimum) two functionally and neurally separable controllers, each computing action values through distinct algorithms.
- **Common currency of value**: Both systems ultimately output a scalar action value that enters a common action-selection mechanism (e.g., a softmax policy), enabling direct competition.
- **Stable internal model (GD)**: The goal-directed system maintains an explicit, updatable world model comprising both action–outcome transition probabilities **p(o|a,s)** and outcome reward functions **r^D(o|s)**.
- **Model-free averaging (Habit)**: The habitual system updates **V_H(a|s)** via incremental experience (e.g., TD-learning), without decomposing that value into its contingency and desirability components.
- **Training-dependent shift**: The relative weighting of goal-directed vs. habitual output is a function of the number of prior training trials and the consistency of the environment; extensive overtraining shifts control toward habitual.
- **Arbitration/mixing**: A higher-level arbitration or mixing mechanism determines what proportion of each controller's output is used for action selection (e.g., via reliability-weighted mixture or competitive inhibition).
- **State-dependent desirability**: The reward function **r^D(o|s)** used by the goal-directed system is sensitive to current internal states (e.g., satiety, physiological need), whereas the habit value **V_H(a|s)** reflects historical rewards and is not updated on-the-fly by internal state changes.
- **Separability of wanting and liking**: The experienced reward **r^O(o|s)** computed at outcome receipt is distinct from the decision-time desirability **r^D(o|s)**; this distinction maps onto Berridge's "wanting vs. liking" framework.

---

## Predictions

- **Outcome devaluation sensitivity**: A goal-directed agent reduces action frequency immediately following devaluation of the associated outcome (e.g., by satiation or taste-aversion pairing) without needing to re-experience the devalued outcome in the training context; a habitual agent does not.
- **Contingency degradation sensitivity**: Goal-directed agents reduce responding when the action–outcome contingency is degraded (i.e., when the outcome occurs equally in the absence of the action); habitual agents are insensitive to this.
- **Overtraining → habit**: After extensive training, an agent that was initially goal-directed becomes habit-dominant; devaluation sensitivity decreases as training trials increase.
- **Novel/high-stakes situations → goal-directed**: In novel environments or where outcomes carry high reward magnitude, goal-directed control is expected to dominate.
- **Time pressure → habit**: Under time pressure or cognitive load, agents rely more heavily on habitual responses.
- **Prefrontal lesions abolish goal-direction**: Damage to prelimbic/medial PFC or dorsomedial striatum should abolish sensitivity to devaluation, collapsing behavior onto habit-like patterns.
- **Dorsolateral striatum lesions impair habits**: Disruption of the dorsolateral striatum (DLS) should preserve devaluation sensitivity even after overtraining (eliminating habitual component).
- **Differential learning speeds**: Goal-directed values update immediately upon receiving new information about outcomes; habitual values update only gradually, tracking the running average of experienced reward.
- **Conflict behavior under controller mismatch**: When goal-directed and habitual controllers recommend different actions (e.g., in food choice where a habitual dessert choice conflicts with a health goal), response time and choice variability increase.

---

## Primary Locus

The paradigm maps onto distinct, dissociable neural circuits:

**Habitual (Model-Free) System:**
- **Dorsolateral striatum (DLS) / putamen**: Critical for stimulus–response habit learning and execution in both rodents and humans. Connected in loops with motor cortex, providing a mechanism through which cues trigger actions. *(Rangel, Camerer & Montague, 2008; Rangel, 2013)*
- **Infralimbic cortex (IL-PFC)**: Necessary for the establishment and deployment of habits; lesions restore goal-directed sensitivity in overtrained animals. *(Rangel, Camerer & Montague, 2008)*
- **Dopaminergic projections to DLS**: Thought to carry the teaching signal (TD prediction error) for updating model-free action values. *(Rangel, Camerer & Montague, 2008)*

**Goal-Directed (Model-Based) System:**
- **Dorsomedial striatum (DMS) / caudate nucleus**: Involved in representing action–outcome associations **p(o|a,s)**. *(Rangel, 2013)*
- **Prelimbic cortex (PL-PFC) / dorsolateral PFC (dlPFC)**: Required for expressing goal-directed, outcome-sensitive behavior; modulates vmPFC value signals to incorporate deferred outcomes. *(Rangel, 2013)*
- **Orbitofrontal cortex (OFC) / ventromedial PFC (vmPFC)**: Computes outcome desirability **r^D(o|s)** at the time of decision, integrating sensory, contextual, and internal-state inputs; activity decreases following experimental devaluation. *(Rangel, 2013)*
- **Hippocampus**: Contributes to tracking action–outcome associations, especially over longer temporal horizons; role less fully established. *(Rangel, 2013)*
- **Insula**: Involved in updating outcome value after changes in physiological states (e.g., satiety), likely via vmPFC connectivity. *(Rangel, 2013)*

**Shared/Arbitration:**
- **Nucleus accumbens / ventral striatum**: Involved in Pavlovian value, motivational salience, and potentially in arbitrating between controllers. *(Rangel, Camerer & Montague, 2008)*
- **Pre-SMA and bilateral inferior parietal sulcus**: Receive vmPFC value signals and implement comparative action selection, modulating motor cortex. *(Rangel, 2013)*

---

## Key Concepts

- **Goal-directed control**: Action selection governed by an explicit internal model linking actions to outcomes and outcomes to current desirability; sensitive to changes in either action–outcome contingency or outcome value.
- **Habitual control**: Action selection governed by stimulus–response associations whose strength reflects historically accumulated reward; insensitive to current outcome desirability (model-free).
- **Model-based control**: Equivalent computational term for goal-directed control; uses a forward model **p(o|a,s)** to simulate outcomes and compute prospective action values.
- **Model-free control**: Equivalent computational term for habitual control; caches and incrementally updates scalar action values directly from experienced reward, without decomposition.
- **Action–outcome (A–O) association**: A learned representation of the probabilistic contingency between a specific action and a specific outcome, **p(o|a,s)**; the core representational element of goal-directed control.
- **Stimulus–response (S–R) association**: A learned link between a stimulus/context and an action, indexed by cached value **V_H(a|s)**; the core representational element of habitual control.
- **Outcome desirability / r^D(o|s)**: The current subjective value of an outcome at decision time, sensitive to present internal states; used by the goal-directed system.
- **Experienced reward / r^O(o|s)**: The hedonic value of an outcome as evaluated when it is received; used by both systems for learning but distinct from decision-time desirability.
- **Outcome devaluation**: Experimental procedure that reduces the value of a specific outcome (by satiation, taste aversion, or pairings with aversion) to dissociate goal-directed from habitual control.
- **Contingency degradation**: Experimental procedure that reduces the correlation between action and outcome (outcome delivered freely without action) to test action–outcome sensitivity.
- **Temporal difference (TD) learning**: The class of model-free algorithms used to incrementally update **V_H(a|s)** via prediction errors: **δ = r + γ·V(s') − V(s)**.
- **Prediction error (δ)**: The signed difference between received and predicted reward; encoded by phasic dopamine activity; used as the learning signal for habitual (and partly goal-directed) value updating.
- **Overtraining / habit formation**: The process by which extended, stable training progressively shifts behavioral control from goal-directed to habitual, reducing devaluation sensitivity.
- **Arbitration**: The higher-level mechanism (possibly prefrontal) that dynamically weights the contribution of goal-directed vs. habitual controllers to action selection, potentially based on their relative uncertainty or reliability.
- **Pavlovian–instrumental transfer (PIT)**: The modulation of instrumental (goal-directed or habitual) behavior by Pavlovian conditioned stimuli; a further interaction layer beyond the primary GD/Habit dichotomy.

---

## Identified Variables

| Variable | Role | Type | Range | Behavior |
|---|---|---|---|---|
| **s** — current state / context | Input to both controllers; identifies the environmental situation | Discrete (or continuous state vector) | Finite set of states *S* | Changes with environment; triggers value lookups |
| **a** — action | The behavioral output being evaluated or selected | Discrete | Finite set of actions *A* | Selected by policy π(a\|s) based on values |
| **o** — outcome | Consequence of taking action *a* in state *s* | Discrete | Finite set of outcomes *O* | Stochastic; drawn from p(o\|a,s) |
| **p(o\|a,s)** — action–outcome contingency | Core model of the goal-directed system; probability of outcome *o* given action *a* in state *s* | Continuous | [0, 1] | Learned and updated from experience; immediate revision possible |
| **r^D(o\|s)** — decision-time desirability | Subjective value of outcome *o* at time of decision; used by goal-directed system | Continuous | [−∞, +∞] (often normalized to [0, 1] or [−1, 1]) | Sensitive to current internal state (satiety, motivation); updates immediately with state change |
| **r^O(o\|s)** — experienced/outcome reward | Hedonic value of outcome *o* as evaluated at time of receipt | Continuous | [−∞, +∞] | Used as learning signal; encodes actual hedonic experience |
| **V_GD(a\|s)** — goal-directed action value | Value of action *a* in state *s* computed model-based: Σ_o p(o\|a,s)·r^D(o\|s) | Continuous | [−∞, +∞] | Updates immediately when p(·) or r^D(·) changes |
| **V_H(a\|s)** — habitual action value | Cached, model-free value of action *a* in state *s*; learned by TD | Continuous | [−∞, +∞] | Slow incremental updates via δ; insensitive to devaluation without re-experience |
| **δ** — reward prediction error | TD error: r + γ·V(s') − V(s); drives model-free value updates | Continuous | (−∞, +∞) | Phasic; zero at prediction accuracy; positive/negative at surprise |
| **γ** — temporal discount factor | Rate at which future rewards are discounted in habitual learning | Continuous | [0, 1] | Fixed or slowly adaptive parameter; shapes long-term value accumulation |
| **α** — learning rate | Step size for TD value update: V ← V + α·δ | Continuous | (0, 1] | Controls how quickly V_H(a\|s) adapts to new experience |
| **ω** — controller weight / arbitration parameter | Mixing weight determining relative contribution of goal-directed (ω) vs. habitual (1−ω) to final action value | Continuous | [0, 1] | Increases toward 0 with overtraining (habit dominance); context-sensitive |
| **N_train** — training trial count | Number of prior training trials; primary driver of habit formation | Discrete | [0, +∞) | Monotonically increases; correlates with decrease in ω (shift to habit) |
| **ΔV_outcome** — outcome value change (devaluation magnitude) | Change in r^D(o) following devaluation manipulation | Continuous | [−∞, 0] (reduction) | Applied externally; goal-directed system responds immediately; habitual system does not |
| **π(a\|s)** — action selection policy | Probability of selecting action *a* in state *s*; typically softmax over values | Continuous | [0, 1] | Determined by V_GD and/or V_H weighted by ω; temperature parameter β controls exploration |
| **β** — inverse temperature (softmax) | Exploration–exploitation trade-off parameter in softmax policy | Continuous | [0, +∞) | High β → near-deterministic (exploit); low β → random (explore) |
| **Internal state (e.g., hunger h)** — physiological drive | Modulates r^D(o\|s) for biologically relevant outcomes; internal state variable | Continuous | [0, 1] (normalized satiety) or [0, +∞) | Drives fluctuation in goal-directed value; ignored by habitual system |

---

## References

- **Rangel, Camerer & Montague (2008)** — *A framework for studying the neurobiology of value-based decision making.* Nature Reviews Neuroscience. DOI: 10.1038/nrn2357
- **Rangel, A. (2013)** — *Regulation of dietary choice by the decision-making circuitry.* Nature Neuroscience, 16(12): 1717–1724. DOI: 10.1038/nn.3561

> **Note on gaps**: The search corpus returned results primarily from Rangel et al. (2008) and Rangel (2013). Foundational empirical papers by Dickinson (e.g., 1985 — *Actions and habits: the development of behavioural autonomy*), Balleine & Dickinson (1998), and the computational model-based/model-free arbitration work by Daw, Niv & Dayan (2005) are extensively cited within these reviews but were not independently returned as corpus entries. Their contributions are described above as attributed within the review literature; direct DOIs for those primary sources were not verified in this search and are therefore not listed as primary references. Readers are directed to the reference lists of both Rangel papers for the full foundational citation trail.
