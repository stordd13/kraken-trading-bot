# Rejeu diagnostic grid — effet (§ C, § E.3, § F)

Généré le 2026-09-20T11:52:14+00:00 · base_sha `9897803f48a6`

`B` = 10000 · `L` = [10, 21, 42] · λ = reestimated · numpy 2.4.1

> L'appariement sur le drawdown (ou la volatilité) observé est une comparaison rétrospective, jamais une allocation validée pour l'avenir.

## BTC/USDC

admissible **True** · warmup **W1** · benchmark comparable **True** · |J_calc| 48 · |J_eligible| 48

> Le warmup 1d/1w de BTC/USDC est `sufficient=False` par `largest_gap_candles` 163 / 23 : les EMA20/50 qui alimentent `get_regime` ont été amorcées à travers le trou pré-fenêtre. `bias_1d` faisant vivre `regime_1d` dans tous les modes, **tout** résultat de cette paire — quel que soit `bear_protection_mode` — repose sur une porte dont l'amorçage n'est pas propre ; le réexaminer est une entrée obligatoire de C3.

> Le comparateur apparié détient moins de 2 % du capital dans l'actif ; la comparaison porte sur l'efficience à très petit budget de risque, pas sur une allocation alternative réaliste. Ce qui empêche un effet absolu trivialement petit de fonder un verdict est le plancher G2, pas cette comparaison.

`max se / min se` sur J_calc (L = 21, dd) : 5.35

| config | cycles | nnz | statut | gate | net_pnl | return % | net/fees | MDD | λ_dd | λ_σ | Δ_dd | Δ_σ | LB(21,dd) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_aeeddd0c` | 483 | 977 | ELIGIBLE | G4 | 74.1714 | 7.4171 | 2.8598 | 13.5442 | 0.0800 | 0.0720 | -1.1446 | -0.8000 | -7.3081 |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_81ece5a1` | 379 | 761 | ELIGIBLE | G2 | 37.3228 | 3.7323 | 1.7955 | 13.9000 | 0.0820 | 0.0730 | -2.4141 | -2.0268 | -8.5775 |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_73d535d6` | 417 | 977 | ELIGIBLE | G2 | 58.4768 | 5.8477 | 2.6237 | 13.1142 | 0.0760 | 0.0620 | -1.4733 | -0.8666 | -7.6368 |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_ba527153` | 242 | 912 | ELIGIBLE | G2 | 56.2659 | 5.6266 | 4.2451 | 8.7950 | 0.0470 | 0.0430 | -0.2794 | -0.1025 | -6.4429 |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_5d0ca827` | 194 | 727 | ELIGIBLE | G2 | 41.5259 | 4.1526 | 3.8000 | 9.2468 | 0.0500 | 0.0460 | -0.8873 | -0.7108 | -7.0507 |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_1d8e270c` | 246 | 912 | ELIGIBLE | G2 | 59.6307 | 5.9631 | 4.4335 | 9.5035 | 0.0520 | 0.0460 | -0.3918 | -0.1273 | -6.5553 |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_a1120e8e` | 143 | 845 | ELIGIBLE | — | 68.4412 | 6.8441 | 8.8025 | 3.7944 | 0.0190 | 0.0230 | 1.3617 | 1.1810 | -4.8018 |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_0d72b529` | 114 | 664 | ELIGIBLE | G2 | 56.3232 | 5.6323 | 8.9211 | 3.9956 | 0.0200 | 0.0240 | 0.9289 | 0.7483 | -5.2346 |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_eb5fc5f9` | 146 | 845 | ELIGIBLE | G2 | 45.0310 | 4.5031 | 5.4883 | 7.4286 | 0.0390 | 0.0350 | -0.2870 | -0.1088 | -6.4505 |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_21f01bb0` | 94 | 771 | ELIGIBLE | G2 | 55.5716 | 5.5572 | 10.7864 | 3.0828 | 0.0150 | 0.0190 | 1.1314 | 0.9500 | -5.0321 |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_f423629b` | 80 | 599 | ELIGIBLE | G2 | 49.3822 | 4.9382 | 10.8950 | 3.2559 | 0.0160 | 0.0200 | 0.8867 | 0.7055 | -5.2767 |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_b0f6090d` | 96 | 771 | ELIGIBLE | G2 | 28.1075 | 2.8107 | 5.0061 | 6.4665 | 0.0340 | 0.0310 | -0.6144 | -0.4803 | -6.7779 |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_825bb9fa` | 375 | 950 | ELIGIBLE | — | 86.5778 | 8.6578 | 4.2934 | 10.2071 | 0.0560 | 0.0570 | 0.2888 | 0.2450 | -5.8747 |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_536293bc` | 306 | 743 | ELIGIBLE | G2 | 57.7282 | 5.7728 | 3.4413 | 10.3944 | 0.0580 | 0.0570 | -0.7160 | -0.6722 | -6.8794 |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_65dd3337` | 326 | 950 | ELIGIBLE | G4 | 61.4061 | 6.1406 | 3.5061 | 10.8190 | 0.0600 | 0.0520 | -0.6855 | -0.3350 | -6.8490 |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_405106c0` | 221 | 911 | ELIGIBLE | — | 64.9642 | 6.4964 | 5.3879 | 7.3716 | 0.0390 | 0.0380 | 0.3536 | 0.3981 | -5.8099 |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_d8dca2b8` | 185 | 727 | ELIGIBLE | G2 | 52.9767 | 5.2977 | 5.1264 | 7.7739 | 0.0410 | 0.0410 | -0.1195 | -0.1195 | -6.2830 |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_3e5bec51` | 225 | 911 | ELIGIBLE | — | 66.5977 | 6.6598 | 5.4359 | 8.1268 | 0.0430 | 0.0420 | 0.2282 | 0.2725 | -5.9353 |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_523e4cce` | 138 | 844 | ELIGIBLE | — | 67.0792 | 6.7079 | 8.9157 | 3.7992 | 0.0190 | 0.0230 | 1.3183 | 1.1376 | -4.8452 |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_e26ac6cb` | 113 | 664 | ELIGIBLE | G2 | 56.1673 | 5.6167 | 8.9677 | 3.9961 | 0.0200 | 0.0240 | 0.9239 | 0.7433 | -5.2396 |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_d0b8a32d` | 143 | 844 | ELIGIBLE | G2 | 44.2824 | 4.4282 | 5.4982 | 7.4336 | 0.0390 | 0.0350 | -0.3112 | -0.1330 | -6.4747 |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_2ff9a937` | 92 | 771 | ELIGIBLE | G2 | 55.0097 | 5.5010 | 10.8900 | 3.0845 | 0.0150 | 0.0190 | 1.1133 | 0.9319 | -5.0502 |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_96dee4d6` | 80 | 599 | ELIGIBLE | G2 | 49.5031 | 4.9503 | 10.9214 | 3.2556 | 0.0160 | 0.0200 | 0.8906 | 0.7094 | -5.2728 |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_9ff78fb7` | 95 | 771 | ELIGIBLE | G2 | 27.8766 | 2.7877 | 5.0098 | 6.4678 | 0.0340 | 0.0310 | -0.6220 | -0.4878 | -6.7855 |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_a591b9bf` | 265 | 909 | ELIGIBLE | — | 103.1969 | 10.3197 | 7.2524 | 5.9325 | 0.0310 | 0.0390 | 1.9171 | 1.5602 | -4.2463 |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_a8ea28c2` | 230 | 723 | ELIGIBLE | — | 85.9830 | 8.5983 | 6.8504 | 5.9759 | 0.0310 | 0.0390 | 1.3774 | 1.0204 | -4.7861 |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_d2882bfe` | 255 | 909 | ELIGIBLE | — | 74.8857 | 7.4886 | 5.4430 | 8.1311 | 0.0430 | 0.0420 | 0.4919 | 0.5362 | -5.6716 |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_b054321f` | 185 | 898 | ELIGIBLE | — | 70.2620 | 7.0262 | 6.9490 | 5.6907 | 0.0290 | 0.0330 | 0.9691 | 0.7900 | -5.1944 |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_e5086996` | 163 | 716 | ELIGIBLE | — | 62.8640 | 6.2864 | 6.9138 | 6.0400 | 0.0310 | 0.0350 | 0.6435 | 0.4646 | -5.5200 |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_94f303d3` | 195 | 898 | ELIGIBLE | — | 66.3131 | 6.6313 | 6.2118 | 7.3001 | 0.0380 | 0.0380 | 0.4411 | 0.4411 | -5.7224 |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_c943880f` | 128 | 844 | ELIGIBLE | — | 64.1162 | 6.4116 | 9.1328 | 3.7890 | 0.0190 | 0.0230 | 1.2237 | 1.0430 | -4.9398 |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_cc468133` | 108 | 664 | ELIGIBLE | G2 | 54.5694 | 5.4569 | 9.0774 | 3.9814 | 0.0200 | 0.0240 | 0.8725 | 0.6920 | -5.2909 |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_8140f17e` | 136 | 844 | ELIGIBLE | G2 | 42.5088 | 4.2509 | 5.5191 | 7.4370 | 0.0390 | 0.0350 | -0.3686 | -0.1904 | -6.5321 |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_6c789021` | 92 | 771 | ELIGIBLE | G2 | 55.6402 | 5.5640 | 11.0134 | 3.0826 | 0.0150 | 0.0190 | 1.1336 | 0.9522 | -5.0299 |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_4426de63` | 80 | 599 | ELIGIBLE | G2 | 49.6813 | 4.9681 | 10.9603 | 3.2550 | 0.0160 | 0.0200 | 0.8964 | 0.7152 | -5.2671 |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_bbc1cdde` | 95 | 771 | ELIGIBLE | G2 | 28.3862 | 2.8386 | 5.1009 | 6.4648 | 0.0340 | 0.0310 | -0.6053 | -0.4712 | -6.7688 |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_ba542585` | 186 | 854 | ELIGIBLE | — | 73.9626 | 7.3963 | 7.2164 | 6.1703 | 0.0320 | 0.0360 | 0.9524 | 0.7737 | -5.2111 |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_9d3bf21b` | 168 | 675 | ELIGIBLE | — | 63.0917 | 6.3092 | 6.6919 | 6.2026 | 0.0320 | 0.0370 | 0.6060 | 0.3828 | -5.5575 |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_0fb41630` | 184 | 854 | ELIGIBLE | — | 69.3654 | 6.9365 | 6.8979 | 6.4299 | 0.0330 | 0.0360 | 0.7614 | 0.6275 | -5.4020 |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_df1cc242` | 147 | 846 | ELIGIBLE | G2 | 56.4973 | 5.6497 | 6.8926 | 5.8875 | 0.0300 | 0.0320 | 0.4843 | 0.3947 | -5.6792 |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_29877aa9` | 135 | 671 | ELIGIBLE | G2 | 52.7863 | 5.2786 | 6.8712 | 6.2254 | 0.0320 | 0.0340 | 0.2754 | 0.1860 | -5.8881 |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_60c43197` | 158 | 846 | ELIGIBLE | — | 62.3339 | 6.2334 | 7.1252 | 6.4702 | 0.0340 | 0.0350 | 0.4923 | 0.4477 | -5.6711 |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_5958d056` | 112 | 808 | ELIGIBLE | G2 | 58.0223 | 5.8022 | 9.3372 | 3.8728 | 0.0190 | 0.0230 | 1.0286 | 0.8479 | -5.1348 |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_0901f763` | 97 | 633 | ELIGIBLE | G2 | 50.2678 | 5.0268 | 9.2114 | 4.0603 | 0.0200 | 0.0240 | 0.7341 | 0.5535 | -5.4294 |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_40171b3b` | 119 | 808 | ELIGIBLE | G2 | 43.4834 | 4.3483 | 6.4149 | 6.5806 | 0.0340 | 0.0330 | -0.1142 | -0.0695 | -6.2777 |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_50614027` | 86 | 766 | ELIGIBLE | G2 | 53.3472 | 5.3347 | 11.2320 | 3.1311 | 0.0160 | 0.0190 | 1.0145 | 0.8785 | -5.1490 |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_de24a942` | 77 | 599 | ELIGIBLE | G2 | 48.4463 | 4.8446 | 11.0569 | 3.3011 | 0.0170 | 0.0200 | 0.8112 | 0.6753 | -5.3523 |
| `grok_grid_atr_adaptive_v4_BTC_USDC_p1_329c44ea` | 87 | 766 | ELIGIBLE | G2 | 23.6829 | 2.3683 | 4.5897 | 6.5430 | 0.0340 | 0.0310 | -0.7593 | -0.6251 | -6.9228 |

### Couverture (§ C.2) — cellules sous 25 cycles

| plancher | multiplicateur | mode | cycles | sous le seuil |
|---|---|---|---|---|
| 0.015 | 1.5 | none | 483 | non |
| 0.015 | 1.5 | 1w_only | 379 | non |
| 0.015 | 1.5 | 1d_only | 417 | non |
| 0.015 | 2.0 | none | 242 | non |
| 0.015 | 2.0 | 1w_only | 194 | non |
| 0.015 | 2.0 | 1d_only | 246 | non |
| 0.015 | 2.5 | none | 143 | non |
| 0.015 | 2.5 | 1w_only | 114 | non |
| 0.015 | 2.5 | 1d_only | 146 | non |
| 0.015 | 3.0 | none | 94 | non |
| 0.015 | 3.0 | 1w_only | 80 | non |
| 0.015 | 3.0 | 1d_only | 96 | non |
| 0.02 | 1.5 | none | 375 | non |
| 0.02 | 1.5 | 1w_only | 306 | non |
| 0.02 | 1.5 | 1d_only | 326 | non |
| 0.02 | 2.0 | none | 221 | non |
| 0.02 | 2.0 | 1w_only | 185 | non |
| 0.02 | 2.0 | 1d_only | 225 | non |
| 0.02 | 2.5 | none | 138 | non |
| 0.02 | 2.5 | 1w_only | 113 | non |
| 0.02 | 2.5 | 1d_only | 143 | non |
| 0.02 | 3.0 | none | 92 | non |
| 0.02 | 3.0 | 1w_only | 80 | non |
| 0.02 | 3.0 | 1d_only | 95 | non |
| 0.025 | 1.5 | none | 265 | non |
| 0.025 | 1.5 | 1w_only | 230 | non |
| 0.025 | 1.5 | 1d_only | 255 | non |
| 0.025 | 2.0 | none | 185 | non |
| 0.025 | 2.0 | 1w_only | 163 | non |
| 0.025 | 2.0 | 1d_only | 195 | non |
| 0.025 | 2.5 | none | 128 | non |
| 0.025 | 2.5 | 1w_only | 108 | non |
| 0.025 | 2.5 | 1d_only | 136 | non |
| 0.025 | 3.0 | none | 92 | non |
| 0.025 | 3.0 | 1w_only | 80 | non |
| 0.025 | 3.0 | 1d_only | 95 | non |
| 0.03 | 1.5 | none | 186 | non |
| 0.03 | 1.5 | 1w_only | 168 | non |
| 0.03 | 1.5 | 1d_only | 184 | non |
| 0.03 | 2.0 | none | 147 | non |
| 0.03 | 2.0 | 1w_only | 135 | non |
| 0.03 | 2.0 | 1d_only | 158 | non |
| 0.03 | 2.5 | none | 112 | non |
| 0.03 | 2.5 | 1w_only | 97 | non |
| 0.03 | 2.5 | 1d_only | 119 | non |
| 0.03 | 3.0 | none | 86 | non |
| 0.03 | 3.0 | 1w_only | 77 | non |
| 0.03 | 3.0 | 1d_only | 87 | non |

Configs perdues au filtre par cellule (plancher × multiplicateur), sur les trois modes :

| plancher \ m | 1.5 | 2.0 | 2.5 | 3.0 |
|---|---|---|---|---|
| 0.015 | 0/3 | 0/3 | 0/3 | 0/3 |
| 0.02 | 0/3 | 0/3 | 0/3 | 0/3 |
| 0.025 | 0/3 | 0/3 | 0/3 | 0/3 |
| 0.03 | 0/3 | 0/3 | 0/3 | 0/3 |

## SOL/USDC

admissible **False** · warmup **W2** · benchmark comparable **False** · |J_calc| 0 · |J_eligible| 0


| config | cycles | nnz | statut | gate | net_pnl | return % | net/fees | MDD | λ_dd | λ_σ | Δ_dd | Δ_σ | LB(21,dd) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_aeeddd0c` | 415 | 786 | DESCRIPTIF | D_NOT_ADMISSIBLE | 152.2250 | 15.2225 | 6.7174 | 15.5349 | — | — | — | — | — |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_81ece5a1` | 326 | 718 | DESCRIPTIF | D_NOT_ADMISSIBLE | 65.9882 | 6.5988 | 3.7295 | 16.0169 | — | — | — | — | — |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_73d535d6` | 342 | 786 | DESCRIPTIF | D_NOT_ADMISSIBLE | 128.4012 | 12.8401 | 6.9678 | 14.3529 | — | — | — | — | — |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_ba527153` | 267 | 782 | DESCRIPTIF | D_NOT_ADMISSIBLE | 145.4343 | 14.5434 | 9.9146 | 11.4843 | — | — | — | — | — |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_5d0ca827` | 200 | 717 | DESCRIPTIF | D_NOT_ADMISSIBLE | 76.0561 | 7.6056 | 6.9148 | 11.0621 | — | — | — | — | — |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_1d8e270c` | 231 | 782 | DESCRIPTIF | D_NOT_ADMISSIBLE | 99.5492 | 9.9549 | 7.8243 | 12.5410 | — | — | — | — | — |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_a1120e8e` | 236 | 782 | DESCRIPTIF | D_NOT_ADMISSIBLE | 147.6791 | 14.7679 | 11.4506 | 10.0426 | — | — | — | — | — |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_0d72b529` | 173 | 717 | DESCRIPTIF | D_NOT_ADMISSIBLE | 75.6229 | 7.5623 | 7.8862 | 9.8522 | — | — | — | — | — |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_eb5fc5f9` | 209 | 782 | DESCRIPTIF | D_NOT_ADMISSIBLE | 111.9486 | 11.1949 | 9.7318 | 10.2705 | — | — | — | — | — |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_21f01bb0` | 230 | 782 | DESCRIPTIF | D_NOT_ADMISSIBLE | 144.1552 | 14.4155 | 11.4465 | 10.1551 | — | — | — | — | — |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_f423629b` | 168 | 717 | DESCRIPTIF | D_NOT_ADMISSIBLE | 72.8928 | 7.2893 | 7.8066 | 9.8092 | — | — | — | — | — |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_b0f6090d` | 205 | 782 | DESCRIPTIF | D_NOT_ADMISSIBLE | 110.8401 | 11.0840 | 9.8051 | 10.2420 | — | — | — | — | — |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_825bb9fa` | 415 | 786 | DESCRIPTIF | D_NOT_ADMISSIBLE | 152.3539 | 15.2354 | 6.7231 | 15.5252 | — | — | — | — | — |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_536293bc` | 326 | 718 | DESCRIPTIF | D_NOT_ADMISSIBLE | 65.9882 | 6.5988 | 3.7295 | 16.0169 | — | — | — | — | — |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_65dd3337` | 342 | 786 | DESCRIPTIF | D_NOT_ADMISSIBLE | 128.4226 | 12.8423 | 6.9689 | 14.3514 | — | — | — | — | — |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_405106c0` | 267 | 782 | DESCRIPTIF | D_NOT_ADMISSIBLE | 145.4343 | 14.5434 | 9.9146 | 11.4843 | — | — | — | — | — |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_d8dca2b8` | 200 | 717 | DESCRIPTIF | D_NOT_ADMISSIBLE | 76.0561 | 7.6056 | 6.9148 | 11.0621 | — | — | — | — | — |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_3e5bec51` | 231 | 782 | DESCRIPTIF | D_NOT_ADMISSIBLE | 99.5492 | 9.9549 | 7.8243 | 12.5410 | — | — | — | — | — |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_523e4cce` | 236 | 782 | DESCRIPTIF | D_NOT_ADMISSIBLE | 147.6791 | 14.7679 | 11.4506 | 10.0426 | — | — | — | — | — |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_e26ac6cb` | 173 | 717 | DESCRIPTIF | D_NOT_ADMISSIBLE | 75.6229 | 7.5623 | 7.8862 | 9.8522 | — | — | — | — | — |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_d0b8a32d` | 209 | 782 | DESCRIPTIF | D_NOT_ADMISSIBLE | 111.9486 | 11.1949 | 9.7318 | 10.2705 | — | — | — | — | — |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_2ff9a937` | 230 | 782 | DESCRIPTIF | D_NOT_ADMISSIBLE | 144.1552 | 14.4155 | 11.4465 | 10.1551 | — | — | — | — | — |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_96dee4d6` | 168 | 717 | DESCRIPTIF | D_NOT_ADMISSIBLE | 72.8928 | 7.2893 | 7.8066 | 9.8092 | — | — | — | — | — |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_9ff78fb7` | 205 | 782 | DESCRIPTIF | D_NOT_ADMISSIBLE | 110.8401 | 11.0840 | 9.8051 | 10.2420 | — | — | — | — | — |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_a591b9bf` | 412 | 786 | DESCRIPTIF | D_NOT_ADMISSIBLE | 152.4439 | 15.2444 | 6.7718 | 15.5164 | — | — | — | — | — |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_a8ea28c2` | 324 | 718 | DESCRIPTIF | D_NOT_ADMISSIBLE | 65.9293 | 6.5929 | 3.7474 | 16.0177 | — | — | — | — | — |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_d2882bfe` | 340 | 786 | DESCRIPTIF | D_NOT_ADMISSIBLE | 128.5050 | 12.8505 | 7.0114 | 14.3378 | — | — | — | — | — |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_b054321f` | 267 | 782 | DESCRIPTIF | D_NOT_ADMISSIBLE | 145.4343 | 14.5434 | 9.9146 | 11.4843 | — | — | — | — | — |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_e5086996` | 200 | 717 | DESCRIPTIF | D_NOT_ADMISSIBLE | 76.0561 | 7.6056 | 6.9148 | 11.0621 | — | — | — | — | — |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_94f303d3` | 231 | 782 | DESCRIPTIF | D_NOT_ADMISSIBLE | 99.5492 | 9.9549 | 7.8243 | 12.5410 | — | — | — | — | — |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_c943880f` | 236 | 782 | DESCRIPTIF | D_NOT_ADMISSIBLE | 147.6791 | 14.7679 | 11.4506 | 10.0426 | — | — | — | — | — |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_cc468133` | 173 | 717 | DESCRIPTIF | D_NOT_ADMISSIBLE | 75.6229 | 7.5623 | 7.8862 | 9.8522 | — | — | — | — | — |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_8140f17e` | 209 | 782 | DESCRIPTIF | D_NOT_ADMISSIBLE | 111.9486 | 11.1949 | 9.7318 | 10.2705 | — | — | — | — | — |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_6c789021` | 230 | 782 | DESCRIPTIF | D_NOT_ADMISSIBLE | 144.1552 | 14.4155 | 11.4465 | 10.1551 | — | — | — | — | — |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_4426de63` | 168 | 717 | DESCRIPTIF | D_NOT_ADMISSIBLE | 72.8928 | 7.2893 | 7.8066 | 9.8092 | — | — | — | — | — |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_bbc1cdde` | 205 | 782 | DESCRIPTIF | D_NOT_ADMISSIBLE | 110.8401 | 11.0840 | 9.8051 | 10.2420 | — | — | — | — | — |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_ba542585` | 399 | 786 | DESCRIPTIF | D_NOT_ADMISSIBLE | 173.4008 | 17.3401 | 7.9744 | 13.6043 | — | — | — | — | — |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_9d3bf21b` | 317 | 718 | DESCRIPTIF | D_NOT_ADMISSIBLE | 79.3585 | 7.9359 | 4.6161 | 14.8131 | — | — | — | — | — |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_0fb41630` | 332 | 786 | DESCRIPTIF | D_NOT_ADMISSIBLE | 136.8240 | 13.6824 | 7.6588 | 13.5335 | — | — | — | — | — |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_df1cc242` | 266 | 782 | DESCRIPTIF | D_NOT_ADMISSIBLE | 155.2564 | 15.5256 | 10.6661 | 10.6079 | — | — | — | — | — |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_29877aa9` | 199 | 717 | DESCRIPTIF | D_NOT_ADMISSIBLE | 75.5846 | 7.5585 | 6.9036 | 11.0664 | — | — | — | — | — |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_60c43197` | 230 | 782 | DESCRIPTIF | D_NOT_ADMISSIBLE | 109.0939 | 10.9094 | 8.6513 | 11.6652 | — | — | — | — | — |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_5958d056` | 236 | 782 | DESCRIPTIF | D_NOT_ADMISSIBLE | 147.6791 | 14.7679 | 11.4506 | 10.0426 | — | — | — | — | — |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_0901f763` | 173 | 717 | DESCRIPTIF | D_NOT_ADMISSIBLE | 75.6229 | 7.5623 | 7.8862 | 9.8522 | — | — | — | — | — |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_40171b3b` | 209 | 782 | DESCRIPTIF | D_NOT_ADMISSIBLE | 111.9486 | 11.1949 | 9.7318 | 10.2705 | — | — | — | — | — |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_50614027` | 230 | 782 | DESCRIPTIF | D_NOT_ADMISSIBLE | 144.1552 | 14.4155 | 11.4465 | 10.1551 | — | — | — | — | — |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_de24a942` | 168 | 717 | DESCRIPTIF | D_NOT_ADMISSIBLE | 72.8928 | 7.2893 | 7.8066 | 9.8092 | — | — | — | — | — |
| `grok_grid_atr_adaptive_v4_SOL_USDC_p1_329c44ea` | 205 | 782 | DESCRIPTIF | D_NOT_ADMISSIBLE | 110.8401 | 11.0840 | 9.8051 | 10.2420 | — | — | — | — | — |

### Couverture (§ C.2) — cellules sous 25 cycles

| plancher | multiplicateur | mode | cycles | sous le seuil |
|---|---|---|---|---|
| 0.015 | 1.5 | none | 415 | non |
| 0.015 | 1.5 | 1w_only | 326 | non |
| 0.015 | 1.5 | 1d_only | 342 | non |
| 0.015 | 2.0 | none | 267 | non |
| 0.015 | 2.0 | 1w_only | 200 | non |
| 0.015 | 2.0 | 1d_only | 231 | non |
| 0.015 | 2.5 | none | 236 | non |
| 0.015 | 2.5 | 1w_only | 173 | non |
| 0.015 | 2.5 | 1d_only | 209 | non |
| 0.015 | 3.0 | none | 230 | non |
| 0.015 | 3.0 | 1w_only | 168 | non |
| 0.015 | 3.0 | 1d_only | 205 | non |
| 0.02 | 1.5 | none | 415 | non |
| 0.02 | 1.5 | 1w_only | 326 | non |
| 0.02 | 1.5 | 1d_only | 342 | non |
| 0.02 | 2.0 | none | 267 | non |
| 0.02 | 2.0 | 1w_only | 200 | non |
| 0.02 | 2.0 | 1d_only | 231 | non |
| 0.02 | 2.5 | none | 236 | non |
| 0.02 | 2.5 | 1w_only | 173 | non |
| 0.02 | 2.5 | 1d_only | 209 | non |
| 0.02 | 3.0 | none | 230 | non |
| 0.02 | 3.0 | 1w_only | 168 | non |
| 0.02 | 3.0 | 1d_only | 205 | non |
| 0.025 | 1.5 | none | 412 | non |
| 0.025 | 1.5 | 1w_only | 324 | non |
| 0.025 | 1.5 | 1d_only | 340 | non |
| 0.025 | 2.0 | none | 267 | non |
| 0.025 | 2.0 | 1w_only | 200 | non |
| 0.025 | 2.0 | 1d_only | 231 | non |
| 0.025 | 2.5 | none | 236 | non |
| 0.025 | 2.5 | 1w_only | 173 | non |
| 0.025 | 2.5 | 1d_only | 209 | non |
| 0.025 | 3.0 | none | 230 | non |
| 0.025 | 3.0 | 1w_only | 168 | non |
| 0.025 | 3.0 | 1d_only | 205 | non |
| 0.03 | 1.5 | none | 399 | non |
| 0.03 | 1.5 | 1w_only | 317 | non |
| 0.03 | 1.5 | 1d_only | 332 | non |
| 0.03 | 2.0 | none | 266 | non |
| 0.03 | 2.0 | 1w_only | 199 | non |
| 0.03 | 2.0 | 1d_only | 230 | non |
| 0.03 | 2.5 | none | 236 | non |
| 0.03 | 2.5 | 1w_only | 173 | non |
| 0.03 | 2.5 | 1d_only | 209 | non |
| 0.03 | 3.0 | none | 230 | non |
| 0.03 | 3.0 | 1w_only | 168 | non |
| 0.03 | 3.0 | 1d_only | 205 | non |

Configs perdues au filtre par cellule (plancher × multiplicateur), sur les trois modes :

| plancher \ m | 1.5 | 2.0 | 2.5 | 3.0 |
|---|---|---|---|---|
| 0.015 | 0/3 | 0/3 | 0/3 | 0/3 |
| 0.02 | 0/3 | 0/3 | 0/3 | 0/3 |
| 0.025 | 0/3 | 0/3 | 0/3 | 0/3 |
| 0.03 | 0/3 | 0/3 | 0/3 | 0/3 |
