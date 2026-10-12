# Real data

Only real, attributable readings go here. Never put simulated values in this folder.

- `readings.csv`: per-lake storage in ML. Rows with `source=bmc` are figures from BMC's
  Hydraulic Engineer's Department 6 am report (Bhandup Master Control Centre).
- `reference_totals.csv`: city-wide percent full for past dates, where per-lake values
  are not available yet (used for the "same day in earlier years" line).

Provenance of the current rows: read on 12 Oct 2026 from https://www.mumbailakewaterlevel.in,
which republishes the BMC report (as of 06:00, 8 Oct 2026; the same page quoted 99.03% for
the same date in 2025 and 98.62% in 2024). Sum of the seven lakes = 13,64,045 ML of 14,47,363 ML.
Replace with BMC's own report once a direct source is confirmed.
