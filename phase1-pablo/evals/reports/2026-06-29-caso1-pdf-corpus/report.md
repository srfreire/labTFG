# Eval suite: `caso1-pdf-corpus`

_Source_: `evals/suites/caso1-pdf-corpus.yaml`
_Stages_: `research, formalize, reason, build`
_Eval corpus_: `/Users/ppazosp/Downloads/Evaluacion_CASO1.zip`
_Topics_: 1 declared, 1 run
_Duration_: 6152.0s
_Cost (est.)_: $33.71

**Overall**: PASS

## KG growth

| | Before | After | Δ |
|---|---:|---:|---:|
| Nodes | 0 | 433 | +433 |
| Relations | 0 | 518 | +518 |

## Topic: PDF-corpus evaluation case 1. Using only the papers available through the eval web_search and search_papers tools, identify and investigate all decision-making paradigms that explain human dietary choice, valuation, reward, and self-control in food decisions. Treat the corpus as the complete literature universe: split, merge, and name paradigms according to the evidence in the papers, then carry every discovered paradigm and formulation forward.

_run_: `bd5e6d0d-382f-46f9-9900-2994e0d5eed3` — _ok_
_paradigms_: attribute-based-value-computation, dlpfc-self-control-modulation, drift-diffusion-model, goal-directed-vs-habitual-control, homeostatic-regulation-of-food-valuation, pavlovian-control-of-food-approach

**Memory writes**:
- `researcher` — status=ok, nodes_created=28, relations_created=30, facts=17
- `formalizer` — status=ok, nodes_created=296, relations_created=324, facts=243
- `reasoner` — status=ok, nodes_created=94, relations_created=130, facts=607
- `builder` — status=ok, nodes_created=15, relations_created=30, facts=180

## Timing

**Stages (avg ms across topics)**:

| Stage | n | avg ms |
|---|---:|---:|
| build | 1 | 589430 |
| classify_umbrella | 1 | 3027 |
| consolidation | 1 | 124709 |
| formalize | 1 | 166863 |
| get_env_spec | 1 | 6 |
| memory_build | 1 | 413139 |
| memory_formalize | 1 | 1281033 |
| memory_reason | 1 | 2764923 |
| memory_research | 1 | 228296 |
| reason | 1 | 341618 |
| research | 1 | 237534 |
| review_build | 1 | 58 |
| review_formalize | 1 | 77 |
| review_reason | 1 | 34 |
| review_research | 1 | 18 |

**Tool calls**:

| Tool | Calls | p50 ms | p95 ms | avg ms |
|---|---:|---:|---:|---:|
| launch_deep_research | 6 | 101697 | 103201 | 96111 |
| read_file | 46 | 14 | 55 | 19 |
| read_report | 6 | 15 | 18 | 14 |
| retrieve_knowledge | 88 | 6026 | 10511 | 5247 |
| run_tests | 55 | 523 | 587 | 531 |
| search_papers | 13 | 5 | 10 | 7 |
| web_search | 14 | 8 | 14 | 8 |
| write_file | 98 | 34 | 56 | 33 |
