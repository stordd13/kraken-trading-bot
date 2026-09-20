# Rejeu diagnostic grid — classes d'indiscernabilité (§ A)

généré 2026-09-20T11:52:14+00:00 · base_sha `9897803f` · prespec `docs/rejeu_grid_prespec.md` sha256 `20079aff60a55152`

DESCRIPTIF — § G.5 : le compte de classes n'entre dans aucune branche de verdict.

> L'égalité de signature est une indiscernabilité sur les sorties exportées. Le journal des transactions n'est pas exporté : ce n'est jamais une preuve d'identité des ordres, ni une preuve que le clamp a saturé.

**Champs inclus** : train (the 24 metric keys) ; test (the 24 metric keys) ; all (the 24 metric keys) ; equity_daily[seg].values (complete, all three segments) ; liquidation[seg] minus timestamp and reference_price ; rejections[seg].by_cause.

**Champs exclus** : params (label of the config, not its output) ; effective_params (label of the config, not its output) ; period (identical by construction) ; warmup (identical per pair, cf. I-A.8).

| paire | configs | classes (sig_exact) | classes (sig_tol) |
|---|---:|---:|---:|
| BTC/USDC | 48 | 48 | 48 |
| SOL/USDC | 48 | 23 | 23 |

## BTC/USDC — classes exactes

| # | signature | n | membres |
|---:|---|---:|---|
| 1 | `0df6105a41b2d8c6` | 1 | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_0901f763` |
| 2 | `dadb4a4491fe9451` | 1 | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_0d72b529` |
| 3 | `4a64840a98a922b7` | 1 | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_0fb41630` |
| 4 | `3b0eca8bec6e3a73` | 1 | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_1d8e270c` |
| 5 | `7c54674140a11674` | 1 | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_21f01bb0` |
| 6 | `3f5b94012507c01e` | 1 | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_29877aa9` |
| 7 | `1d91c2e5d37c9a8b` | 1 | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_2ff9a937` |
| 8 | `0e59dc47541137b4` | 1 | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_329c44ea` |
| 9 | `c8725e47e58a71c1` | 1 | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_3e5bec51` |
| 10 | `c0be26cacbcd4392` | 1 | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_40171b3b` |
| 11 | `d96facca7c38e537` | 1 | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_405106c0` |
| 12 | `88980e6f57863dab` | 1 | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_4426de63` |
| 13 | `13428a79747c5450` | 1 | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_50614027` |
| 14 | `2a204cd033d8ccaa` | 1 | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_523e4cce` |
| 15 | `e4dca291493054bf` | 1 | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_536293bc` |
| 16 | `643e4ad9fcdb7b90` | 1 | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_5958d056` |
| 17 | `46e3f048cfed5774` | 1 | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_5d0ca827` |
| 18 | `ae920bd601471027` | 1 | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_60c43197` |
| 19 | `f3234eca8decdf39` | 1 | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_65dd3337` |
| 20 | `075dc534326deffa` | 1 | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_6c789021` |
| 21 | `ddc9bc05beb9d2de` | 1 | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_73d535d6` |
| 22 | `e1996f37a394b676` | 1 | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_8140f17e` |
| 23 | `f6934c6fb1e36e8d` | 1 | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_81ece5a1` |
| 24 | `a6ebe906831d9e17` | 1 | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_825bb9fa` |
| 25 | `89959bd18294dd05` | 1 | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_94f303d3` |
| 26 | `466bcfbe9ae7fa35` | 1 | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_96dee4d6` |
| 27 | `22da985b3f63d039` | 1 | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_9d3bf21b` |
| 28 | `c86ce5c4ad2ac7c0` | 1 | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_9ff78fb7` |
| 29 | `b8d5a3615301d4d8` | 1 | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_a1120e8e` |
| 30 | `949fc238adc08b43` | 1 | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_a591b9bf` |
| 31 | `7eb2a00c8eb77da8` | 1 | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_a8ea28c2` |
| 32 | `5eab27bd90fad550` | 1 | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_aeeddd0c` |
| 33 | `632a5eca731e0270` | 1 | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_b054321f` |
| 34 | `b5761f175a83fb56` | 1 | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_b0f6090d` |
| 35 | `65421d1ae5745362` | 1 | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_ba527153` |
| 36 | `a4d8818d831cc56f` | 1 | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_ba542585` |
| 37 | `f9c9e8c0369b0c17` | 1 | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_bbc1cdde` |
| 38 | `b3ac0da4135a984b` | 1 | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_c943880f` |
| 39 | `80bb3513bb2f0796` | 1 | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_cc468133` |
| 40 | `782cefecee959974` | 1 | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_d0b8a32d` |
| 41 | `695289d8439d039d` | 1 | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_d2882bfe` |
| 42 | `42b8a7750e315d69` | 1 | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_d8dca2b8` |
| 43 | `3d2cf665ad15a617` | 1 | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_de24a942` |
| 44 | `3bd6aa42469fcf92` | 1 | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_df1cc242` |
| 45 | `60554656e235b528` | 1 | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_e26ac6cb` |
| 46 | `dd71047ab45788d5` | 1 | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_e5086996` |
| 47 | `4dd8cc45649450f6` | 1 | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_eb5fc5f9` |
| 48 | `c2b1e622b41fd906` | 1 | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_f423629b` |

Classes tolérantes : partition identique aux classes exactes.

## BTC/USDC — premières différences entre classes voisines

| a | b | chemin |
|---|---|---|
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_0901f763` | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_0d72b529` | `$.equity_daily.all[255]` |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_0d72b529` | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_0fb41630` | `$.equity_daily.all[19]` |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_0fb41630` | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_1d8e270c` | `$.equity_daily.all[3]` |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_1d8e270c` | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_21f01bb0` | `$.equity_daily.all[3]` |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_21f01bb0` | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_29877aa9` | `$.equity_daily.all[19]` |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_29877aa9` | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_2ff9a937` | `$.equity_daily.all[19]` |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_2ff9a937` | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_329c44ea` | `$.equity_daily.all[66]` |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_329c44ea` | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_3e5bec51` | `$.equity_daily.all[3]` |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_3e5bec51` | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_40171b3b` | `$.equity_daily.all[3]` |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_40171b3b` | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_405106c0` | `$.equity_daily.all[3]` |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_405106c0` | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_4426de63` | `$.equity_daily.all[3]` |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_4426de63` | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_50614027` | `$.equity_daily.all[19]` |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_50614027` | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_523e4cce` | `$.equity_daily.all[19]` |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_523e4cce` | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_536293bc` | `$.equity_daily.all[19]` |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_536293bc` | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_5958d056` | `$.equity_daily.all[19]` |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_5958d056` | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_5d0ca827` | `$.equity_daily.all[19]` |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_5d0ca827` | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_60c43197` | `$.equity_daily.all[19]` |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_60c43197` | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_65dd3337` | `$.equity_daily.all[3]` |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_65dd3337` | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_6c789021` | `$.equity_daily.all[3]` |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_6c789021` | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_73d535d6` | `$.equity_daily.all[3]` |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_73d535d6` | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_8140f17e` | `$.equity_daily.all[3]` |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_8140f17e` | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_81ece5a1` | `$.equity_daily.all[19]` |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_81ece5a1` | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_825bb9fa` | `$.equity_daily.all[3]` |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_825bb9fa` | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_94f303d3` | `$.equity_daily.all[3]` |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_94f303d3` | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_96dee4d6` | `$.equity_daily.all[3]` |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_96dee4d6` | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_9d3bf21b` | `$.equity_daily.all[255]` |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_9d3bf21b` | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_9ff78fb7` | `$.equity_daily.all[19]` |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_9ff78fb7` | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_a1120e8e` | `$.equity_daily.all[19]` |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_a1120e8e` | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_a591b9bf` | `$.equity_daily.all[3]` |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_a591b9bf` | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_a8ea28c2` | `$.equity_daily.all[3]` |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_a8ea28c2` | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_aeeddd0c` | `$.equity_daily.all[3]` |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_aeeddd0c` | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_b054321f` | `$.equity_daily.all[3]` |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_b054321f` | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_b0f6090d` | `$.equity_daily.all[3]` |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_b0f6090d` | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_ba527153` | `$.equity_daily.all[3]` |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_ba527153` | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_ba542585` | `$.equity_daily.all[3]` |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_ba542585` | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_bbc1cdde` | `$.equity_daily.all[19]` |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_bbc1cdde` | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_c943880f` | `$.equity_daily.all[19]` |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_c943880f` | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_cc468133` | `$.equity_daily.all[19]` |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_cc468133` | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_d0b8a32d` | `$.equity_daily.all[19]` |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_d0b8a32d` | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_d2882bfe` | `$.equity_daily.all[3]` |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_d2882bfe` | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_d8dca2b8` | `$.equity_daily.all[3]` |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_d8dca2b8` | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_de24a942` | `$.equity_daily.all[255]` |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_de24a942` | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_df1cc242` | `$.equity_daily.all[19]` |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_df1cc242` | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_e26ac6cb` | `$.equity_daily.all[19]` |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_e26ac6cb` | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_e5086996` | `$.equity_daily.all[255]` |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_e5086996` | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_eb5fc5f9` | `$.equity_daily.all[19]` |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_eb5fc5f9` | `grok_grid_atr_adaptive_v4_BTC_USDC_p1_f423629b` | `$.equity_daily.all[19]` |

## SOL/USDC — classes exactes

| # | signature | n | membres |
|---:|---|---:|---|
| 1 | `88f01185847d6667` | 4 | `grok_grid_atr_adaptive_v4_SOL_USDC_p1_0901f763`, `grok_grid_atr_adaptive_v4_SOL_USDC_p1_0d72b529`, `grok_grid_atr_adaptive_v4_SOL_USDC_p1_cc468133`, `grok_grid_atr_adaptive_v4_SOL_USDC_p1_e26ac6cb` |
| 2 | `114273989bde4a93` | 1 | `grok_grid_atr_adaptive_v4_SOL_USDC_p1_0fb41630` |
| 3 | `56516be43de105ec` | 3 | `grok_grid_atr_adaptive_v4_SOL_USDC_p1_1d8e270c`, `grok_grid_atr_adaptive_v4_SOL_USDC_p1_3e5bec51`, `grok_grid_atr_adaptive_v4_SOL_USDC_p1_94f303d3` |
| 4 | `828f910195385bfb` | 4 | `grok_grid_atr_adaptive_v4_SOL_USDC_p1_21f01bb0`, `grok_grid_atr_adaptive_v4_SOL_USDC_p1_2ff9a937`, `grok_grid_atr_adaptive_v4_SOL_USDC_p1_50614027`, `grok_grid_atr_adaptive_v4_SOL_USDC_p1_6c789021` |
| 5 | `81475975e9a6efa3` | 1 | `grok_grid_atr_adaptive_v4_SOL_USDC_p1_29877aa9` |
| 6 | `b0b437c30f5b4d91` | 4 | `grok_grid_atr_adaptive_v4_SOL_USDC_p1_329c44ea`, `grok_grid_atr_adaptive_v4_SOL_USDC_p1_9ff78fb7`, `grok_grid_atr_adaptive_v4_SOL_USDC_p1_b0f6090d`, `grok_grid_atr_adaptive_v4_SOL_USDC_p1_bbc1cdde` |
| 7 | `9d4209c63868590c` | 4 | `grok_grid_atr_adaptive_v4_SOL_USDC_p1_40171b3b`, `grok_grid_atr_adaptive_v4_SOL_USDC_p1_8140f17e`, `grok_grid_atr_adaptive_v4_SOL_USDC_p1_d0b8a32d`, `grok_grid_atr_adaptive_v4_SOL_USDC_p1_eb5fc5f9` |
| 8 | `da04e7cc8028f3d9` | 3 | `grok_grid_atr_adaptive_v4_SOL_USDC_p1_405106c0`, `grok_grid_atr_adaptive_v4_SOL_USDC_p1_b054321f`, `grok_grid_atr_adaptive_v4_SOL_USDC_p1_ba527153` |
| 9 | `2dd18a0436e7704d` | 4 | `grok_grid_atr_adaptive_v4_SOL_USDC_p1_4426de63`, `grok_grid_atr_adaptive_v4_SOL_USDC_p1_96dee4d6`, `grok_grid_atr_adaptive_v4_SOL_USDC_p1_de24a942`, `grok_grid_atr_adaptive_v4_SOL_USDC_p1_f423629b` |
| 10 | `a50e48dcb5794b73` | 4 | `grok_grid_atr_adaptive_v4_SOL_USDC_p1_523e4cce`, `grok_grid_atr_adaptive_v4_SOL_USDC_p1_5958d056`, `grok_grid_atr_adaptive_v4_SOL_USDC_p1_a1120e8e`, `grok_grid_atr_adaptive_v4_SOL_USDC_p1_c943880f` |
| 11 | `2099a14ca13c3e9f` | 2 | `grok_grid_atr_adaptive_v4_SOL_USDC_p1_536293bc`, `grok_grid_atr_adaptive_v4_SOL_USDC_p1_81ece5a1` |
| 12 | `18b3837fb86915cd` | 3 | `grok_grid_atr_adaptive_v4_SOL_USDC_p1_5d0ca827`, `grok_grid_atr_adaptive_v4_SOL_USDC_p1_d8dca2b8`, `grok_grid_atr_adaptive_v4_SOL_USDC_p1_e5086996` |
| 13 | `8317a77590dd9bf0` | 1 | `grok_grid_atr_adaptive_v4_SOL_USDC_p1_60c43197` |
| 14 | `41b884d78ce1132a` | 1 | `grok_grid_atr_adaptive_v4_SOL_USDC_p1_65dd3337` |
| 15 | `1fea73bf81e368c8` | 1 | `grok_grid_atr_adaptive_v4_SOL_USDC_p1_73d535d6` |
| 16 | `6f7c048098141872` | 1 | `grok_grid_atr_adaptive_v4_SOL_USDC_p1_825bb9fa` |
| 17 | `3fc7990b303f017e` | 1 | `grok_grid_atr_adaptive_v4_SOL_USDC_p1_9d3bf21b` |
| 18 | `bcac60d54be96ffd` | 1 | `grok_grid_atr_adaptive_v4_SOL_USDC_p1_a591b9bf` |
| 19 | `fbed876de2120018` | 1 | `grok_grid_atr_adaptive_v4_SOL_USDC_p1_a8ea28c2` |
| 20 | `b3338d1cb9285ef0` | 1 | `grok_grid_atr_adaptive_v4_SOL_USDC_p1_aeeddd0c` |
| 21 | `bf5056c091451a95` | 1 | `grok_grid_atr_adaptive_v4_SOL_USDC_p1_ba542585` |
| 22 | `f8be97c41f7db3a1` | 1 | `grok_grid_atr_adaptive_v4_SOL_USDC_p1_d2882bfe` |
| 23 | `634c32697ee5d1e1` | 1 | `grok_grid_atr_adaptive_v4_SOL_USDC_p1_df1cc242` |

Classes tolérantes : partition identique aux classes exactes.

## SOL/USDC — premières différences entre classes voisines

| a | b | chemin |
|---|---|---|
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_0901f763` | `grok_grid_atr_adaptive_v4_SOL_USDC_p1_0fb41630` | `$.equity_daily.all[277]` |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_0fb41630` | `grok_grid_atr_adaptive_v4_SOL_USDC_p1_1d8e270c` | `$.equity_daily.all[293]` |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_1d8e270c` | `grok_grid_atr_adaptive_v4_SOL_USDC_p1_21f01bb0` | `$.equity_daily.all[319]` |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_21f01bb0` | `grok_grid_atr_adaptive_v4_SOL_USDC_p1_29877aa9` | `$.equity_daily.all[277]` |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_29877aa9` | `grok_grid_atr_adaptive_v4_SOL_USDC_p1_329c44ea` | `$.equity_daily.all[277]` |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_329c44ea` | `grok_grid_atr_adaptive_v4_SOL_USDC_p1_40171b3b` | `$.equity_daily.all[434]` |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_40171b3b` | `grok_grid_atr_adaptive_v4_SOL_USDC_p1_405106c0` | `$.equity_daily.all[319]` |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_405106c0` | `grok_grid_atr_adaptive_v4_SOL_USDC_p1_4426de63` | `$.equity_daily.all[277]` |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_4426de63` | `grok_grid_atr_adaptive_v4_SOL_USDC_p1_523e4cce` | `$.equity_daily.all[277]` |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_523e4cce` | `grok_grid_atr_adaptive_v4_SOL_USDC_p1_536293bc` | `$.equity_daily.all[277]` |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_536293bc` | `grok_grid_atr_adaptive_v4_SOL_USDC_p1_5d0ca827` | `$.equity_daily.all[367]` |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_5d0ca827` | `grok_grid_atr_adaptive_v4_SOL_USDC_p1_60c43197` | `$.equity_daily.all[277]` |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_60c43197` | `grok_grid_atr_adaptive_v4_SOL_USDC_p1_65dd3337` | `$.equity_daily.all[293]` |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_65dd3337` | `grok_grid_atr_adaptive_v4_SOL_USDC_p1_73d535d6` | `$.equity_daily.all[1024]` |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_73d535d6` | `grok_grid_atr_adaptive_v4_SOL_USDC_p1_825bb9fa` | `$.equity_daily.all[396]` |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_825bb9fa` | `grok_grid_atr_adaptive_v4_SOL_USDC_p1_9d3bf21b` | `$.equity_daily.all[277]` |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_9d3bf21b` | `grok_grid_atr_adaptive_v4_SOL_USDC_p1_a591b9bf` | `$.equity_daily.all[277]` |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_a591b9bf` | `grok_grid_atr_adaptive_v4_SOL_USDC_p1_a8ea28c2` | `$.equity_daily.all[277]` |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_a8ea28c2` | `grok_grid_atr_adaptive_v4_SOL_USDC_p1_aeeddd0c` | `$.equity_daily.all[277]` |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_aeeddd0c` | `grok_grid_atr_adaptive_v4_SOL_USDC_p1_ba542585` | `$.equity_daily.all[429]` |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_ba542585` | `grok_grid_atr_adaptive_v4_SOL_USDC_p1_d2882bfe` | `$.equity_daily.all[396]` |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_d2882bfe` | `grok_grid_atr_adaptive_v4_SOL_USDC_p1_df1cc242` | `$.equity_daily.all[293]` |

## Lecture rétroactive B4

Source : `results/B4_P7_phase1_cross_validate.json` — champs conservés par ce fichier uniquement (`strategy`, `pair`, `params`, `liquidation`, `train`, `test`, `all`).

| paire | configs | classes (sig_exact) | référence | accord |
|---|---:|---:|---:|---|
| BTC/USDC | 48 | 45 | 45 | oui |
| SOL/USDC | 48 | 48 | 48 | oui |
