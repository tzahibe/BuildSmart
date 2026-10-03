# B06 / B09 (and other all-infeasible families): per-witness infeasibility certificates

## B06 — 156 witnesses, family complete = True, oracle: 156 INFEASIBLE / 0 UNKNOWN, by method {'branch_and_bound': 32, 'certificate': 124}

- certificate kinds: {'B&B: INFEASIBLE': 32, 'WIDTH': 124}
- most frequent WIDTH contradictions (band needing the width, band capping it): 
  - 12x: needs [('MASTER', 3.3), ('BEDROOM_1', 2.9), ('BATHROOM_2', 1.9)] vs cap [('BATHROOM_1', 6.33)]
  - 12x: needs [('BATHROOM_2', 1.9), ('BEDROOM_1', 2.9), ('MASTER', 3.3)] vs cap [('BATHROOM_1', 6.33)]
  - 4x: needs [('KITCHEN', 2.7), ('LIVING', 3.3), ('BATHROOM_2', 1.9), ('BEDROOM_1', 2.9), ('MASTER', 3.3)] vs cap [('BATHROOM_1', 6.33)]
  - 4x: needs [('MASTER', 3.3), ('BEDROOM_1', 2.9), ('BATHROOM_2', 1.9), ('LIVING', 3.3), ('KITCHEN', 2.7)] vs cap [('BATHROOM_1', 6.33)]
  - 4x: needs [('BEDROOM_1', 2.9), ('BATHROOM_2', 1.9), ('LIVING', 3.3), ('KITCHEN', 2.7), ('MASTER', 3.3)] vs cap [('BATHROOM_1', 6.33)]
  - 4x: needs [('MASTER', 3.3), ('KITCHEN', 2.7), ('LIVING', 3.3), ('BATHROOM_2', 1.9), ('BEDROOM_1', 2.9)] vs cap [('BATHROOM_1', 6.33)]
- example: WIDTH: band 2 needs width >= 8.10 m (sum of its cells' minimum dimensions [('MASTER', 3.3), ('BEDROOM_1', 2.9), ('BATHROOM_2', 1.9)]) but band 3 allows at most 6.33 m (each cell's max area / its minimum depth: [('BATHROOM_1', 6.33)])

## B07 — 4752 witnesses, family complete = True, oracle: 4752 INFEASIBLE / 0 UNKNOWN, by method {'certificate': 4368, 'branch_and_bound': 384}

- certificate kinds: {'WIDTH': 4368, 'B&B: INFEASIBLE': 384}
- most frequent WIDTH contradictions (band needing the width, band capping it): 
  - 208x: needs [('MASTER', 3.3), ('BEDROOM_1', 2.9), ('BEDROOM_2', 2.9), ('BATHROOM_2', 1.9)] vs cap [('BATHROOM_1', 6.33)]
  - 208x: needs [('BEDROOM_2', 2.9), ('BATHROOM_2', 1.9), ('BEDROOM_1', 2.9), ('MASTER', 3.3)] vs cap [('BATHROOM_1', 6.33)]
  - 208x: needs [('BATHROOM_2', 1.9), ('BEDROOM_2', 2.9), ('BEDROOM_1', 2.9), ('MASTER', 3.3)] vs cap [('BATHROOM_1', 6.33)]
  - 208x: needs [('BEDROOM_1', 2.9), ('BATHROOM_2', 1.9), ('BEDROOM_2', 2.9), ('MASTER', 3.3)] vs cap [('BATHROOM_1', 6.33)]
  - 208x: needs [('MASTER', 3.3), ('BEDROOM_2', 2.9), ('BATHROOM_2', 1.9), ('BEDROOM_1', 2.9)] vs cap [('BATHROOM_1', 6.33)]
  - 208x: needs [('MASTER', 3.3), ('BEDROOM_1', 2.9), ('BATHROOM_2', 1.9), ('BEDROOM_2', 2.9)] vs cap [('BATHROOM_1', 6.33)]
- example: WIDTH: band 2 needs width >= 11.00 m (sum of its cells' minimum dimensions [('MASTER', 3.3), ('BEDROOM_1', 2.9), ('BEDROOM_2', 2.9), ('BATHROOM_2', 1.9)]) but band 3 allows at most 6.33 m (each cell's max area / its minimum depth: [('BATHROOM_1', 6.33)])

