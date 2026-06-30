# Verdict

Pass with reservations.

The case is scientifically useful and mostly faithful to the supplied corpus, but it needs expert review before the artifacts are treated as a clean reusable benchmark.

Decisive reasons:

- the 4 carried-forward paradigms are supported by the 3 included papers, especially Petzschner et al. for HRL, IAI and predictive coding
- the pipeline produced 12 formulations, 12 registered model rows and 12 test files, and the registered model files expose the required `decide`, `update` and `get_state` methods
- the formulation content is plausible for a grid-world DecisionModel, but several formulations mix HRL, active inference and predictive coding across paradigm folders
- the KG export has 272 nodes and 352 relations, but the run logged 96 KG endpoint errors across researcher, formalizer and reasoner memory writes
- only 5 Postulate nodes appear in the KG snapshot, all under `homeostatic-regulation`, while the error log shows missing postulates for HRL, IAI and predictive coding
- the artifact bundle is internally usable, but duplicate model files, non-canonical graph keys and parameter duplication weaken later reinjection

# Evidence table

| Criterion | Judgement | Evidence path |
|---|---|---|
| Corpus faithfulness | Pass | `/Users/ppazosp/projects/labTFG/phase1-pablo/evals/reports/2026-06-29-caso2-pdf-corpus/artifact-bundle/corpus/manifest.json` lists 3 papers. Extracted text supports the main labels in `corpus/texts/Petzschner_Koch_computationalmodels_bodyregulation_2021.txt`, lines around 41, 246 to 270, 298 to 340 and 1269 to 1276. |
| Paradigm quality | Pass with reservations | `artifact-bundle/storage/research/80d9be2e-8521-4e58-b982-9c1da697297c/report.md` describes 6 frameworks, but the run carries forward 4 paradigms in `/Users/ppazosp/projects/labTFG/phase1-pablo/evals/reports/2026-06-29-caso2-pdf-corpus/report.md`. |
| Formulation quality | Pass with reservations | 12 reasoner JSON files exist under `artifact-bundle/storage/models/80d9be2e-8521-4e58-b982-9c1da697297c/reasoner/`. The markdown formulation files under `artifact-bundle/storage/research/80d9be2e-8521-4e58-b982-9c1da697297c/formulations/` give equations and decision logic. |
| Model quality | Pass | `/Users/ppazosp/projects/labTFG/phase1-pablo/evals/reports/2026-06-29-caso2-pdf-corpus/artifact-bundle/database/models.json` has 12 registered models. The builder tree has 12 test files and the registered model files expose `decide`, `update` and `get_state`. |
| Memory and artifact quality | Pass with reservations | `/Users/ppazosp/projects/labTFG/phase1-pablo/evals/reports/2026-06-29-caso2-pdf-corpus/artifact-bundle/kg_snapshot_2026-06-29.json` has 272 nodes and 352 relations. Database exports include 54 artifacts, 12 models, 272 node observations and 1,184 pipeline memory rows. |
| Error and warning review | Reservations | `/Users/ppazosp/projects/labTFG/phase1-pablo/evals/reports/2026-06-29-caso2-pdf-corpus/report.json` records 4 researcher KG errors, 22 formalizer KG errors and 70 reasoner KG errors. The builder review records 3 warnings. |
| Overall judgement | Pass with reservations | The run completed all stages and the eval report says PASS, but the KG and taxonomy issues matter for a TFG handoff. |

# Findings by criterion

## 1. Corpus faithfulness

The main scientific claims trace back to the included corpus.

The corpus manifest lists 3 papers:

- `Computational Models of Interoception and Body Regulation`
- `The free-energy principle: a unified brain theory?`
- `Homeostatic reinforcement learning for integrating reward collection and physiological stability`

The extracted Petzschner text names homeostasis, allostasis, active inference, predictive coding and reinforcement learning in the keyword area. It also has sections for interoceptive predictive coding, HRL and IAI. The HRL paper supports drive reduction, physiological stability, physiological rationality and the link between reward seeking and homeostasis. The Friston paper supports free energy, active inference, Bayesian brain and predictive coding.

The report also uses cited works outside the 3 PDFs, such as Cannon, Hull, Cabanac, Conant and Ashby, Rao and Ballard, Sutton and Barto. This is mostly acceptable because those works are cited inside the supplied papers. It should not be read as independent evidence from outside the corpus.

Judgement: pass.

## 2. Paradigm quality

The discovered paradigms are coherent, but the abstraction level is uneven.

The final carried-forward set is:

- `homeostatic-regulation`
- `homeostatic-reinforcement-learning`
- `interoceptive-active-inference`
- `predictive-coding`

This is a defensible set for this corpus. Petzschner explicitly frames HRL, IAI and predictive coding as computational models for interoception and body regulation. The broad `homeostatic-regulation` paradigm is also grounded in the corpus.

The reservation is that the research report first names 6 frameworks: homeostatic regulation, HRL, Bayesian brain hypothesis, active inference, IAI and predictive coding. It then carries forward only 4. The merge is understandable, but the report does not clearly explain why Bayesian brain and active inference become formulations or substructure rather than paradigms.

There is also overlap between folders. For example, `homeostatic-regulation` includes an IAI formulation, `interoceptive-active-inference` includes an HRL formulation, and `predictive-coding` includes an active inference formulation. These are scientifically related, but the hierarchy is not clean enough for an expert taxonomy without review.

Judgement: pass with reservations.

## 3. Formulation quality

The formulations are scientifically plausible and usable for simulation, but some are simplified grid-world translations.

The 12 formulations include:

- 3 under homeostatic regulation
- 3 under homeostatic reinforcement learning
- 3 under interoceptive active inference
- 3 under predictive coding

The HRL formulations use drive functions, drive-reduction reward and temporal-difference learning. This matches Keramati and Gutkin. The IAI formulations use Bayesian state estimation, free energy, expected free energy and allostatic prior shifting. This matches Friston and Petzschner at a high level. The predictive coding formulations use precision-weighted prediction errors, Bayesian filtering and expected free energy.

The equations in the markdown files are coherent enough for a simulated grid-world. Some parameter defaults are calibrated by the system rather than directly drawn from papers. Examples include energy decay, movement cost, sensory noise and policy temperature. That is acceptable for an implementation benchmark, but these values should not be presented as empirical parameters from the corpus.

The reasoner JSON files store variables, parameters, rules, decision logic and references. They do not store equations under an `equations` key. The equations are present in the markdown formulation files, so this is not a scientific failure. It does reduce machine-readability for later review.

Judgement: pass with reservations.

## 4. Model quality

The registered models match the DecisionModel contract at the interface level.

`database/models.json` has 12 rows. Each row has a class name, paradigm, formulation, `s3_model_key` and `s3_test_key`. The builder output has 12 `test_*.py` files. The eval report records 40 successful `run_tests` tool calls.

Static inspection found the required methods in the generated model files:

- `decide(self, perception: dict) -> Action`
- `update(self, action, reward, new_perception)`
- `get_state(self) -> dict`

The tests cover meaningful behaviours, including movement toward resources, eating when hungry, hunger or energy updates, Bayesian belief updates, normalized beliefs and read-only `decide` behaviour in at least one active inference model.

There is one artifact hygiene concern. The builder folder contains 21 model files, while the database registers 12. Several formulations have both hyphenated and underscored copies. Some duplicate copies differ in line count, for example the active inference predictive coding files have 510 and 536 lines. The registered `s3_model_key` paths point to the hyphenated copies, so this does not break the registered models. It can confuse later reinjection or manual review.

Judgement: pass.

## 5. Memory and artifact quality

The artifact bundle is complete enough to reinject, but the KG is not clean.

The bundle manifest has no bundle-level errors and includes corpus, database, KG snapshot and storage sections. The database exports include:

- 1 run in `database/runs.json`
- 54 artifact rows in `database/artifacts.json`
- 12 model rows in `database/models.json`
- 272 node observations in `database/node_run_observations.json`
- 1,184 memory rows in `database/pipeline_memories.json`
- 0 simulation observations in `database/simulation_observations.json`

The KG snapshot has:

- 272 nodes
- 352 relations
- 4 Paradigm nodes
- 12 Formulation nodes
- 12 Model nodes
- 4 Paper nodes
- 6 Author nodes
- 84 Variable nodes
- 127 Parameter nodes

The KG contains the 3 source papers plus a Conant and Ashby paper node. That fourth paper is cited in the corpus, but it is not one of the source PDFs. The graph also has Cannon and Hull author nodes without matching paper nodes.

The main reinjection risk is structural. The KG has only 5 Postulate nodes, all under `homeostatic-regulation`. Reasoner errors show that the pipeline tried to connect parameters to missing postulates under `homeostatic-reinforcement-learning`, `interoceptive-active-inference` and `predictive-coding`. This means later graph queries may find models and parameters but fail to recover their intended postulate support.

Judgement: pass with reservations.

## 6. Error and warning review

The reported PASS is credible for execution, but the warning count matters for expert review.

Material warnings and errors:

- 96 KG endpoint errors across memory writes: 4 researcher, 22 formalizer and 70 reasoner
- missing endpoint errors for `BELONGS_TO`, `USES_VARIABLE`, `MODULATES` and `DERIVES_FROM`
- missing postulate nodes for HRL, IAI and predictive coding
- author nodes for Hull and Cannon lack `AUTHORED` edges to paper nodes
- Conant and Ashby paper node lacks DOI and author nodes
- duplicated prior precision parameter under IAI
- model to paper `CITES` relation uses a non-canonical source endpoint key
- builder review warns that at least one model node may not be visible as expected in the graph snapshot

These are not enough to fail the case because the markdown, JSON files and registered model rows preserve the main artifacts. They are enough to stop a clean pass.

# Concrete issues

## High severity

1. Missing KG postulates outside `homeostatic-regulation`

The KG snapshot has 5 Postulate nodes, all with IDs `homeostatic-regulation:P1` to `P5`. The reasoner logged 70 `DERIVES_FROM` endpoint errors for missing postulates under HRL, IAI and predictive coding. This weakens traceability from parameters to scientific assumptions.

Evidence:

- `/Users/ppazosp/projects/labTFG/phase1-pablo/evals/reports/2026-06-29-caso2-pdf-corpus/artifact-bundle/kg_snapshot_2026-06-29.json`
- `/Users/ppazosp/projects/labTFG/phase1-pablo/evals/reports/2026-06-29-caso2-pdf-corpus/report.json`

2. Taxonomy overlap between paradigms and formulations

The pipeline carries forward 4 paradigms but the research report names 6 frameworks. It then places HRL inside IAI, IAI inside homeostatic regulation and active inference inside predictive coding. This may be a valid conceptual nesting, but the report does not explain the merge rules.

Evidence:

- `/Users/ppazosp/projects/labTFG/phase1-pablo/evals/reports/2026-06-29-caso2-pdf-corpus/artifact-bundle/storage/research/80d9be2e-8521-4e58-b982-9c1da697297c/report.md`
- `/Users/ppazosp/projects/labTFG/phase1-pablo/evals/reports/2026-06-29-caso2-pdf-corpus/report.md`

## Medium severity

3. KG endpoint errors could reduce reinjection quality

The eval report marks all stages as ok, but `report.json` records endpoint failures in researcher, formalizer and reasoner memory writes. These failures affect structural edges, not just optional metadata.

Evidence:

- `report.json`, field `.topics[0].run.memory_per_stage`

4. Duplicate model files could confuse later loading

The builder folder has 21 `*_model.py` files but only 12 registered model rows. The registered rows point to hyphenated model files, but underscored copies also exist. Some copies differ in line count.

Evidence:

- `/Users/ppazosp/projects/labTFG/phase1-pablo/evals/reports/2026-06-29-caso2-pdf-corpus/artifact-bundle/storage/models/80d9be2e-8521-4e58-b982-9c1da697297c/builder/`
- `/Users/ppazosp/projects/labTFG/phase1-pablo/evals/reports/2026-06-29-caso2-pdf-corpus/artifact-bundle/database/models.json`

5. Machine-readable formulations do not expose equations directly

The markdown formulation files include equations. The reasoner JSON files store `rules`, not an `equations` array. This may be by design, but it makes automated trace checks harder.

Evidence:

- `/Users/ppazosp/projects/labTFG/phase1-pablo/evals/reports/2026-06-29-caso2-pdf-corpus/artifact-bundle/storage/models/80d9be2e-8521-4e58-b982-9c1da697297c/reasoner/`
- `/Users/ppazosp/projects/labTFG/phase1-pablo/evals/reports/2026-06-29-caso2-pdf-corpus/artifact-bundle/storage/research/80d9be2e-8521-4e58-b982-9c1da697297c/formulations/`

## Low severity

6. Source metadata is partly incomplete

The corpus manifest has empty author arrays for the 3 papers. The KG creates 6 Author nodes, but some important cited authors have incomplete paper links. This is a metadata quality issue, not a content failure.

Evidence:

- `/Users/ppazosp/projects/labTFG/phase1-pablo/evals/reports/2026-06-29-caso2-pdf-corpus/artifact-bundle/corpus/manifest.json`
- `/Users/ppazosp/projects/labTFG/phase1-pablo/evals/reports/2026-06-29-caso2-pdf-corpus/artifact-bundle/kg_snapshot_2026-06-29.json`

7. Report claims are sometimes stronger than the implementation

Some formulations use simplified one-step or grid-world approximations of active inference and predictive coding. This is suitable for simulation, but the report should label them as implementation approximations.

Evidence:

- formulation markdown files under `/Users/ppazosp/projects/labTFG/phase1-pablo/evals/reports/2026-06-29-caso2-pdf-corpus/artifact-bundle/storage/research/80d9be2e-8521-4e58-b982-9c1da697297c/formulations/`

# Manual expert review needed

An expert should review:

- whether the final 4-paradigm taxonomy is the right level for the TFG, or whether Bayesian brain and active inference should be separate paradigms
- whether formulations that cross paradigms should be duplicated, nested or moved
- whether the parameter defaults are acceptable simulation choices and clearly marked as such
- whether `DERIVES_FROM` should link parameters to per-paradigm postulates, and whether the missing postulates should be created
- whether duplicate model files should be removed from future bundles or marked as aliases
- whether the KG should include cited-but-not-supplied papers as normal Paper nodes or as citation-only nodes

# Numeric score

Score: 78 out of 100.

Breakdown:

- corpus faithfulness: 18 out of 20
- paradigm quality: 13 out of 20
- formulation quality: 16 out of 20
- model quality: 17 out of 20
- memory and artifact quality: 9 out of 15
- error and warning handling: 5 out of 5

The score is above the pass threshold because the run produced coherent corpus-grounded paradigms, formulations and runnable-style models. It is below a clean pass because KG traceability is damaged by missing postulate endpoints, the taxonomy needs manual review, and duplicate model artifacts weaken reuse.
