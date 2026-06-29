# Decision-making paradigms: Human dietary choice, valuation, reward, and self-control in food decisions

---

## 1. Drift-Diffusion Model
A sequential evidence-accumulation model in which a noisy decision variable drifts toward one of two absorbing boundaries, unifying response accuracy and response-time distributions into a single framework applied directly to food-choice speed and difficulty.

**Key authors**: Roger Ratcliff, Gail McKoon, Bogacz, Gold, Shadlen, Forstmann, Wagenmakers
**Key concepts**: drift rate (*v*) — the net value difference between food options (e.g., taste vs. health); boundary separation (*a*) — response caution / self-control threshold; starting-point bias (*z*) — pre-decisional preference for taste over health; non-decision time (*t₀*); speed-accuracy trade-off; first-passage time; within-trial Gaussian noise; across-trial variability in *v*, *z*, and *t₀*; neural ramp-to-threshold in LIP/pre-SMA

---

## 2. Goal-Directed vs. Habitual Control
Behavior is governed by two dissociable valuation systems — a goal-directed (model-based) system that prospectively computes action→outcome→reward chains, and a habitual (model-free) system that caches stimulus→response values from prior reward history — that compete for action selection in food environments, with the balance shifting toward habit under extensive training or stress.

**Key authors**: Antonio Rangel, Colin Camerer, P. Read Montague, Anthony Dickinson (via Rangel 2008/2013), Bernard Balleine (via Rangel), Nathaniel Daw, Peter Dayan
**Key concepts**: action–outcome contingency *p(o|a,s)*; decision-time desirability *r^D(o|s)*; experienced reward *r^O(o|s)*; goal-directed value *V_GD*; habit value *V_H*; temporal difference prediction error *δ*; discount factor *γ*; learning rate *α*; controller mixing weight *ω*; outcome devaluation sensitivity; contingency degradation; overtraining → habit shift; arbitration; Pavlovian–instrumental transfer

---

## 3. Attribute-Based Value Computation
The brain decomposes every food option into multiple measurable dimensions (taste, caloric density, health consequences), assigns attention-modulated weights to each, and integrates them into a single scalar subjective value signal in vmPFC that directly drives choice; this is the computational algorithm of the goal-directed system and generalises to novel, never-before-experienced foods.

**Key authors**: Antonio Rangel, Colin Camerer, P. Read Montague
**Key concepts**: attribute value *aᵢ(o)*; attribute weight *wᵢ* (modulated by attention *αₐₜₜ*); overall value *V(o) = Σwᵢ·aᵢ*; attribute space; immediate vs. abstract attributes (taste vs. health); attentional modulation; attribute conflict; vmPFC chosen-value signal; dlPFC→vmPFC attribute re-weighting; devaluation sensitivity; delta discount factor *δ* for delayed attributes; inter-option value difference *ΔV*; cognitive cost of attribute processing

---

## 4. Pavlovian Control of Food Approach
Food-predictive cues automatically elicit hard-wired preparatory (approach) and consummatory (eating) responses through classical conditioning, bypassing deliberate computation; this stimulus-bound, model-free controller is driven by mesolimbic dopamine for incentive salience ("wanting") and μ-opioid circuits for hedonic pleasure ("liking"), and its strength scales with hunger state.

**Key authors**: Antonio Rangel, Colin Camerer, P. Read Montague (Ivan Pavlov foundational; Berridge incentive-salience via Rangel 2013)
**Key concepts**: Pavlovian state value *V(s)*; reward prediction error *δ = r − V(s)*; CS–US contingency *P(US|CS)*; hunger modulation *h*; approach probability *A_approach*; approach vigor *v_approach*; CS salience; sign-tracking vs. goal-tracking; incentive salience ("wanting") vs. hedonic impact ("liking"); Pavlovian–instrumental transfer (PIT); consummatory response rate *C_eat*; phasic dopamine (DA); μ-opioid tone; BLA activity; Pavlovian controller weight *W_Pav*; extinction

---

## 5. Homeostatic Regulation of Food Valuation
Metabolic and endocrine signals — ghrelin (short-term orexigenic), leptin (long-term anorexigenic), insulin, and blood glucose — dynamically modulate the subjective value of food within the brain's valuation circuitry (vmPFC/OFC and hypothalamus), continuously updating the attribute weights on taste, calories, and health as the organism's energy state shifts; a closed-loop negative-feedback system governs energy intake, expenditure, fat mass, and body weight over multiple timescales.

**Key authors**: Antonio Rangel, Marine Jacquier
**Key concepts**: hunger state *H*; ghrelin *[G]*; leptin *[L]*; leptin receptor density *R_L*; insulin *[I]*; blood glucose *[BG]*; food subjective value *V(f, S)*; attribute weights *w_taste, w_caloric, w_health*; energy intake *I*; energy expenditure *E*; energy balance *EB = I − E*; fat mass *F*; body weight *BW*; meal-initiation threshold *θ*; devaluation index *d*; controller weights *(α_G, α_H, α_D)*; energy expenditure adaptation (delay ~8 days); leptin resistance; Pavlovian override of satiety; RPE/δ updating habitual food values

---

## 6. dlPFC Self-Control Modulation
The left dorsolateral prefrontal cortex (dlPFC, BA 9/46) exerts top-down, causally necessary control over the vmPFC value-computation process by selectively amplifying the weight of abstract/delayed food attributes (health) relative to immediate/hedonic attributes (taste), enabling goal-consistent dietary choices; this modulation is graded, limited by depletion, triggered by goal–impulse conflict, and quantified as dlPFC–vmPFC functional connectivity at the moment of decision.

**Key authors**: Antonio Rangel, Colin Camerer, P. Read Montague
**Key concepts**: composite chosen value *CCV = w_taste·taste + w_health·health*; dlPFC–vmPFC coupling strength *C_dlPFC*; attribute re-weighting; conflict signal *Conflict(t)*; goal activation *G*; goal-directed value *V_GD* vs. habit value *V_H*; decision reward function *r_D(o|s)*; action–outcome probability *p(o|a,s)*; self-control success *SC_success*; cognitive depletion *Depletion(t)*; TMS causal disruption; health-rating slope on vmPFC as biomarker of self-control

---

## Cross-paradigm interaction map

Distinct brain regions / neural substrates extracted from all six `## Primary Locus` sections:

| Paradigm | LIP / pre-SMA | vmPFC / medial OFC | dlPFC (BA 9/46) | Dorsomedial striatum | Dorsolateral striatum | Nucleus accumbens / Ventral striatum | Basolateral amygdala (BLA) | Central amygdala (CeA) | Hypothalamus (ARC) | VTA / Mesolimbic DA | Ventral pallidum | Hippocampus | Insula | Inferior parietal sulcus | Brainstem (NTS/PAG) | Subthalamic nucleus (STN) | Frontal Eye Fields / Superior Colliculus |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Drift-Diffusion Model** | ✓ | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ | ✓ |
| **Goal-Directed vs. Habitual Control** | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✗ | ✗ | ✓ | ✗ | ✓ | ✓ | ✓ | ✗ | ✗ | ✗ |
| **Attribute-Based Value Computation** | ✓ | ✓ | ✓ | ✓ | ✗ | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ | ✓ | ✓ | ✗ | ✗ | ✗ |
| **Pavlovian Control of Food Approach** | ✗ | ✓ | ✗ | ✗ | ✗ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✗ | ✗ | ✓ | ✗ | ✗ |
| **Homeostatic Regulation of Food Valuation** | ✗ | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✗ | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✓ | ✗ | ✗ |
| **dlPFC Self-Control Modulation** | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ | ✓ | ✓ | ✗ | ✗ | ✗ |

> **Reading the map**: vmPFC/medial OFC is the single convergence hub shared by all six paradigms — it is where drift evidence accumulates (DDM), where attribute-weighted values are integrated (ABVC), where goal-directed value updates land (GD/Habit), where Pavlovian outcome values are expressed (Pavlovian), where homeostatic hormones recalibrate food worth (Homeostatic), and where dlPFC top-down reweighting occurs (Self-Control). dlPFC clusters with the model-based/deliberative paradigms (DDM, GD/Habit, ABVC, dlPFC), while amygdala, ventral pallidum, PAG, and hypothalamus are exclusive to the more automatic controllers (Pavlovian, Homeostatic). STN and FEF/SC are unique to the DDM, reflecting its perceptual-decision heritage. This anatomy predicts which paradigms will produce synergistic or conflicting agent behaviors in simulation: Pavlovian and Homeostatic controllers share VTA/NAcc and will amplify one another under hunger + cue co-exposure; dlPFC Self-Control and Habitual Control are anatomically opponent (dlPFC vs. dorsolateral striatum), predicting competitive suppression.

---

## References

- Bogacz, R., Brown, E., Moehlis, J., Holmes, P., & Cohen, J. D. (2006) — *The physics of optimal decision making: A formal analysis of models of performance in two-alternative forced-choice tasks.* Psychological Review, 113(4), 700–765. DOI: 10.1037/0033-295X.113.4.700

- Forstmann, B. U., Dutilh, G., Brown, S., Neumann, J., von Cramon, D. Y., Ridderinkhof, K. R., & Wagenmakers, E.-J. (2008) — *Striatum and pre-SMA facilitate decision-making under time pressure.* PNAS, 105(45), 17538–17542. DOI: 10.1073/pnas.0805903105

- Gold, J. I., & Shadlen, M. N. (2007) — *The neural basis of decision making.* Annual Review of Neuroscience, 30, 535–574. DOI: 10.1146/annurev.neuro.29.051605.113038

- Jacquier, M. (2016) — *Mathematical modeling of the hormonal regulation of food intake and body weight: applications to caloric restriction and leptin resistance.* Doctoral thesis, Université Claude Bernard Lyon 1. HAL: tel-01273347

- Rangel, A. (2013) — *Regulation of dietary choice by the decision-making circuitry.* Nature Neuroscience, 16(12), 1717–1724. DOI: 10.1038/nn.3561

- Rangel, A., Camerer, C., & Montague, P. R. (2008) — *A framework for studying the neurobiology of value-based decision making.* Nature Reviews Neuroscience. DOI: 10.1038/nrn2357

- Ratcliff, R. (1978) — *A theory of memory retrieval.* Psychological Review, 85(2), 59–108. DOI: 10.1037/0033-295X.85.2.59

- Ratcliff, R., & McKoon, G. (2008) — *The diffusion decision model: Theory and data for two-choice decision tasks.* Neural Computation, 20(4), 873–922. DOI: 10.1162/neco.2008.12-06-420

- Ratcliff, R., & Rouder, J. N. (1998) — *Modeling response times for two-choice decisions.* Psychological Science, 9(5), 347–356. DOI: 10.1111/1467-9280.00067

- Smith, P. L., & Ratcliff, R. (2004) — *Psychology and neurobiology of simple decisions.* Trends in Neurosciences, 27(3), 161–168. DOI: 10.1016/j.tins.2004.01.006

- Wagenmakers, E.-J. (2009) — *Methodological and empirical developments for the Ratcliff diffusion model of response times and accuracy.* European Journal of Cognitive Psychology, 21(5), 641–671. DOI: 10.1080/09541440802205067

## Research Tree Map

```
Decision-making paradigms: Human dietary choice, valuation, reward, and self-control in food decisions
├── Attribute-Based Value Computation
│   ├── weighted-linear-summation-with-state-dependent-attribute-weights-algebraic
│   ├── attribute-based-evidence-accumulation-drift-diffusion
│   └── ode-based-dynamic-attribute-valuation-with-cognitive-control
├── dlPFC Self-Control Modulation
│   ├── attribute-reweighting-algebraic-model
│   ├── executive-resource-ode-with-dual-value-arbitration
│   └── bayesian-conflict-gated-stochastic-control
├── Drift-Diffusion Model
│   ├── classical-wiener-process-with-per-action-accumulators
│   ├── algebraic-closed-form-ddm-with-softmax-action-selection
│   └── collapsing-boundary-ode-accumulators-with-lateral-inhibition
├── Goal-Directed vs. Habitual Control
│   ├── dual-q-table-with-fixed-exponential-decay-arbitration
│   ├── uncertainty-based-bayesian-arbitration
│   └── ode-based-habit-strength-with-continuous-arbitration-dynamics
├── Homeostatic Regulation of Food Valuation
│   ├── drive-reduction-ode-with-goal-directed-valuation
│   ├── hormonal-modulation-with-softmax-reinforcement-learning
│   └── dual-controller-competition-with-pavlovian-override
└── Pavlovian Control of Food Approach
    ├── rescorlawagner-cached-value-agent-with-softmax-action-selection
    ├── incentive-salience-dual-process-agent-wantingliking-dissociation
    └── ode-based-continuous-drive-dynamics-with-deterministic-threshold-policy
```
