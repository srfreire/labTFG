All seven deep research reports are back. Here is the complete synthesis:

---

# Decision-making paradigms: Interaction between homeostatic and hedonic systems in the regulation of food intake behavior

---

## 1. Homeostatic Regulation
The body maintains energy balance through negative-feedback loops that compare current energy state to a defended set-point, generating corrective eating or fasting behaviors proportional to the detected error.

**Key authors**: Claude Bernard, Walter B. Cannon, Gina Turrigiano, Eve Marder, Morteza Keramati, Boris Gutkin, Fridolin Gross

**Key concepts**:
- **Set-point & error signal**: Regulated variables (blood glucose, adiposity, body weight) are compared against a target; the resulting error signal `e = A − s` drives corrective action
- **Negative feedback via hypothalamus**: Arcuate nucleus AgRP/POMC neurons integrate peripheral signals (leptin, insulin, ghrelin) and drive hunger or satiety
- **Integral control law**: Ensures zero steady-state error: `dA/dt = c(t) − d·A(t) + E(t)`; scales to synaptic homeostasis in neural circuits
- **Homeostatic RL reformulation**: Reward is recast as drive-reduction, `r(t) = D(x(t)) − D(x(t+1))`, unifying energy regulation with reinforcement learning
- **Drive depletion–repletion cycle**: Eating is motivated by accumulated deviations from set-point, terminated by satiety feedback

---

## 2. Hedonic / Reward-Based Regulation of Food Intake
The mesolimbic reward circuit can override homeostatic satiety signals, driving intake of palatable food beyond caloric need through dopaminergic and opioidergic processing of pleasure and incentive.

**Key authors**: Kent Berridge, Terry Robinson, Ann Kelley, Michael Lutter, Eric Nestler, Nora Volkow, Frederick Toates

**Key concepts**:
- **Dual-process integration**: Intake is jointly determined by homeostatic drive H(t) and reward value R(t): `I(t) = α·H(t) + β·R(t) + γ·H(t)·R(t)` — crucially, the interaction term γ means hunger amplifies reward valuation
- **Mesolimbic dopamine pathway**: VTA → nucleus accumbens signaling encodes reward prediction errors and energizes food seeking
- **Opioid/endocannabinoid "liking"**: μ-opioid and CB1 receptors in accumbens shell mediate hedonic pleasure ("liking") independently of dopamine
- **Hypothalamic–reward crosstalk**: Leptin and ghrelin receptors are expressed in the VTA; metabolic state directly modulates reward circuit gain
- **Override of satiety**: Palatability-driven reward can suppress leptin/CCK satiety signals, producing overconsumption of palatable foods even in a sated state

---

## 3. Incentive Salience Theory
Dopamine-mediated "wanting" (motivational urgency toward food) is neurobiologically dissociable from opioid-mediated "liking" (hedonic pleasure), and can be pathologically amplified by sensitization independent of actual enjoyment.

**Key authors**: Kent C. Berridge, Terry E. Robinson, Paul Montague, Nathaniel Daw

**Key concepts**:
- **Wanting ≠ Liking**: "Wanting" is incentive salience attributed to stimuli by mesolimbic dopamine; "liking" is hedonic impact mediated by opioid/endocannabinoid hotspots in the ventral pallidum and accumbens shell — the two can be fully dissociated
- **Cue-triggered craving**: Food-associated cues recruit dopamine to focus attention and approach motivation toward food, even without hunger or expected pleasure
- **Sensitization**: Repeated exposure to palatable food or food cues escalates "wanting" via dopaminergic sensitization while "liking" remains constant or decreases
- **Temporal Difference integration**: RPE signal `δ` drives associative learning, while a separate dopamine-gated incentive salience term gates action selection — action is controlled by IS, not learned value alone
- **Relevance to obesity/addiction**: Explains why people crave food they no longer enjoy — a dissociation highly relevant to binge eating and food addiction

---

## 4. Allostatic / Opponent-Process Model of Food Intake
Repeated cycles of palatable food intake recruit a progressively dominant opponent (aversive/stress) process that lowers the hedonic set-point, shifting the motivation for eating from positive reinforcement (pleasure) toward negative reinforcement (relief of dysphoria).

**Key authors**: George Koob, Michel Le Moal, Richard Solomon, Laurence Corbit, Peter Sterling, Jay Eyer, Bruce McEwen

**Key concepts**:
- **a-process / b-process dynamics**: Each eating episode triggers a primary hedonic a-process and a slower, longer-lasting opponent b-process; with repetition, b dominates and the net hedonic experience declines
- **Allostatic set-point shift**: Chronic overconsumption of palatable food resets the reward baseline downward; eating becomes necessary to reach a new (lower) functional norm rather than to experience pleasure
- **Neurochemical substrates**: Downregulation of dopamine D2 receptors, upregulation of CRF and dynorphin stress systems in the extended amygdala
- **Negative reinforcement loop**: Abstinence produces negative affect, anxiety, and dysphoria that drive renewed intake — a compulsive, addiction-like cycle
- **Formal ODE model**: a-process and b-process modeled with first-order differential equations; allostatic load accumulates as residual opponent-process burden

---

## 5. Associative Learning and Conditioned Appetite
Neutral environmental cues (sights, sounds, smells, contexts) acquire powerful motivational control over food seeking through associative learning, driven by dopaminergic reward prediction error signals that update cue–food associations trial by trial.

**Key authors**: Ivan Pavlov, Robert Rescorla, Allan Wagner, Wolfram Schultz, Amy Reichelt

**Key concepts**:
- **Rescorla–Wagner model**: Associative strength updates as `ΔVᵢ = αᵢ · β · (λ − ΣVⱼ)` where the prediction error `(λ − ΣVⱼ)` drives learning — overeating environments that are cue-rich produce strongly conditioned appetites
- **Temporal Difference (TD) learning**: Extends R–W to real-time sequences; dopamine RPE signal `δ(t)` maps onto phasic dopamine activity recorded in VTA/SNc
- **Conditioned hunger**: CS presentation (e.g., food advertisement) can reinstate appetite and physiological preparatory responses (insulin, gastric acid) even in the absence of hunger
- **Homeostatic–hedonic gating**: Metabolic state (hunger) modulates the strength of conditioned responding — CS-triggered "wanting" is amplified when the animal is energy-depleted, linking associative and homeostatic systems
- **Relevance to obesity**: Obesogenic environments densely packed with food cues produce chronic cue-triggered motivation that overrides homeostatic satiety

---

## 6. Cognitive / Executive Control of Eating Behavior
Top-down prefrontal mechanisms — including inhibitory control, working memory, and cognitive flexibility — modulate eating decisions by counteracting bottom-up reward-driven approach, with breakdowns in these functions predicting overeating and obesity.

**Key authors**: Akira Miyake; contributors to *Appetite*, *Current Opinion in Behavioral Sciences*, and *Neuropsychiatric Disease and Treatment*

**Key concepts**:
- **Triadic interaction model**: Intake = `Reward system activation − Executive control + Valuation processes`; DLPFC exerts inhibitory top-down modulation on the reward/limbic system
- **Three core executive functions**: (1) Inhibitory control — suppressing prepotent responses to palatable food; (2) Working memory — holding dietary goals online while making food choices; (3) Cognitive flexibility — shifting away from food-cue focus
- **DLPFC–hypothalamus–striatum circuit**: Prefrontal cortex projects to hypothalamic feeding circuits and accumbens to regulate both homeostatic and hedonic drives
- **Ego depletion & cognitive load**: Executive control is a limited resource; stress, fatigue, or cognitive load impair inhibition and reliably increase hedonic eating
- **Interindividual variability**: Deficits in food-specific inhibitory control are a strong predictor of BMI and binge eating, independent of general executive function

---

## 7. Gut–Brain Axis Signaling
Bidirectional communication between the gastrointestinal tract and the central nervous system — via vagal neural pathways, satiety/orexigenic hormones, and microbiota-derived metabolites — integrates peripheral nutritional status with both hypothalamic homeostatic circuits and mesolimbic reward circuits.

**Key authors**: Hans-Rudolf Berthoud, Emeran Mayer, Byung Yoo, Jae Park

**Key concepts**:
- **Satiety hormone cascade**: Post-ingestive nutrient sensing triggers GLP-1, PYY, and CCK release from gut enteroendocrine cells → vagus nerve → nucleus tractus solitarius (NTS) → arcuate nucleus; modeled as first-order stimulated secretion with clearance kinetics
- **Ghrelin as hunger signal**: Stomach-derived ghrelin rises pre-prandially, acts on arcuate AgRP neurons and VTA dopamine neurons to simultaneously increase homeostatic drive AND reward system gain
- **Vagal afferents**: The vagus transmits real-time mechanical and chemical signals from gut lumen to brainstem, providing caloric load information upstream of conscious awareness
- **Microbiota–gut–brain axis**: SCFAs produced by fermentation stimulate GLP-1 and PYY release; tryptophan metabolites (indoles) and serotonin modulate vagal tone and reward processing
- **Hypothalamic integration**: Arcuate nucleus integrates hormonal signals into a weighted sum of orexigenic (NPY/AgRP) vs. anorexigenic (POMC/CART) output that gates both energy expenditure and the gain of reward circuits
- **Reward system modulation**: Leptin and GLP-1 receptors in the VTA and nucleus accumbens directly regulate dopamine release, providing a mechanistic link between gut-derived satiety signals and hedonic eating suppression

---

## Cross-paradigm interaction map

| Paradigm | Primary locus | Role in homeostatic–hedonic interaction |
|---|---|---|
| Homeostatic regulation | Hypothalamus / arcuate nucleus | Defines the energy-deficit drive that sets the baseline urgency to eat |
| Hedonic/reward regulation | VTA / nucleus accumbens | Can override satiety; amplified by hunger; drives palatability-based overconsumption |
| Incentive salience | Mesolimbic dopamine | Dissociates motivation from pleasure; cue-driven "wanting" can persist independently of need |
| Allostatic/opponent-process | Extended amygdala / stress systems | Chronic hedonic eating degrades the reward set-point, creating compulsive negative-reinforcement cycles |
| Associative learning | VTA → striatum → cortex | Converts environmental cues into conditioned motivational drives; hunger gates cue strength |
| Cognitive executive control | DLPFC → striatum / hypothalamus | Top-down brake on both homeostatic urgency and hedonic craving; resource-limited and stress-sensitive |
| Gut–brain axis | Enteroendocrine cells → vagus → NTS → hypothalamus / VTA | Provides real-time peripheral nutritional state input to both homeostatic and reward circuits |

Together, these paradigms describe food intake not as a single regulated variable but as an **emergent outcome of competing and cooperating drives**: energy-deficit signals from the gut and hypothalamus set the motivational baseline; reward circuits amplify or suppress intake based on palatability and learned cue value; incentive salience can decouple motivation from pleasure; allostatic load shifts the reward set-point over time; and prefrontal executive control serves as the arbitrating higher-level decision-maker — all regulated moment-to-moment by the continuous stream of gut-derived hormonal and neural signals.