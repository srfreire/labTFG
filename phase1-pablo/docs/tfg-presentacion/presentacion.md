---
marp: true
theme: labdark
paginate: true
footer: 'Pablo Pazos Parada · Laboratorio virtual para la toma de decisiones humanas · USC'
---

<!-- _class: title -->
<!-- _paginate: false -->
<!-- _footer: '' -->

# Laboratorio virtual para la toma de decisiones humanas

<span class="subtitle">Fase 1 — de literatura científica a modelos ejecutables</span>

<div class="meta">
Pablo Pazos Parada<br>
Grado en Ingeniería Informática · USC · 2026<br>
Tutor: Eduardo Manuel Sánchez Vila
</div>

---

# Una descripción no es un modelo

<div class="big">"Simular regulación homeostática"</div>

<div class="note">Faltan autores · variables · ecuaciones · acciones · pruebas</div>

---

# La solución separa las decisiones

Cada transformación de representación deja un artefacto revisable: un paso, una responsabilidad, una traza.

<div class="diagram">
<svg viewBox="0 0 1140 200" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid meet">
  <defs>
    <marker id="a" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
      <path d="M0,0 L6,3 L0,6" fill="none" stroke="rgba(255,255,255,0.4)" stroke-width="1.5"/>
    </marker>
  </defs>
  <rect x="10"   y="70" width="150" height="60" rx="8" fill="#0d0d0d" stroke="rgba(255,255,255,0.3)" stroke-width="1.5"/>
  <rect x="208"  y="70" width="150" height="60" rx="8" fill="#0d0d0d" stroke="rgba(255,255,255,0.3)" stroke-width="1.5"/>
  <rect x="406"  y="70" width="150" height="60" rx="8" fill="#0d0d0d" stroke="rgba(255,255,255,0.3)" stroke-width="1.5"/>
  <rect x="604"  y="70" width="150" height="60" rx="8" fill="#0d0d0d" stroke="rgba(255,255,255,0.3)" stroke-width="1.5"/>
  <rect x="802"  y="70" width="150" height="60" rx="8" fill="#0d0d0d" stroke="rgba(255,255,255,0.3)" stroke-width="1.5"/>
  <rect x="1000" y="70" width="130" height="60" rx="8" fill="#0d0d0d" stroke="#fff" stroke-width="2.5"/>
  <text x="85"   y="106" fill="#fff" font-family="Satoshi,sans-serif" font-size="20" text-anchor="middle">descripción</text>
  <text x="283"  y="106" fill="#fff" font-family="Satoshi,sans-serif" font-size="20" text-anchor="middle">Researcher</text>
  <text x="481"  y="106" fill="#fff" font-family="Satoshi,sans-serif" font-size="20" text-anchor="middle">Formalizer</text>
  <text x="679"  y="106" fill="#fff" font-family="Satoshi,sans-serif" font-size="20" text-anchor="middle">Reasoner</text>
  <text x="877"  y="106" fill="#fff" font-family="Satoshi,sans-serif" font-size="20" text-anchor="middle">Builder</text>
  <text x="1065" y="106" fill="#fff" font-family="Satoshi,sans-serif" font-size="19" text-anchor="middle">DecisionModel</text>
  <line x1="164" y1="100" x2="204" y2="100" stroke="rgba(255,255,255,0.4)" stroke-width="1.5" marker-end="url(#a)"/>
  <line x1="362" y1="100" x2="402" y2="100" stroke="rgba(255,255,255,0.4)" stroke-width="1.5" marker-end="url(#a)"/>
  <line x1="560" y1="100" x2="600" y2="100" stroke="rgba(255,255,255,0.4)" stroke-width="1.5" marker-end="url(#a)"/>
  <line x1="758" y1="100" x2="798" y2="100" stroke="rgba(255,255,255,0.4)" stroke-width="1.5" marker-end="url(#a)"/>
  <line x1="956" y1="100" x2="996" y2="100" stroke="rgba(255,255,255,0.4)" stroke-width="1.5" marker-end="url(#a)"/>
</svg>
</div>

<div class="note">deep/*.md → formulations/*.md → reasoner/*.json → builder/*_model.py</div>

---

# Arquitectura del sistema

El usuario entra por CLI o web; un servidor con Router y agentes orquesta el trabajo; los servicios compartidos guardan estado, artefactos y conocimiento.

<div class="diagram">
<svg viewBox="0 0 1000 420" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid meet">
  <defs>
    <marker id="b" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
      <path d="M0,0 L6,3 L0,6" fill="none" stroke="rgba(255,255,255,0.35)" stroke-width="1.2"/>
    </marker>
  </defs>
  <rect x="330" y="12" width="340" height="58" rx="6" fill="none" stroke="rgba(255,255,255,0.2)" stroke-width="1.2"/>
  <text x="500" y="30" fill="rgba(255,255,255,0.5)" font-family="Satoshi,sans-serif" font-size="13" text-anchor="middle">equipo del usuario</text>
  <rect x="345" y="38" width="90" height="24" rx="4" fill="#0d0d0d" stroke="rgba(255,255,255,0.3)" stroke-width="1.2"/><text x="390" y="54" fill="#fff" font-family="Satoshi,sans-serif" font-size="15" text-anchor="middle">CLI</text>
  <rect x="455" y="38" width="90" height="24" rx="4" fill="#0d0d0d" stroke="rgba(255,255,255,0.3)" stroke-width="1.2"/><text x="500" y="54" fill="#fff" font-family="Satoshi,sans-serif" font-size="15" text-anchor="middle">web</text>
  <rect x="565" y="38" width="90" height="24" rx="4" fill="#0d0d0d" stroke="rgba(255,255,255,0.3)" stroke-width="1.2"/><text x="610" y="54" fill="#fff" font-family="Satoshi,sans-serif" font-size="15" text-anchor="middle">evals</text>
  <rect x="360" y="110" width="280" height="180" rx="6" fill="none" stroke="rgba(255,255,255,0.2)" stroke-width="1.2"/>
  <text x="500" y="128" fill="rgba(255,255,255,0.5)" font-family="Satoshi,sans-serif" font-size="13" text-anchor="middle">servidor fase 1</text>
  <rect x="390" y="136" width="220" height="30" rx="4" fill="#0d0d0d" stroke="rgba(255,255,255,0.3)" stroke-width="1.2"/><text x="500" y="156" fill="#fff" font-family="Satoshi,sans-serif" font-size="15" text-anchor="middle">FastAPI · REST + WebSocket</text>
  <rect x="390" y="176" width="220" height="30" rx="4" fill="#0d0d0d" stroke="rgba(255,255,255,0.3)" stroke-width="1.2"/><text x="500" y="196" fill="#fff" font-family="Satoshi,sans-serif" font-size="15" text-anchor="middle">Router · máquina de estados</text>
  <rect x="390" y="216" width="220" height="30" rx="4" fill="#0d0d0d" stroke="rgba(255,255,255,0.3)" stroke-width="1.2"/><text x="500" y="236" fill="#fff" font-family="Satoshi,sans-serif" font-size="15" text-anchor="middle">Agentes especializados</text>
  <rect x="390" y="256" width="220" height="26" rx="4" fill="#0d0d0d" stroke="rgba(255,255,255,0.3)" stroke-width="1.2"/><text x="500" y="273" fill="#fff" font-family="Satoshi,sans-serif" font-size="15" text-anchor="middle">Herramientas</text>
  <line x1="500" y1="62" x2="500" y2="134" stroke="rgba(255,255,255,0.35)" stroke-width="1.2" marker-end="url(#b)"/>
  <rect x="300" y="330" width="400" height="78" rx="6" fill="none" stroke="rgba(255,255,255,0.2)" stroke-width="1.2"/>
  <text x="500" y="348" fill="rgba(255,255,255,0.5)" font-family="Satoshi,sans-serif" font-size="13" text-anchor="middle">servicios compartidos</text>
  <ellipse cx="355" cy="378" rx="34" ry="9" fill="#0d0d0d" stroke="rgba(255,255,255,0.3)" stroke-width="1.2"/><path d="M321,378 v18 a34,9 0 0 0 68,0 v-18" fill="#0d0d0d" stroke="rgba(255,255,255,0.3)" stroke-width="1.2"/><text x="355" y="384" fill="#fff" font-family="Satoshi,sans-serif" font-size="14" text-anchor="middle">Neo4j</text>
  <ellipse cx="445" cy="378" rx="34" ry="9" fill="#0d0d0d" stroke="rgba(255,255,255,0.3)" stroke-width="1.2"/><path d="M411,378 v18 a34,9 0 0 0 68,0 v-18" fill="#0d0d0d" stroke="rgba(255,255,255,0.3)" stroke-width="1.2"/><text x="445" y="384" fill="#fff" font-family="Satoshi,sans-serif" font-size="14" text-anchor="middle">Qdrant</text>
  <ellipse cx="545" cy="378" rx="38" ry="9" fill="#0d0d0d" stroke="rgba(255,255,255,0.3)" stroke-width="1.2"/><path d="M507,378 v18 a38,9 0 0 0 76,0 v-18" fill="#0d0d0d" stroke="rgba(255,255,255,0.3)" stroke-width="1.2"/><text x="545" y="384" fill="#fff" font-family="Satoshi,sans-serif" font-size="14" text-anchor="middle">Postgres</text>
  <ellipse cx="645" cy="378" rx="34" ry="9" fill="#0d0d0d" stroke="rgba(255,255,255,0.3)" stroke-width="1.2"/><path d="M611,378 v18 a34,9 0 0 0 68,0 v-18" fill="#0d0d0d" stroke="rgba(255,255,255,0.3)" stroke-width="1.2"/><text x="645" y="384" fill="#fff" font-family="Satoshi,sans-serif" font-size="14" text-anchor="middle">MinIO</text>
  <line x1="470" y1="290" x2="420" y2="350" stroke="rgba(255,255,255,0.35)" stroke-width="1.2" marker-end="url(#b)"/>
  <line x1="560" y1="290" x2="620" y2="350" stroke="rgba(255,255,255,0.35)" stroke-width="1.2" marker-end="url(#b)"/>
  <rect x="740" y="200" width="230" height="70" rx="6" fill="none" stroke="rgba(255,255,255,0.2)" stroke-width="1.2"/>
  <text x="855" y="220" fill="rgba(255,255,255,0.5)" font-family="Satoshi,sans-serif" font-size="13" text-anchor="middle">APIs externas</text>
  <text x="855" y="242" fill="#fff" font-family="Satoshi,sans-serif" font-size="15" text-anchor="middle">LLM · rerank</text>
  <text x="855" y="262" fill="#fff" font-family="Satoshi,sans-serif" font-size="15" text-anchor="middle">búsqueda web · embeddings</text>
  <line x1="612" y1="235" x2="738" y2="235" stroke="rgba(255,255,255,0.35)" stroke-width="1.2" marker-end="url(#b)"/>
</svg>
</div>

---

# Workflow de agentes

El Router avanza etapa a etapa y para en cada puerta de revisión: el usuario aprueba o pide corrección. Si rechaza, reprograma solo la etapa afectada.

<div class="diagram">
<svg viewBox="0 0 900 440" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid meet">
  <defs>
    <marker id="c" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
      <path d="M0,0 L6,3 L0,6" fill="none" stroke="rgba(255,255,255,0.35)" stroke-width="1.2"/>
    </marker>
  </defs>
  <line x1="225" y1="30" x2="225" y2="430" stroke="rgba(255,255,255,0.15)" stroke-width="1"/>
  <line x1="450" y1="30" x2="450" y2="430" stroke="rgba(255,255,255,0.15)" stroke-width="1"/>
  <line x1="675" y1="30" x2="675" y2="430" stroke="rgba(255,255,255,0.15)" stroke-width="1"/>
  <text x="112" y="22" fill="rgba(255,255,255,0.6)" font-family="Satoshi,sans-serif" font-size="16" text-anchor="middle">Usuario</text>
  <text x="337" y="22" fill="rgba(255,255,255,0.6)" font-family="Satoshi,sans-serif" font-size="16" text-anchor="middle">Router</text>
  <text x="562" y="22" fill="rgba(255,255,255,0.6)" font-family="Satoshi,sans-serif" font-size="16" text-anchor="middle">Agentes</text>
  <text x="787" y="22" fill="rgba(255,255,255,0.6)" font-family="Satoshi,sans-serif" font-size="16" text-anchor="middle">Memoria</text>
  <rect x="40"  y="45"  width="145" height="30" rx="15" fill="#0d0d0d" stroke="rgba(255,255,255,0.3)" stroke-width="1.2"/><text x="112" y="64"  fill="#fff" font-family="Satoshi,sans-serif" font-size="13" text-anchor="middle">describe problema</text>
  <rect x="270" y="95"  width="135" height="30" rx="15" fill="#0d0d0d" stroke="rgba(255,255,255,0.3)" stroke-width="1.2"/><text x="337" y="114" fill="#fff" font-family="Satoshi,sans-serif" font-size="13" text-anchor="middle">clasifica</text>
  <rect x="490" y="145" width="145" height="30" rx="15" fill="#0d0d0d" stroke="rgba(255,255,255,0.3)" stroke-width="1.2"/><text x="562" y="164" fill="#fff" font-family="Satoshi,sans-serif" font-size="13" text-anchor="middle">Researcher</text>
  <rect x="40"  y="195" width="145" height="30" rx="15" fill="#0d0d0d" stroke="rgba(255,255,255,0.3)" stroke-width="1.2"/><text x="112" y="214" fill="#fff" font-family="Satoshi,sans-serif" font-size="13" text-anchor="middle">revisa paradigmas</text>
  <rect x="490" y="245" width="145" height="30" rx="15" fill="#0d0d0d" stroke="rgba(255,255,255,0.3)" stroke-width="1.2"/><text x="562" y="264" fill="#fff" font-family="Satoshi,sans-serif" font-size="13" text-anchor="middle">Formalizer</text>
  <rect x="40"  y="295" width="145" height="30" rx="15" fill="#0d0d0d" stroke="rgba(255,255,255,0.3)" stroke-width="1.2"/><text x="112" y="314" fill="#fff" font-family="Satoshi,sans-serif" font-size="13" text-anchor="middle">selecciona formul.</text>
  <rect x="490" y="345" width="145" height="30" rx="15" fill="#0d0d0d" stroke="rgba(255,255,255,0.3)" stroke-width="1.2"/><text x="562" y="364" fill="#fff" font-family="Satoshi,sans-serif" font-size="13" text-anchor="middle">Reasoner + Builder</text>
  <rect x="40"  y="395" width="145" height="30" rx="15" fill="#0d0d0d" stroke="rgba(255,255,255,0.3)" stroke-width="1.2"/><text x="112" y="414" fill="#fff" font-family="Satoshi,sans-serif" font-size="13" text-anchor="middle">aprueba modelo</text>
  <rect x="715" y="395" width="145" height="30" rx="15" fill="#0d0d0d" stroke="rgba(255,255,255,0.3)" stroke-width="1.2"/><text x="787" y="414" fill="#fff" font-family="Satoshi,sans-serif" font-size="13" text-anchor="middle">consolida</text>
  <path d="M112,75 v20 h158"   fill="none" stroke="rgba(255,255,255,0.35)" stroke-width="1.2" marker-end="url(#c)"/>
  <path d="M337,125 v20 h153"  fill="none" stroke="rgba(255,255,255,0.35)" stroke-width="1.2" marker-end="url(#c)"/>
  <path d="M490,175 h-378 v20" fill="none" stroke="rgba(255,255,255,0.35)" stroke-width="1.2" marker-end="url(#c)"/>
  <path d="M112,225 v20 h378"  fill="none" stroke="rgba(255,255,255,0.35)" stroke-width="1.2" marker-end="url(#c)"/>
  <path d="M490,275 h-378 v20" fill="none" stroke="rgba(255,255,255,0.35)" stroke-width="1.2" marker-end="url(#c)"/>
  <path d="M112,325 v20 h378"  fill="none" stroke="rgba(255,255,255,0.35)" stroke-width="1.2" marker-end="url(#c)"/>
  <path d="M490,375 h-378 v20" fill="none" stroke="rgba(255,255,255,0.35)" stroke-width="1.2" marker-end="url(#c)"/>
  <path d="M185,410 h530"      fill="none" stroke="rgba(255,255,255,0.35)" stroke-width="1.2" marker-end="url(#c)"/>
</svg>
</div>

---

# Arquitectura de memoria

El MemoryAgent escribe conocimiento aceptado; el Retriever lo devuelve con procedencia cuando un agente llama `retrieve_knowledge`.

<div class="diagram">
<svg viewBox="0 0 940 380" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid meet">
  <defs>
    <marker id="d" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
      <path d="M0,0 L6,3 L0,6" fill="none" stroke="rgba(255,255,255,0.35)" stroke-width="1.2"/>
    </marker>
  </defs>
  <rect x="20" y="60"  width="150" height="50" rx="6" fill="#0d0d0d" stroke="rgba(255,255,255,0.3)" stroke-width="1.2"/><text x="95" y="90" fill="#fff" font-family="Satoshi,sans-serif" font-size="15" text-anchor="middle">Router</text>
  <rect x="20" y="250" width="150" height="50" rx="6" fill="#0d0d0d" stroke="rgba(255,255,255,0.3)" stroke-width="1.2"/><text x="95" y="280" fill="#fff" font-family="Satoshi,sans-serif" font-size="15" text-anchor="middle">Agentes</text>
  <rect x="290" y="45"  width="180" height="80" rx="6" fill="#0d0d0d" stroke="rgba(255,255,255,0.3)" stroke-width="1.2"/><text x="380" y="78"  fill="#fff" font-family="Satoshi,sans-serif" font-size="15" text-anchor="middle">MemoryAgent</text><text x="380" y="100" fill="rgba(255,255,255,0.5)" font-family="Satoshi,sans-serif" font-size="12" text-anchor="middle">extrae · escribe</text>
  <rect x="290" y="235" width="180" height="80" rx="6" fill="#0d0d0d" stroke="rgba(255,255,255,0.3)" stroke-width="1.2"/><text x="380" y="268" fill="#fff" font-family="Satoshi,sans-serif" font-size="15" text-anchor="middle">Retriever</text><text x="380" y="290" fill="rgba(255,255,255,0.5)" font-family="Satoshi,sans-serif" font-size="12" text-anchor="middle">híbrido · rerank</text>
  <line x1="170" y1="85"  x2="288" y2="85"  stroke="rgba(255,255,255,0.35)" stroke-width="1.2" marker-end="url(#d)"/>
  <line x1="170" y1="275" x2="288" y2="275" stroke="rgba(255,255,255,0.35)" stroke-width="1.2" marker-end="url(#d)"/>
  <ellipse cx="760" cy="55"  rx="42" ry="11" fill="#0d0d0d" stroke="rgba(255,255,255,0.3)" stroke-width="1.2"/><path d="M718,55 v20 a42,11 0 0 0 84,0 v-20" fill="#0d0d0d" stroke="rgba(255,255,255,0.3)" stroke-width="1.2"/><text x="760" y="80" fill="#fff" font-family="Satoshi,sans-serif" font-size="14" text-anchor="middle">MinIO</text>
  <ellipse cx="760" cy="140" rx="42" ry="11" fill="#0d0d0d" stroke="rgba(255,255,255,0.3)" stroke-width="1.2"/><path d="M718,140 v20 a42,11 0 0 0 84,0 v-20" fill="#0d0d0d" stroke="rgba(255,255,255,0.3)" stroke-width="1.2"/><text x="760" y="165" fill="#fff" font-family="Satoshi,sans-serif" font-size="14" text-anchor="middle">Postgres</text>
  <ellipse cx="760" cy="225" rx="42" ry="11" fill="#0d0d0d" stroke="rgba(255,255,255,0.3)" stroke-width="1.2"/><path d="M718,225 v20 a42,11 0 0 0 84,0 v-20" fill="#0d0d0d" stroke="rgba(255,255,255,0.3)" stroke-width="1.2"/><text x="760" y="250" fill="#fff" font-family="Satoshi,sans-serif" font-size="14" text-anchor="middle">Neo4j</text>
  <ellipse cx="760" cy="310" rx="42" ry="11" fill="#0d0d0d" stroke="rgba(255,255,255,0.3)" stroke-width="1.2"/><path d="M718,310 v20 a42,11 0 0 0 84,0 v-20" fill="#0d0d0d" stroke="rgba(255,255,255,0.3)" stroke-width="1.2"/><text x="760" y="335" fill="#fff" font-family="Satoshi,sans-serif" font-size="14" text-anchor="middle">Qdrant</text>
  <path d="M470,70  C570,58 640,52 716,52"   fill="none" stroke="rgba(255,255,255,0.35)" stroke-width="1.2" marker-end="url(#d)"/>
  <path d="M470,95  C570,120 640,134 716,138" fill="none" stroke="rgba(255,255,255,0.35)" stroke-width="1.2" marker-end="url(#d)"/>
  <path d="M470,265 C570,240 640,228 716,224" fill="none" stroke="rgba(255,255,255,0.35)" stroke-width="1.2" marker-end="url(#d)"/>
  <path d="M470,290 C570,300 640,306 716,308" fill="none" stroke="rgba(255,255,255,0.35)" stroke-width="1.2" marker-end="url(#d)"/>
</svg>
</div>

---

# Tres métodos definen cada modelo

Un contrato mínimo que la Fase 2 carga por duck typing, sin adaptador.

- `decide(perception) -> Action` — elige acción, sin mutar estado
- `update(action, reward, new_perception)` — aprende tras recompensa
- `get_state() -> dict` — expone los internos

---

# La validación cubre cada transición

Cada capa protege un salto de representación distinto, de la estructura a la integración.

| paso | capa | qué protege |
|---|---|---|
| 01 | estructura | schemas y contratos |
| 02 | pipeline | estados, persistencia y reanudación |
| 03 | código | importación y pruebas |
| 04 | memoria | escritura, recuperación y procedencia |
| 05 | integración | carga dinámica en Fase 2 |

---

# Dos casos produjeron 27 modelos

Dos paradigmas reales recorridos de extremo a extremo. Ambos pipelines pasaron; ambos jueces aprobaron con reservas.

| caso | papers | paradigmas | specs | modelos | juez |
|---|---|---|---|---|---|
| caso 01 | 3 | 6 | 18 | 15 | 72/100 |
| caso 02 | 3 | 4 | 12 | 12 | 78/100 |

---

# Un PASS técnico no prueba validez científica

<div class="cols">
<div>
<h2>demostrado</h2>

- el pipeline completa etapas
- los artefactos son auditables
- los modelos se ejecutan
</div>
<div>
<h2>pendiente</h2>

- validación por expertos
- comparación con modelos manuales
- más dominios y repeticiones
</div>
</div>

---

# La aportación es el proceso

<div class="big">repetible · trazable · acumulativo · ejecutable</div>

<div class="note">El sistema acelera el trabajo. El investigador mantiene el criterio.</div>
