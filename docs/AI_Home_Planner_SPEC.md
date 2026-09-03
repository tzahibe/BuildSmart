# AI Home Planner — Product & Engineering Specification

## 1. תיאור הפרויקט

AI Home Planner היא אפליקציה שמלווה משתמש ראשוני שרוצה לבנות פרויקט מגורים.

המשתמש מזין:
- כתובת / מגרש מיועד
- גודל המגרש
- דרישות בנייה (מספר קומות ומטרות)
- מספר קומות
- שטח בנוי רצוי
- מרפסות
- ממ"ד
- חניה
- בריכה
- מרפסות
- העדפות תכנון

המערכת:
1. מפרשת את דרישות המשתמש ל-structured requirements.
2. מאתרת את המיקום ומסמכת תכנון רלוונטיים.
3. מאתרת תוכניות, תבחיני התקנות רלוונטיים.
4. מחלצת constraints תקנוניים.
5. מייצרת תכנון ראשוני פרמטרי.
6. מאמתת את התכנון מול constraints.
7. מציגה הסברים, אי-ודאויות ומקורות.
8. מאפשרת ביצוע What-if ולשפר את התכנון.
9. מודדת את איכות ה-RAG, ה-Agent וה-compliance באמצעות Evaluation.

> המערכת אינה מהווה תכנון סופי או תחליף לאדריכל. היא מיועדת לשלב ראשוני, ואינה מס, עורך דין או מסמך רשמי של רשות.

---

# 2. עקרונות ארכיטקטוניים

## Principle A — LLM אינו מקור אמת ארכיטקטוני

ה-LLM אחראי על:
- הבנת intent
- פירוק דרישות
- תרגום פעולות
- קריאת tools
- הסקת מסקנות מתוך evidence

כל מדידות מספריות אחראי על:
- חישובי שטחים
- מגבלות
- setbacks
- intersections
- geometry
- אימות constraints

## Principle B — כל טענה רגולטורית מחייבת Evidence

כל טענה חייבת:
> "המותר הוא 220 מ"ר"

חייבת:
- מקור
- מספר מסמך/תוכנית
- סעיף/עמוד ממנו הופק
- timestamp/version
- confidence

## Principle C — אין מחליטים במקום המשתמש

אם המערכת אינה בטוחה בגבי constraint:
`UNKNOWN`

ולא:
`ALLOWED`

## Principle D — מפרידים בין Retrieval לבין Reasoning

```text
Sources
  ↓
Retrieval
  ↓
Evidence
  ↓
Rule extraction
  ↓
Deterministic validation
  ↓
LLM explanation
```

## Principle E — MVP לפני Multi-Agent Complexity

מתחילים עם Agent אחד שמסתפק tools ברור.
רק כאשר אנחנו שהflow עולה מפרקים ל-Agents.

---

# 3. MVP Scope

ה-MVP מתמקד ב:

**עיר אחת + מגרש עם מידע קרקע + תכנון ראשוני + compliance בסיסי.**

הרעיון:
- מתמקדים בעיר/רשות אחת.
- זה נותן פתרון את המורכבות המרובה בשלב הראשוני.

---

# 4. Feature 01 — Project Creation

### User Story

המשתמש חדש רוצה לפתוח פרויקט חדש ולתאר את דרישות הבנייה.

### Input

```json
{
  "address": "...",
  "plot_area_m2": 500,
  "description": "בית בן קומתיים 220 מ״ר, 4 חדרי שינה..."
}
```

### Requirements

- יצירת project_id.
- שמירת user requirements.
- שמירת source text המקורי.
- status של הפרויקט.
- אפשרות עדכון דרישות.

### Acceptance Criteria

- ניתן ליצור פרויקט.
- ניתן לטעון פרויקט קיים.
- כל שדה נשמר כמקור המקורי.

---

# 5. Feature 02 — Natural Language Requirement Parser

### מטרה

מנתח תיאור חופשי ל-schema מובנה.

### Example

Input:

> "אני רוצה בית בן קומתיים בשטח 220 מ"ר, 4 חדרי שינה, ממ"ד, חניה ל-2 עם בריכה 8 על 4 בחצר האחורית."

Output:

```json
{
  "floors": 2,
  "target_built_area_m2": 220,
  "bedrooms": 4,
  "safe_room": true,
  "parking_spaces": 2,
  "pool": {
    "requested": true,
    "length_m": 8,
    "width_m": 4
  }
}
```

### Important

כל field צריך תיוג:
- requested
- inferred
- unknown

אין להמציא נתונים שהמשתמש לא נתן.

---

# 6. Feature 03 — Plot / Location Resolution

### מטרה

מתרגם כתובת למידע תכנוני רלוונטי.

Pipeline:

```text
Address
 ↓
Geocoding
 ↓
Coordinates
 ↓
Parcel identification
 ↓
Planning entities
```

### Output

```json
{
  "address": "...",
  "coordinates": {
    "lat": 0,
    "lng": 0
  },
  "parcel": {
    "block": "...",
    "parcel": "..."
  }
}
```

### Acceptance Criteria

- כתובת מתורגמת למיקום.
- coordinates נשמרים.
- parcel identification נשמר כאשר ניתן.
- כאשר אין certainty — מסומן `UNKNOWN`.

---

# 7. Feature 04 — Planning Data Connector

### מטרה

יצירת abstraction למקורות תכנון רשמיים.

המערכת צריכה ממשק אחיד:

```text
PlanningDataProvider
```

וכל implementation ספציפי.

### Interface

```python
class PlanningDataProvider:
    def find_plans_for_location(...)
    def get_plan(...)
    def get_plan_documents(...)
    def get_geographic_data(...)
```

### MVP

ממש provider ראשוני עבור מקורות ציבוריים או פיקטיביים ברורים.

אין hard-code של ערכי תוכן business logic.

---

# 8. Feature 05 — Regulatory Document Ingestion

### מטרה

מעבד מסמכים:
- תוכניות תב"ע
- תשריטים
- נספחים
- הנחיות
- מסמכי רשות
- תקנות בנייה ואחרות

### Pipeline

```text
Document
 ↓
Download
 ↓
Parse
 ↓
OCR if required
 ↓
Normalize
 ↓
Chunk
 ↓
Metadata
 ↓
Embedding
 ↓
Vector DB
```

### Metadata

```json
{
  "document_id": "...",
  "plan_id": "...",
  "authority": "...",
  "document_type": "regulation",
  "page": 12,
  "section": "4.2",
  "effective_date": "...",
  "source_url": "..."
}
```

---

# 9. Feature 06 — Hybrid RAG

RAG חייב לשלב:

- semantic/vector search
- lexical/BM25 search
- metadata filtering
- reranking

Pipeline:

```text
Query
 ↓
Vector Search ─┐
                ├─ Fusion → Reranker → Evidence
BM25 ───────────┘
```

### Metadata filters

לדוגמה:

```text
authority = Modi'in
plan_id = XYZ
document_type = instructions
```

---

# 10. Feature 07 — Regulatory Knowledge Extraction

זה אחד ה-features המשמעותיים ביותר.

המערכת לא צריכה רק להחזיר chunks.

היא צריכה לחלץ מהטקסט הרגולטורי constraints.

Example:

```text
"קו בניין קדמי מינימלי 5 מטרים"
```

Output:

```json
{
  "rule_type": "setback",
  "direction": "front",
  "minimum_distance_m": 5,
  "scope": "primary_building",
  "source": {
    "document_id": "...",
    "page": 17,
    "section": "4.3"
  }
}
```

### Constraint Types

ל-MVP:

- max_building_area
- max_floor_area
- max_floors
- max_height
- front_setback
- rear_setback
- side_setback
- parking_spaces
- permitted_use
- pool
- balcony
- basement
- roof
- safe_room

---

# 11. Feature 08 — Regulatory Rule Engine

לא מבצע את האימות רק באמצעות LLM.

יש Rule Engine דטרמיניסטי.

Example:

```python
result = rule_engine.check(
    design=design,
    constraints=constraints
)
```

Output:

```json
{
  "rule": "rear_setback",
  "status": "FAIL",
  "actual": 3.8,
  "required": 5.0,
  "difference": -1.2,
  "evidence_id": "..."
}
```

Statuses:

- PASS
- FAIL
- WARNING
- UNKNOWN
- NOT_APPLICABLE

---

# 12. Feature 09 — Parametric Design Model

לא מייצר floor plan ישירות מהתמונה.

יש model מובנה.

```json
{
  "site": {
    "width_m": 20,
    "depth_m": 25
  },
  "building": {
    "floors": 2
  },
  "rooms": [
    {
      "type": "living_room",
      "floor": 1,
      "area_m2": 35,
      "x": 4,
      "y": 5,
      "width_m": 7,
      "depth_m": 5
    }
  ]
}
```

ה-geometry ניתנת להמרה ל-SVG/Canvas.

---

# 13. Feature 10 — Layout Generator

### Input

- plot geometry
- regulatory constraints
- user requirements

### Output

כמה חלופות פריסה:

```text
Option A — Garden oriented
Option B — Privacy oriented
Option C — Maximum usable area
```

### Objective

ממקסם:

```text
user satisfaction
+
usable area
+
functional layout
```

תוך שמירה על:

```text
hard constraints
```

---

# 14. Feature 11 — Compliance Agent

ה-Agent מקבל:

```text
User requirements
+
Proposed design
+
Regulatory evidence
+
Deterministic rule results
```

ומייצר report.

### Example

```json
{
  "overall_status": "PARTIAL",
  "issues": [
    {
      "severity": "HIGH",
      "rule": "rear_setback",
      "status": "FAIL",
      "explanation": "...",
      "evidence": ["..."]
    }
  ]
}
```

---

# 15. Feature 12 — Verification / Critic Agent

ה-Critic צריך לוודא שאין מצב שגוי בתשובה.

Checks:

- כל claim נתמך?
- כל citation תואם?
- האם נעשה שימוש בתאריך לא נכון?
- האם rule לא עוקב אחר הדרישה?
- האם יש conflict בין מקורות?
- האם המערכת לא מציגה תשובה שגוי כוודאית?

Output:

```json
{
  "verified": false,
  "issues": [
    {
      "claim": "...",
      "reason": "Source does not establish applicability"
    }
  ]
}
```

---

# 16. Feature 13 — What-If / Design Optimization

המשתמש יכול לשנות דרישה:

> "אני רוצה 250 מ"ר במקום 220."

המערכת:

```text
Current Design
 ↓
Changed Requirement
 ↓
Constraint analysis
 ↓
Optimization
 ↓
New layout
 ↓
Compliance
```

המערכת צריכה לשמור היסטוריית דרישות שהשתנו.

---

# 17. Feature 14 — Evidence & Explainability UI

כל אימות רגולטורי צריך להציג:

```text
Requirement
Actual
Status
Source
Section/Page
Confidence
```

Example:

```text
Rear setback

Required: 5.0m
Design:   3.8m
Status:   ❌ FAIL

Source:
Plan XYZ
Section 4.3
Page 17

[Open Source]
```

---

# 18. Feature 15 — Confidence System

Confidence אינו "ניחוש של ה-LLM".

הוא מחשב confidence לפי:

- source quality
- retrieval score
- reranker score
- rule applicability
- verification result
- source freshness
- conflicting sources

Levels:

```text
HIGH
MEDIUM
LOW
UNKNOWN
```

---

# 19. Feature 16 — Evaluation Framework

זה Feature קריטי.

יש Golden Dataset.

```json
{
  "id": "case_001",
  "question": "...",
  "location": "...",
  "expected_rules": [],
  "expected_sources": [],
  "reference_answer": "..."
}
```

### Retrieval metrics

- Recall@K
- Precision@K
- MRR

### Generation metrics

- faithfulness
- answer relevance
- citation correctness

### Compliance metrics

- rule detection accuracy
- applicability accuracy
- false positive rate
- false negative rate

### Agent metrics

- tool selection accuracy
- unnecessary calls
- steps
- latency
- tokens
- cost

---

# 20. Feature 17 — Evaluation Regression

כל שינוי משמעותי בקוד צריך להריץ Evaluation.

```text
git push
 ↓
CI
 ↓
unit tests
 ↓
RAG evaluation
 ↓
compliance evaluation
 ↓
report
```

ה-build נכשל אם:

```text
Recall@5 drops > threshold
OR
Citation accuracy drops
OR
Critical compliance metric drops
```

---

# 21. Feature 18 — Observability

נשמר trace לכל run:

```text
Project
 ├── requirement_parser
 ├── location_resolution
 ├── retrieval
 ├── reranking
 ├── rule_extraction
 ├── design_generation
 ├── compliance
 ├── verification
```

לכל step:

- input
- output
- duration
- tokens
- model
- cost
- errors

---

# 22. Feature 19 — LLM Router

לא כל משימה צריכה מודל חזק.

לדוגמה:

```text
Simple extraction → cheap model
Complex reasoning → strong model
Embeddings → embedding model
Reranking → reranker
```

ה-Router צריך להיות configurable.

---

# 23. Feature 20 — Safety / Regulatory Guardrails

הממשק מציג:

> Preliminary analysis only.

אין להוסיף:

- כל תוצאה UNKNOWN ל-ALLOWED.
- כל תוצאה מקור שאינו מדויק.
- כל תוצאה שמסמן שמדד "מדויק" בלי evidence.
- conflict בין מקורות דורש בדיקה נוספת.
- מניעת השמה דורש בדיקה נוספת.
- תשובות רגולטוריות צריכות citations.

---

# 24. Feature 21 — Web UI

מסכים:

### Dashboard

```text
Projects
New Project
Recent Designs
```

### Project

```text
Requirements
Location
Regulations
Design
Compliance
Evidence
```

### Design

```text
2D Plan
Floor selector
Dimensions
Warnings
```

### Compliance

```text
PASS
FAIL
WARNING
UNKNOWN
```

### Evidence

```text
Source
Document
Section
Relevant excerpt
```

---

# 25. Suggested Tech Stack

## Backend

- Python
- FastAPI
- Pydantic
- PostgreSQL
- PostGIS
- pgvector

## AI

- LLM provider abstraction
- embeddings
- reranker
- LangGraph only where orchestration is useful

## Frontend

- Next.js
- TypeScript
- SVG / Canvas for floor plans

## Infrastructure

- Docker
- Docker Compose
- GitHub Actions

## Testing

- pytest
- integration tests
- evaluation tests

---

# 26. Suggested Repository Structure

```text
ai-home-planner/
│
├── apps/
│   ├── api/
│   └── web/
│
├── packages/
│   ├── domain/
│   ├── geometry/
│   ├── regulations/
│   ├── retrieval/
│   ├── agents/
│   ├── evaluation/
│   └── llm/
│
├── data/
│   ├── raw/
│   ├── processed/
│   └── evaluation/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── evaluation/
│
├── docs/
│   ├── architecture.md
│   ├── decisions.md
│   └── evaluation.md
│
├── infra/
│   └── docker/
│
├── scripts/
│
├── .github/
│   └── workflows/
│
├── docker-compose.yml
├── README.md
└── pyproject.toml
```

---

# 27. Development Phases

## Phase 1 — Foundation

- repository
- FastAPI
- database
- project model
- requirements schema
- basic UI

## Phase 2 — Location

- geocoding abstraction
- parcel abstraction
- planning provider interface

## Phase 3 — RAG

- document ingestion
- chunking
- embeddings
- pgvector
- BM25
- reranking

## Phase 4 — Regulation Engine

- rule schema
- rule extraction
- deterministic validation
- evidence model

## Phase 5 — Design Engine

- parametric geometry
- room model
- site constraints
- SVG floor plan
- layout generation

## Phase 6 — Agents

Start with:

```text
Planning Agent
Regulation Agent
Design Agent
Verification Agent
```

Do not create agents where a normal function is sufficient.

## Phase 7 — Evaluation

- golden dataset
- retrieval metrics
- compliance metrics
- citation metrics
- agent metrics

## Phase 8 — What-if

- modify requirements
- regenerate
- compare versions

## Phase 9 — Observability

- traces
- token usage
- latency
- cost
- failures

## Phase 10 — Production Polish

- authentication if needed
- Docker
- CI
- evaluation regression
- documentation
- demo

---

# 28. First Milestone — "Vertical Slice"

Do NOT start by implementing every feature.

The first target is one complete flow:

```text
Address
  ↓
Resolve location
  ↓
Find one applicable plan
  ↓
Retrieve one relevant document
  ↓
Extract 3-5 constraints
  ↓
Create simple house
  ↓
Validate constraints
  ↓
Display floor plan
  ↓
Display evidence
```

Only after this works end-to-end should additional features be added.

---

# 29. Definition of Done for MVP

The MVP is successful when a user can:

1. Enter an address.
2. Describe a house.
3. Receive structured requirements.
4. Resolve the planning context.
5. Retrieve relevant planning documents.
6. Extract applicable constraints.
7. Generate a parametric preliminary layout.
8. See a 2D floor plan.
9. See PASS/FAIL/WARNING/UNKNOWN for constraints.
10. Click a violation and see its evidence.
11. Change a requirement and regenerate.
12. Run an evaluation dataset.
13. See measurable system quality.

---

# 30. Instructions for Claude Code

Build incrementally.

Before implementing a feature:

1. Inspect the existing repository.
2. Identify existing abstractions.
3. Do not duplicate logic.
4. Define typed schemas first.
5. Add tests.
6. Implement the smallest working version.
7. Run tests.
8. Update documentation.

Do not:
- invent Israeli regulatory data.
- hard-code regulatory values unless they come from a documented fixture.
- treat LLM output as authoritative numeric truth.
- use an image-generation model as the source of geometric truth.
- create unnecessary agents.
- hide uncertainty.
- silently fall back from verified data to guessed data.

Prefer:
- deterministic domain logic
- typed interfaces
- provider abstractions
- evidence-first design
- reproducible evaluations
- small composable modules

Every external data provider must be replaceable.

Every LLM provider must be replaceable.

Every regulatory claim must be traceable to evidence.

---

# 31. Portfolio Goal

The project should demonstrate:

- RAG
- hybrid retrieval
- reranking
- structured LLM outputs
- tool calling
- agent orchestration
- deterministic constraint solving
- geospatial data
- regulatory reasoning
- evaluation
- observability
- CI/CD
- production-oriented architecture

The central engineering principle:

> **Use LLMs for ambiguity and reasoning; use deterministic software for facts, geometry and constraints.**

The core product loop:

```text
USER INTENT
    ↓
STRUCTURED REQUIREMENTS
    ↓
PLANNING CONTEXT
    ↓
REGULATORY RETRIEVAL
    ↓
EVIDENCE
    ↓
CONSTRAINTS
    ↓
PARAMETRIC DESIGN
    ↓
DETERMINISTIC VALIDATION
    ↓
LLM EXPLANATION
    ↓
VERIFICATION
    ↓
DESIGN + COMPLIANCE REPORT
    ↓
WHAT-IF
    ↓
RE-EVALUATE
```
