# Rejeu diagnostic grid — validité de campagne (§ I-A)

- artefact : `results/rejeu_grid_20260919/P7_phase1_grid.json` (sha256 `08d981e493402f37a8649a47090293a8f64358b61d8558d4978f13e1ff6436c6`)
- pré-spec : `docs/rejeu_grid_prespec.md` (sha256 `20079aff60a551526bfec0ae399803e83e6dd69c821ab6b20af4d856ba9f3691`)
- base sha : `9897803f48a6537a248f5a41c53a1ea5522d46a0` · HEAD `0120ce856c2b48c6fc0a4cdec2e4df51c1bcfb03`
- verdict : **EXPLOITABLE (exit 0)** — échecs : aucun

| # | Assertion | Résultat | Détail |
|---|---|---|---|
| I-A.1 | artifact parses; no selection or report output beside it | ok | 7 file(s) in the output directory, none matching *selection*.json / *report*.md |
| I-A.2 | 96 entries, 48 per pair, key set rebuilt from the grid | ok | key set rebuilt in-script from expand_grid(GRID_ATR_GRID) x make_key: 96 keys |
| I-A.3 | no entry carries an error key | ok | 96 entries named and counted first; 0 carrying an error key (collect_flags would have skipped them silently) |
| I-A.4 | 22 top-level keys per entry (conditional on I-A.3) | ok | 22 top-level keys expected per entry |
| I-A.5 | frozen campaign perimeter: exchange, fees, costs, versions | ok | spread_pct / slippage_pct asserted only when positions > 0; required null (with timestamp, price, reference_price and trades == 0) when positions == 0 |
| I-A.6 | period equals the four frozen bounds, split recomputed | ok | split recomputed from P7_START + (P7_END - P7_START) * 0.7 = 2025-05-07T04:48:00+00:00 |
| I-A.7 | params and effective_params equal the frozen configuration | ok | Decimals compared through Decimal(str(value)) (effective_params exports them as strings); source never asserted (it reads class_default even under an override); bear_protection_1d_enabled not exported, hence not asserted (section J.4); limitation: effective_params is captured on the LAST segment executed (all) |
| I-A.8 | liquidation / equity_daily / rejections / warmup present and shaped | ok | BTC/USDC: one warmup block shared by its 48 configs; SOL/USDC: one warmup block shared by its 48 configs |
| I-A.9 | equity grids 1097 / 769 / 330, anchored at 1000, all finite | ok | test bounds observed (reported, the pre-spec freezes only the all bounds): 2025-05-07T04:48:00+00:00 -> 2026-04-01T00:00:00+00:00; train bounds observed (reported, the pre-spec freezes only the all bounds): 2023-04-01T00:00:00+00:00 -> 2025-05-07T04:48:00+00:00; points expected: all 1097, train 769, test 330 |
| I-A.10 | 24 metric keys and instrument self-test against the exported curve | ok | 24 metric keys; sharpe / sortino / max_drawdown_pct(index) / defined returns recomputed from equity_daily values converted to Decimal, tolerance 1e-06, None <-> None exact; cagr_pct is NOT exported: it is recomputed and compared to no field; its only admissible cross-check (calmar_ratio x max_drawdown_pct_daily) ran on 288 segment(s) and was SKIPPED on 0 |
| I-A.11 | per-segment accounting identities | ok | all figures coerced by Decimal(str(x)) as b4_flags._dec does; no '~ 0' assertion exists anywhere: unrealized_pnl IS liquidation.pnl |
| I-A.12 | terminal liquidation reconciliation, explicit | ok | 288 liquidation block(s) reconciled explicitly (not delegated), with the b4_flags tolerances applied AFTER presence was proven by I-A.8 |
| I-A.13 | b4_flags mute and flag_segment re-applied over 96 x 3 | ok | collect_flags mute and flag_segment independently re-applied over 288 (entry, segment) pairs — evaluated only now, after I-A.1..I-A.12 |
| I-A.14 | instrument integrity: control diff, worktree, fingerprints | ok | git HEAD 0120ce856c2b48c6fc0a4cdec2e4df51c1bcfb03 against base 9897803f48a6537a248f5a41c53a1ea5522d46a0; tests diff lists 7 path(s), all inside the closed list of 7; python 3.12.3, numpy 2.4.1, host krakenbot, poetry.lock c8313b8b39d2, 6 engine fingerprint(s) |
| I-A.15 | data_coverage.json and benchmark.json produced before the campaign | ok | 'produced before the campaign' is read as generated_at <= the campaign artifact's mtime |
