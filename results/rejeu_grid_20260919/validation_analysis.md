# Rejeu diagnostic grid — validité des analyses (§ I-B)

`ok` : **True** · sortie `0` · prespec `20079aff60a55152`

| # | Assertion | État | Détail |
|---|---|---|---|
| I-B.1 | effect.json records B, L, seeds, numpy, |J_calc| and the λ mode | ok | ok |
| I-B.2 | frozen bootstrap parameters: B, block lengths, seeds | ok | seeds rebuilt in-script from SEED_BASE 20260919 |
| I-B.3 | degenerate replications counted and the § F.7 rule applied | ok | 0 degenerate replication(s) recorded, 0 config(s) over the cap |
| I-B.4 | first failing gate of every ineligible config | ok | ineligible configs by first failing gate: D_NOT_ADMISSIBLE x48 |
| I-B.5 | a rerun on the same inputs reproduces LB_j bit for bit | ok | 96 LB block(s) compared against the --rerun artifact |
| I-B.6 | signatures.json present or explicitly not producible | ok | 2 pair block(s); § G.5: degeneracy never changes a verdict |
| I-B.7 | clamp.json present or explicitly not producible | ok | § G.5: the clamp never changes a verdict, in any direction |

Un échec ici donne `inconclusif (F_NOT_ESTIMABLE)` **sans toucher au verdict de campagne** (§ I-B).
