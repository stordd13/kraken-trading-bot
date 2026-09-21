# C3 — validité d'entrée (§ I-A)

généré 2026-09-22T00:00:00+00:00 · protocole 9b62915069e59e9b · observations `results/rejeu_grid_20260919/P7_phase1_grid.json` sha256 `08d981e493402f37`

Préfixe `train`, ancrage `2025-05-07T04:48:00+00:00`, 96 candidats, provenance `contaminated`.

| assertion | statut | détail |
|---|---|---|
| I-A.1 forme des observations | ok | 96 entrées, préfixe 'train' |
| I-A.2 D5 — contrats d'instrument égaux au manifeste | **non assertable** | non assertable : D5 — intervalle d'exécution — aucun porteur `exec_interval` dans 96 entrée(s) : le runner n'exporte pas l'intervalle d'exécution (§ A.7, aucun champ de la liste blanche ne le porte) |
| I-A.3 bornes du préfixe exactement [début, T] | ok | ok |
| I-A.4 unicité des identités et univers fermé | ok | 96 identités, égales à l'univers |
| I-A.5 provenance de l'univers | ok | provenance 'contaminated' (liste close § A.5) |
| I-A.6 amorçage du préfixe : séries de décision, sufficient recalculé | ok | ok |
| I-A.7 artefact de couverture | **non assertable** | non assertable : couverture (D1, § A.7) — artefact de couverture non fourni — aucun producteur committé ne peut le fabriquer en C3a |
| I-A.8 D2 — promotion en refus d'artefact sur la totalité | **ÉCHEC** | D2 échoue sur la totalité des 96 candidats de l'artefact : refus d'artefact D_WARMUP_PREFIX, aucun classement n'est produit (§ I.1 l.5, § D.3) |

**Entrée refusée** — `D_WARMUP_PREFIX` (portée artefact, I-A.8) : D2 échoue sur la totalité des 96 candidats de l'artefact : refus d'artefact D_WARMUP_PREFIX, aucun classement n'est produit (§ I.1 l.5, § D.3)

> cet artefact ne satisfait pas les conditions d'entrée C3

Diagnostics de candidats (D2) : 96

- `grok_grid_atr_adaptive_v4_BTC_USDC_p1_aeeddd0c` : séries insuffisantes 1d, 1w
- `grok_grid_atr_adaptive_v4_BTC_USDC_p1_81ece5a1` : séries insuffisantes 1d, 1w
- `grok_grid_atr_adaptive_v4_BTC_USDC_p1_73d535d6` : séries insuffisantes 1d, 1w
- `grok_grid_atr_adaptive_v4_BTC_USDC_p1_ba527153` : séries insuffisantes 1d, 1w
- `grok_grid_atr_adaptive_v4_BTC_USDC_p1_5d0ca827` : séries insuffisantes 1d, 1w
- `grok_grid_atr_adaptive_v4_BTC_USDC_p1_1d8e270c` : séries insuffisantes 1d, 1w
- `grok_grid_atr_adaptive_v4_BTC_USDC_p1_a1120e8e` : séries insuffisantes 1d, 1w
- `grok_grid_atr_adaptive_v4_BTC_USDC_p1_0d72b529` : séries insuffisantes 1d, 1w
- `grok_grid_atr_adaptive_v4_BTC_USDC_p1_eb5fc5f9` : séries insuffisantes 1d, 1w
- `grok_grid_atr_adaptive_v4_BTC_USDC_p1_21f01bb0` : séries insuffisantes 1d, 1w
- `grok_grid_atr_adaptive_v4_BTC_USDC_p1_f423629b` : séries insuffisantes 1d, 1w
- `grok_grid_atr_adaptive_v4_BTC_USDC_p1_b0f6090d` : séries insuffisantes 1d, 1w
- `grok_grid_atr_adaptive_v4_BTC_USDC_p1_825bb9fa` : séries insuffisantes 1d, 1w
- `grok_grid_atr_adaptive_v4_BTC_USDC_p1_536293bc` : séries insuffisantes 1d, 1w
- `grok_grid_atr_adaptive_v4_BTC_USDC_p1_65dd3337` : séries insuffisantes 1d, 1w
- `grok_grid_atr_adaptive_v4_BTC_USDC_p1_405106c0` : séries insuffisantes 1d, 1w
- `grok_grid_atr_adaptive_v4_BTC_USDC_p1_d8dca2b8` : séries insuffisantes 1d, 1w
- `grok_grid_atr_adaptive_v4_BTC_USDC_p1_3e5bec51` : séries insuffisantes 1d, 1w
- `grok_grid_atr_adaptive_v4_BTC_USDC_p1_523e4cce` : séries insuffisantes 1d, 1w
- `grok_grid_atr_adaptive_v4_BTC_USDC_p1_e26ac6cb` : séries insuffisantes 1d, 1w
- `grok_grid_atr_adaptive_v4_BTC_USDC_p1_d0b8a32d` : séries insuffisantes 1d, 1w
- `grok_grid_atr_adaptive_v4_BTC_USDC_p1_2ff9a937` : séries insuffisantes 1d, 1w
- `grok_grid_atr_adaptive_v4_BTC_USDC_p1_96dee4d6` : séries insuffisantes 1d, 1w
- `grok_grid_atr_adaptive_v4_BTC_USDC_p1_9ff78fb7` : séries insuffisantes 1d, 1w
- `grok_grid_atr_adaptive_v4_BTC_USDC_p1_a591b9bf` : séries insuffisantes 1d, 1w
- `grok_grid_atr_adaptive_v4_BTC_USDC_p1_a8ea28c2` : séries insuffisantes 1d, 1w
- `grok_grid_atr_adaptive_v4_BTC_USDC_p1_d2882bfe` : séries insuffisantes 1d, 1w
- `grok_grid_atr_adaptive_v4_BTC_USDC_p1_b054321f` : séries insuffisantes 1d, 1w
- `grok_grid_atr_adaptive_v4_BTC_USDC_p1_e5086996` : séries insuffisantes 1d, 1w
- `grok_grid_atr_adaptive_v4_BTC_USDC_p1_94f303d3` : séries insuffisantes 1d, 1w
- `grok_grid_atr_adaptive_v4_BTC_USDC_p1_c943880f` : séries insuffisantes 1d, 1w
- `grok_grid_atr_adaptive_v4_BTC_USDC_p1_cc468133` : séries insuffisantes 1d, 1w
- `grok_grid_atr_adaptive_v4_BTC_USDC_p1_8140f17e` : séries insuffisantes 1d, 1w
- `grok_grid_atr_adaptive_v4_BTC_USDC_p1_6c789021` : séries insuffisantes 1d, 1w
- `grok_grid_atr_adaptive_v4_BTC_USDC_p1_4426de63` : séries insuffisantes 1d, 1w
- `grok_grid_atr_adaptive_v4_BTC_USDC_p1_bbc1cdde` : séries insuffisantes 1d, 1w
- `grok_grid_atr_adaptive_v4_BTC_USDC_p1_ba542585` : séries insuffisantes 1d, 1w
- `grok_grid_atr_adaptive_v4_BTC_USDC_p1_9d3bf21b` : séries insuffisantes 1d, 1w
- `grok_grid_atr_adaptive_v4_BTC_USDC_p1_0fb41630` : séries insuffisantes 1d, 1w
- `grok_grid_atr_adaptive_v4_BTC_USDC_p1_df1cc242` : séries insuffisantes 1d, 1w
- `grok_grid_atr_adaptive_v4_BTC_USDC_p1_29877aa9` : séries insuffisantes 1d, 1w
- `grok_grid_atr_adaptive_v4_BTC_USDC_p1_60c43197` : séries insuffisantes 1d, 1w
- `grok_grid_atr_adaptive_v4_BTC_USDC_p1_5958d056` : séries insuffisantes 1d, 1w
- `grok_grid_atr_adaptive_v4_BTC_USDC_p1_0901f763` : séries insuffisantes 1d, 1w
- `grok_grid_atr_adaptive_v4_BTC_USDC_p1_40171b3b` : séries insuffisantes 1d, 1w
- `grok_grid_atr_adaptive_v4_BTC_USDC_p1_50614027` : séries insuffisantes 1d, 1w
- `grok_grid_atr_adaptive_v4_BTC_USDC_p1_de24a942` : séries insuffisantes 1d, 1w
- `grok_grid_atr_adaptive_v4_BTC_USDC_p1_329c44ea` : séries insuffisantes 1d, 1w
- `grok_grid_atr_adaptive_v4_SOL_USDC_p1_aeeddd0c` : séries insuffisantes 4h, 1d, 1w
- `grok_grid_atr_adaptive_v4_SOL_USDC_p1_81ece5a1` : séries insuffisantes 4h, 1d, 1w
- `grok_grid_atr_adaptive_v4_SOL_USDC_p1_73d535d6` : séries insuffisantes 4h, 1d, 1w
- `grok_grid_atr_adaptive_v4_SOL_USDC_p1_ba527153` : séries insuffisantes 4h, 1d, 1w
- `grok_grid_atr_adaptive_v4_SOL_USDC_p1_5d0ca827` : séries insuffisantes 4h, 1d, 1w
- `grok_grid_atr_adaptive_v4_SOL_USDC_p1_1d8e270c` : séries insuffisantes 4h, 1d, 1w
- `grok_grid_atr_adaptive_v4_SOL_USDC_p1_a1120e8e` : séries insuffisantes 4h, 1d, 1w
- `grok_grid_atr_adaptive_v4_SOL_USDC_p1_0d72b529` : séries insuffisantes 4h, 1d, 1w
- `grok_grid_atr_adaptive_v4_SOL_USDC_p1_eb5fc5f9` : séries insuffisantes 4h, 1d, 1w
- `grok_grid_atr_adaptive_v4_SOL_USDC_p1_21f01bb0` : séries insuffisantes 4h, 1d, 1w
- `grok_grid_atr_adaptive_v4_SOL_USDC_p1_f423629b` : séries insuffisantes 4h, 1d, 1w
- `grok_grid_atr_adaptive_v4_SOL_USDC_p1_b0f6090d` : séries insuffisantes 4h, 1d, 1w
- `grok_grid_atr_adaptive_v4_SOL_USDC_p1_825bb9fa` : séries insuffisantes 4h, 1d, 1w
- `grok_grid_atr_adaptive_v4_SOL_USDC_p1_536293bc` : séries insuffisantes 4h, 1d, 1w
- `grok_grid_atr_adaptive_v4_SOL_USDC_p1_65dd3337` : séries insuffisantes 4h, 1d, 1w
- `grok_grid_atr_adaptive_v4_SOL_USDC_p1_405106c0` : séries insuffisantes 4h, 1d, 1w
- `grok_grid_atr_adaptive_v4_SOL_USDC_p1_d8dca2b8` : séries insuffisantes 4h, 1d, 1w
- `grok_grid_atr_adaptive_v4_SOL_USDC_p1_3e5bec51` : séries insuffisantes 4h, 1d, 1w
- `grok_grid_atr_adaptive_v4_SOL_USDC_p1_523e4cce` : séries insuffisantes 4h, 1d, 1w
- `grok_grid_atr_adaptive_v4_SOL_USDC_p1_e26ac6cb` : séries insuffisantes 4h, 1d, 1w
- `grok_grid_atr_adaptive_v4_SOL_USDC_p1_d0b8a32d` : séries insuffisantes 4h, 1d, 1w
- `grok_grid_atr_adaptive_v4_SOL_USDC_p1_2ff9a937` : séries insuffisantes 4h, 1d, 1w
- `grok_grid_atr_adaptive_v4_SOL_USDC_p1_96dee4d6` : séries insuffisantes 4h, 1d, 1w
- `grok_grid_atr_adaptive_v4_SOL_USDC_p1_9ff78fb7` : séries insuffisantes 4h, 1d, 1w
- `grok_grid_atr_adaptive_v4_SOL_USDC_p1_a591b9bf` : séries insuffisantes 4h, 1d, 1w
- `grok_grid_atr_adaptive_v4_SOL_USDC_p1_a8ea28c2` : séries insuffisantes 4h, 1d, 1w
- `grok_grid_atr_adaptive_v4_SOL_USDC_p1_d2882bfe` : séries insuffisantes 4h, 1d, 1w
- `grok_grid_atr_adaptive_v4_SOL_USDC_p1_b054321f` : séries insuffisantes 4h, 1d, 1w
- `grok_grid_atr_adaptive_v4_SOL_USDC_p1_e5086996` : séries insuffisantes 4h, 1d, 1w
- `grok_grid_atr_adaptive_v4_SOL_USDC_p1_94f303d3` : séries insuffisantes 4h, 1d, 1w
- `grok_grid_atr_adaptive_v4_SOL_USDC_p1_c943880f` : séries insuffisantes 4h, 1d, 1w
- `grok_grid_atr_adaptive_v4_SOL_USDC_p1_cc468133` : séries insuffisantes 4h, 1d, 1w
- `grok_grid_atr_adaptive_v4_SOL_USDC_p1_8140f17e` : séries insuffisantes 4h, 1d, 1w
- `grok_grid_atr_adaptive_v4_SOL_USDC_p1_6c789021` : séries insuffisantes 4h, 1d, 1w
- `grok_grid_atr_adaptive_v4_SOL_USDC_p1_4426de63` : séries insuffisantes 4h, 1d, 1w
- `grok_grid_atr_adaptive_v4_SOL_USDC_p1_bbc1cdde` : séries insuffisantes 4h, 1d, 1w
- `grok_grid_atr_adaptive_v4_SOL_USDC_p1_ba542585` : séries insuffisantes 4h, 1d, 1w
- `grok_grid_atr_adaptive_v4_SOL_USDC_p1_9d3bf21b` : séries insuffisantes 4h, 1d, 1w
- `grok_grid_atr_adaptive_v4_SOL_USDC_p1_0fb41630` : séries insuffisantes 4h, 1d, 1w
- `grok_grid_atr_adaptive_v4_SOL_USDC_p1_df1cc242` : séries insuffisantes 4h, 1d, 1w
- `grok_grid_atr_adaptive_v4_SOL_USDC_p1_29877aa9` : séries insuffisantes 4h, 1d, 1w
- `grok_grid_atr_adaptive_v4_SOL_USDC_p1_60c43197` : séries insuffisantes 4h, 1d, 1w
- `grok_grid_atr_adaptive_v4_SOL_USDC_p1_5958d056` : séries insuffisantes 4h, 1d, 1w
- `grok_grid_atr_adaptive_v4_SOL_USDC_p1_0901f763` : séries insuffisantes 4h, 1d, 1w
- `grok_grid_atr_adaptive_v4_SOL_USDC_p1_40171b3b` : séries insuffisantes 4h, 1d, 1w
- `grok_grid_atr_adaptive_v4_SOL_USDC_p1_50614027` : séries insuffisantes 4h, 1d, 1w
- `grok_grid_atr_adaptive_v4_SOL_USDC_p1_de24a942` : séries insuffisantes 4h, 1d, 1w
- `grok_grid_atr_adaptive_v4_SOL_USDC_p1_329c44ea` : séries insuffisantes 4h, 1d, 1w

Portée du run : ce run établit le refus D2 seul ; le manifeste est dérivé des clés de l'artefact qu'il encadre, donc ses assertions D5 ne prouvent rien d'indépendant ; provenance `contaminated` = qualification du rapport gelé results/rejeu_grid_report.md § 10.3 ; aucun classement, aucun verdict économique sur la famille grid (§ D.3)
