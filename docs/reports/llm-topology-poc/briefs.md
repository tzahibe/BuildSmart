# 20 stratified briefs (Issue #151, AC-3)

Selected deterministically from the FROZEN, committed 432-context regression corpus (`backend/tests/regression_corpus/corpus.json`) — see `briefs.py`'s own module docstring for the selection method. Every brief below is PLANNED by the current generator (never a REFUSED context), since "the current generator's best topology" needs a solved plan to extract from.

| brief | source_key (project_id) | bedrooms | wet_rooms | safe_room | open_plan | size_tier | aspect_tier | built_area_m2 |
|---|---|---|---|---|---|---|---|---|
| B01 | `89359a62-6065-4950-b32c-e05f2d466319` | 1 | 1 | False | False | large | square | 440.0 |
| B02 | `96e774ed-b8ba-4d8b-af7e-3cab4aa51797` | 1 | 1 | False | True | medium | narrow | 216.0 |
| B03 | `aadfc3e3-3a58-4127-993c-9dfe969beb5b` | 2 | 1 | False | False | medium | wide | 250.0 |
| B04 | `b2ff5f84-1528-4d94-a24f-ae787409ae21` | 2 | 2 | True | False | large | square | 440.0 |
| B05 | `5c445085-ec89-4fe1-876c-97cdbc7c8707` | 2 | 1 | False | True | large | square | 288.0 |
| B06 | `edefd96c-468d-4290-944b-2a733da8ee4d` | 3 | 2 | False | False | large | narrow | 312.0 |
| B07 | `c19159c9-e06b-475c-aebb-eec36f562b3c` | 3 | 2 | True | False | large | square | 360.0 |
| B08 | `ec361aa8-e011-4073-942d-7064e5daff44` | 3 | 1 | False | True | small | square | 132.0 |
| B09 | `d7b102b6-04d7-4cbc-ba4b-550ee6d0bc6f` | 3 | 3 | False | False | large | square | 440.0 |
| B10 | `707a343b-ad99-4cb9-9eb3-28afaa96fbe8` | 4 | 2 | False | False | large | square | 288.0 |
| B11 | `b1252b33-7538-4472-8d27-94caefd9ae30` | 4 | 2 | True | True | medium | narrow | 216.0 |
| B12 | `660b8e68-bb39-4ee5-a8aa-e360a74e5c6f` | 4 | 3 | False | False | large | square | 360.0 |
| B13 | `bbf79316-509d-4065-9609-ff2f45a2ff64` | 4 | 2 | False | True | small | square | 132.0 |
| B14 | `ae07d979-3ce8-4e85-ac63-c65a57391c71` | 5 | 3 | False | False | medium | narrow | 216.0 |
| B15 | `2ee54127-2314-4053-a540-75921b2c5f79` | 5 | 2 | True | False | medium | square | 181.25 |
| B16 | `9b716aea-cfb1-434a-8679-2c56f0c9e4f9` | 5 | 3 | True | True | medium | wide | 216.0 |
| B17 | `7786477a-8136-4b7d-a574-12674f044a38` | 6 | 3 | False | False | medium | wide | 216.0 |
| B18 | `c0062449-9a40-4fe9-8ad7-5a0bd4d0cd1b` | 6 | 3 | True | False | medium | square | 181.25 |
| B19 | `e7d7be8a-d27f-48e6-a94f-adb9a500d23f` | 6 | 2 | False | True | medium | square | 181.25 |
| B20 | `b739ef02-1fe1-4876-ac97-17f834e6cae9` | 2 | 3 | True | True | small | square | 132.0 |

## Coverage across the 20

- bedrooms: [1, 2, 3, 4, 5, 6]
- wet_rooms: [1, 2, 3]
- safe_room: [False, True]
- open_plan: [False, True]
- size_tier: ['large', 'medium', 'small']
- aspect_tier: ['narrow', 'square', 'wide']

## Regenerate

From `backend/`: `uv run python -m app.ai_harness.topology_poc.briefs` (deterministic — same corpus, same 20 briefs, every time).
