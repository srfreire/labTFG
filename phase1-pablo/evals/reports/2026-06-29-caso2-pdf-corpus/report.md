# Eval suite: `caso2-pdf-corpus`

_Source_: `evals/suites/caso2-pdf-corpus.yaml`
_Stages_: `research, formalize, reason, build`
_Eval corpus_: `/Users/ppazosp/Downloads/Evaluacion_CASO2.zip`
_Topics_: 1 declared, 1 run
_Duration_: 4961.8s
_Cost (est.)_: $24.47

**Overall**: PASS

## KG growth

| | Before | After | Δ |
|---|---:|---:|---:|
| Nodes | 0 | 272 | +272 |
| Relations | 0 | 352 | +352 |

## Topic: PDF-corpus evaluation case 2. Using only the papers available through the eval web_search and search_papers tools, identify and investigate all decision-making paradigms that explain body regulation, homeostasis, interoception, active inference, and reinforcement learning in adaptive behavior. Treat the corpus as the complete literature universe: split, merge, and name paradigms according to the evidence in the papers, then carry every discovered paradigm and formulation forward.

_run_: `80d9be2e-8521-4e58-b982-9c1da697297c` — _ok_
_paradigms_: homeostatic-regulation, homeostatic-reinforcement-learning, interoceptive-active-inference, predictive-coding

**Memory writes**:
- `researcher` — status=ok, nodes_created=30, relations_created=38, facts=24
- `formalizer` — status=ok, nodes_created=137, relations_created=160, facts=122
- `reasoner` — status=ok, nodes_created=93, relations_created=125, facts=378
- `builder` — status=ok, nodes_created=12, relations_created=24, facts=132

## Timing

**Stages (avg ms across topics)**:

| Stage | n | avg ms |
|---|---:|---:|
| build | 1 | 773752 |
| classify_umbrella | 1 | 4178 |
| consolidation | 1 | 116833 |
| formalize | 1 | 174167 |
| get_env_spec | 1 | 9 |
| memory_build | 1 | 359579 |
| memory_formalize | 1 | 800387 |
| memory_reason | 1 | 1960025 |
| memory_research | 1 | 169208 |
| reason | 1 | 361041 |
| research | 1 | 241182 |
| review_build | 1 | 43 |
| review_formalize | 1 | 86 |
| review_reason | 1 | 32 |
| review_research | 1 | 9 |

**Tool calls**:

| Tool | Calls | p50 ms | p95 ms | avg ms |
|---|---:|---:|---:|---:|
| launch_deep_research | 4 | 103684 | 110301 | 103505 |
| read_file | 31 | 12 | 49 | 26 |
| read_report | 4 | 17 | 20 | 16 |
| retrieve_knowledge | 60 | 5327 | 11368 | 5348 |
| run_tests | 40 | 574 | 1586 | 725 |
| search_papers | 9 | 3 | 8 | 5 |
| web_search | 9 | 6 | 9 | 6 |
| write_file | 72 | 40 | 107 | 53 |
