# Reference artefacts

## Complete Generalized Protection RCA Matrix

- **File:** `Complete_Generalized_Protection_RCA_Matrix_L1_L2_L3_Fallback_LBB.xlsx`
- **Executable pack:** `rules/rca/matrix_v1.yaml` (v1.1.0 — all 54 scenarios)
- **Export JSON:** `rules/rca/_excel_matrix_export.json`
- **Regenerate YAML:** from `backend/`:

```text
python scripts/export_excel_matrix.py
python scripts/generate_full_matrix_yaml.py
```

Sheets used: Complete RCA Matrix, LBB Cascade Logic, Fallback Methodology, RCA Taxonomy.
