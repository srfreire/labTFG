# Predictive Coding — Deep Research

## Foundations

Predictive Coding (PC) is a framework for understanding brain function in which the nervous system continuously generates top-down predictions about incoming sensory signals and computes the mismatch — prediction error — between those predictions and actual sensory input. The brain's principal computational goal is to minimize prediction errors (equivalently, to maximize model evidence for the agent's own existence), rather than to passively receive and process sensory signals.

The computational roots of predictive coding trace to **Helmholtz's (1860s)** notion of perception as "unconscious inference," and to **analysis-by-synthesis** models in speech research. In its modern, hierarchical neural form, the foundational account is due to **Rao & Ballard (1999)**, who formalized a hierarchical generative model of the visual cortex explaining extra-classical receptive field effects through top-down prediction and bottom-up prediction-error signaling. This work is explicitly cited as the canonical PC reference in Friston (2010) and Petzschner et al. (2021).

The framework was subsequently absorbed and generalized by **Karl Friston** into the **Free Energy Principle (FEP)** (Friston, 2010, DOI: 10.1038/nrn2787), which frames predictive coding as one facet of a universal principle: adaptive self-organizing systems minimize variational free energy — a tractable upper bound on the surprise (negative log model evidence) of their sensory states. Under the FEP, prediction error minimization subsumes perception, action, attention, and learning within a single mathematical objective.

Friston & Kiebel (2009) extended the framework to cover temporal sequences, action (Active Inference), and multi-level cortical hierarchies. Petzschner, Garfinkel, Paulus, Koch, & Khalsa (2021, DOI: 10.1016/j.tins.2020.09.012) expanded predictive coding to interoceptive and body-regulation domains.

---

## Postulates

**P1.** The brain maintains a generative model of the world and continuously generates top-down predictions; only prediction errors — not raw sensory signals — are propagated between hierarchical levels. *(Rao & Ballard, 1999; cited in Friston, 2010 and Petzschner et al., 2021)*

**P2.** Perception is the process of inverting the generative model: the brain infers the most probable hidden causes of its sensory signals by minimizing the divergence between the approximate posterior (recognition density) and the true posterior. *(Friston, 2010)*

**P3.** Variational free energy F is an upper bound on sensory surprise: F ≥ −ln p(s̃ | m). Any adaptive agent that minimizes F also implicitly minimizes surprise, maintaining itself within its expected (viable) sensory states. *(Friston, 2010)*

**P4.** Precision (inverse variance) weights prediction errors; attention is the process of optimizing precision weights so that reliable signals gain more influence on belief updating. *(Friston, 2010)*

**P5.** Under Active Inference, actions are generated to fulfill predictions rather than to update them — the agent samples sensory data consistent with its current beliefs, closing the action–perception loop. *(Friston, 2010; Petzschner et al., 2021)*

**P6.** Prediction errors propagated via interoceptive pathways serve both to update internal body models and to drive body-regulatory actions; agents "stay alive by predicting the states that keep them alive, and act to fulfill those predictions." *(Petzschner et al., 2021)*

---

## Assumptions

- The brain encodes probability distributions (beliefs), not point estimates; it maintains a **recognition density** q(ϑ | μ) over hidden causes ϑ.
- A **generative model** p(s̃, ϑ | m) — specifying both a likelihood p(s̃ | ϑ, m) and a prior p(ϑ | m) — is implicitly encoded in synaptic weights and connection strengths.
- The cortex is organized as a **hierarchical system** in which each level generates predictions for the level below and receives prediction-error signals from the level below.
- **Top-down connections** carry predictions (backward connections); **bottom-up connections** carry prediction errors (forward connections).
- The generative model is a **Gaussian/Laplace** approximation in the simplest formulation, rendering inference tractable.
- **Precision** (inverse variance) of prediction errors is dynamically modulatable, providing a mechanism for attention and weighting of sensory channels.
- The agent can reduce free energy by two means: (a) **perceptual inference** — changing internal states μ to better match sensory data; (b) **active inference** — changing sensory data a by acting on the world to conform to predictions.
- Learning (slower timescale) updates the parameters θ of the generative model; inference (faster timescale) updates the current state estimates μ.
- Free energy F is computable by the agent since it is a function of: (i) sensory states s̃(t), and (ii) internal states μ(t) encoding the recognition density.

---

## Predictions

- **Perception is constructive**: percepts reflect a weighted combination of prior predictions and sensory likelihood, not just bottom-up input. Ambiguous stimuli will be resolved by priors.
- **Sensory attenuation**: predicted sensory inputs produce attenuated neural responses compared to unpredicted inputs (reduced prediction error for expected signals).
- **Mismatch negativity (MMN)**: unexpected stimuli elicit larger neural responses than expected ones, proportional to prediction error magnitude.
- **Attentional modulation**: increasing the precision weight on a sensory channel amplifies the effective prediction-error signal for that channel, increasing its influence on perception — equivalent to directed attention.
- **Motor behaviour as self-fulfilling prophecy**: movement arises from the brain generating predictions of desired proprioceptive states, with reflex arcs acting to reduce the resulting proprioceptive prediction error.
- **Curiosity and active sampling**: agents will preferentially sample states that are expected to reduce uncertainty (epistemic foraging), because this reduces free energy.
- **Hallucinations/delusions**: pathologically strong priors or impaired precision weighting can cause internally-generated predictions to dominate over sensory evidence, producing percepts unconstrained by reality.
- **Interoceptive prediction errors** drive body-regulation behavior: deviations between predicted and sensed internal states (temperature, glucose, osmolarity) motivate corrective homeostatic actions.
- **Learning** (updating generative model parameters) occurs when prediction errors persist across time, updating synaptic weights to improve future predictions.

---

## Primary Locus

The neural implementation of predictive coding is distributed across a **cortical hierarchy**, with no single locus:

- **Primary sensory cortices (V1, S1, A1)**: lowest level; receive top-down predictions from higher areas; superficial-layer neurons (layers II/III) encode prediction errors propagated upward; deep-layer neurons (layers V/VI) encode predictions sent downward. *(Rao & Ballard, 1999, cited in Friston, 2010)*
- **Hierarchical association cortices (V2–V5, temporal, parietal, prefrontal)**: progressively encode higher-order, more abstract predictions and receive prediction errors from subordinate levels. *(Friston, 2010)*
- **Prefrontal cortex (PFC)**: highest cortical levels encoding abstract priors and temporal context; sends strong top-down predictions throughout the hierarchy.
- **Thalamus**: modulates precision (gain) of cortical prediction-error signals; contributes to attention via thalamocortical loops. *(Friston, 2010)*
- **Anterior cingulate cortex (ACC) and subgenual cortex**: highest-level interoceptive hierarchy nodes encoding visceromotor predictions. *(Petzschner et al., 2021)*
- **Insula**: key interoceptive relay; integrates ascending visceral prediction errors with top-down interoceptive predictions. *(Petzschner et al., 2021)*
- **Basal ganglia / dopaminergic system**: proposed to encode precision-weighted prediction errors, with dopamine acting as a precision or salience signal on prediction errors. *(Friston, 2010)*
- **Hypothalamus**: interacts with reward-learning circuitry to instantiate homeostatic priors; its signals modulate dopaminergic activity consistent with interoceptive prediction error encoding. *(Petzschner et al., 2021)*

---

## Key Concepts

- **Generative Model**: A probabilistic model p(s̃, ϑ | m) encoding the joint probability of sensory data s̃ and their hidden causes ϑ, given the agent's world model m. Specifies both a likelihood (how causes generate sensations) and a prior over causes.
- **Recognition Density** q(ϑ | μ): The agent's approximate posterior belief over hidden causes, parameterized by internal brain states μ. Represents the agent's current best guess about what caused its sensations.
- **Prediction Error (PE)**: The signed difference between actual sensory input and the top-down prediction at a given level. The key signal propagated upward through the hierarchy to update beliefs.
- **Variational Free Energy (F)**: An information-theoretic upper bound on surprise (−ln p(s̃ | m)), computable by the agent. Equivalent to KL-divergence between recognition and posterior densities, minus log model evidence. Minimizing F is the brain's central objective.
- **Surprise (Surprisal)**: −ln p(s̃ | m), the negative log probability of sensory observations under the generative model. Not directly computable; F bounds it from above.
- **Precision (Π)**: The inverse variance of a prediction error distribution. Acts as a confidence weight: high-precision prediction errors have greater influence on belief updating. Neural correlate of attention.
- **Active Inference**: The process whereby action a is selected to minimize free energy by making sensory input conform to predictions, rather than by updating beliefs. Unifies motor control with perception under a single principle.
- **Empirical Prior**: A prior distribution on causes at one hierarchical level, constrained by predictions from the level above rather than fixed. Allows priors to be learned and updated online.
- **Hierarchical Generative Model**: A multi-level generative model in which causes at level l generate predicted states at level l−1; each level's posterior becomes the prior for the level below, enabling multi-scale inference.
- **Model Evidence**: p(s̃ | m), the marginal likelihood of sensory data under the generative model. Maximizing model evidence (minimizing surprise) is the brain's distal objective; minimizing free energy achieves this proximally.
- **KL-Divergence (D_KL)**: A non-negative measure of the difference between two probability distributions. Appears in the free energy decomposition as the "perceptual divergence" between recognition and posterior densities; minimizing it makes beliefs more accurate.
- **Prediction (top-down)**: The expected sensory state at level l, generated by projecting the level-(l+1) posterior through the generative model. Carried by backward (descending) cortical connections.

---

## Identified Variables

| Variable | Role | Type | Range | Behavior |
|---|---|---|---|---|
| **s̃(t)** — Sensory signal (and its motion) | Input to generative model at lowest level; compared against prediction to generate PE | Continuous | ℝⁿ (n = dimensionality of sensory vector) | Changes continuously with environment; drives bottom-up PE signals |
| **ϑ = {x̃, θ, γ}** — Hidden causes | True external states, parameters, and precisions generating sensory data; unobservable by agent | Continuous | ℝᵐ (model-dependent) | Evolve according to environment dynamics; agent must infer them |
| **μ(t)** — Internal brain states (sufficient statistics of recognition density) | Parameterize q(ϑ | μ); updated continuously to minimize F | Continuous | ℝᵐ | Governed by gradient descent on F: dμ/dt = −∂F/∂μ |
| **q(ϑ | μ)** — Recognition density | Agent's approximate posterior belief; encodes current hypothesis about hidden causes | Continuous (probability distribution) | Probability simplex / Gaussian parameters | Updated via inference to converge toward true posterior p(ϑ | s̃) |
| **F(s̃, μ)** — Variational free energy | Global objective to minimize; upper bounds surprise; drives both perception and action | Continuous (scalar) | [0, +∞) | Decreases monotonically during correct inference; minimized through μ and a updates |
| **ε(l)(t)** — Prediction error at level l | Signed difference: actual input at level l minus top-down prediction from level l+1 | Continuous | ℝⁿ (per level) | Propagated upward in hierarchy; drives belief updating; approaches 0 at convergence |
| **Π(l)** — Precision at level l (inverse variance) | Weights prediction error ε(l) in belief updating; attention control variable | Continuous (scalar or matrix) | (0, +∞), often [0.01, 100] in practice | Modulated dynamically; high precision = high attention; encodes reliability of signal |
| **a(t)** — Action | Motor output; changes external states to minimize proprioceptive/exteroceptive PE | Continuous | ℝᵏ (k = motor degrees of freedom) | Governed by: da/dt = −∂F/∂a; drives sensations toward predictions |
| **p̂(l)(t)** — Prediction at level l | Top-down expected value of level-(l−1) input, generated from μ(l) via generative model | Continuous | ℝⁿ (per level) | Determined by current beliefs at level l; updated with μ; decreases PE when accurate |
| **θ** — Generative model parameters | Synaptic weights encoding likelihood mapping and prior structure; updated during learning | Continuous | ℝᵖ | Slower timescale than μ; updated by Hebbian-like rules proportional to precision-weighted PE |
| **γ** — Log-precision (hyperparameter) | Controls expected amplitude of random fluctuations; sets prior on precision | Continuous | ℝ (precision ∝ exp(γ)) | Adjusted to optimize hierarchical precision weighting; links to neuromodulation |
| **−ln p(s̃ | m)** — Surprise (Surprisal) | True objective; not directly computable; bounded by F | Continuous (scalar) | [0, +∞) | Minimized indirectly through F minimization; quantifies improbability of current sensations |
| **D_KL[q ‖ p(ϑ | s̃)]** — Perceptual divergence | Difference between agent's beliefs and optimal posterior; equals zero at exact inference | Continuous (scalar) | [0, +∞) | Driven toward zero by perceptual inference; non-zero reflects residual model inaccuracy |
| **L** — Hierarchical level index | Discrete index of cortical processing level | Discrete (integer) | {1, 2, …, L}, L typically 4–8 for cortex | Fixed architecture; higher levels = more abstract, slower timescale representations |

---

## References

- **Friston, K. (2010)** — *The free-energy principle: a unified brain theory?* Nature Reviews Neuroscience. DOI: 10.1038/nrn2787
- **Petzschner, F.H., Garfinkel, S.N., Paulus, M.P., Koch, C., & Khalsa, S.S. (2021)** — *Computational Models of Interoception and Body Regulation.* Trends in Neurosciences. DOI: 10.1016/j.tins.2020.09.012
- **Keramati, M. & Gutkin, B. (2014)** — *Homeostatic reinforcement learning for integrating reward collection and physiological stability.* eLife. DOI: 10.7554/eLife.04811
- **Rao, R.P. & Ballard, D.H. (1999)** — *Predictive coding in the visual cortex: a functional interpretation of some extra-classical receptive field effects.* Nature Neuroscience, 2, 79–87. [Cited as foundational reference in Friston (2010) and Petzschner et al. (2021)]
- **Friston, K. & Kiebel, S. (2009)** — *Predictive coding under the free-energy principle.* Philosophical Transactions of the Royal Society B: Biological Sciences, 364, 1211–1221. [Cited in Petzschner et al. (2021)]
