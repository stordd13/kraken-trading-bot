# C3 — validité d'entrée (§ I-A)

généré 2026-09-28T00:00:00+00:00 · protocole 9300f4e53bfd3663 · observations `/home/bruno/runs/c3b_prefix/out/run1/observations.json` sha256 `57e48213c8b4a46f`

Préfixe `train`, ancrage `2020-09-11T21:36:00+00:00`, 12 candidats, provenance `unknown`.

| assertion | statut | détail |
|---|---|---|
| I-A.1 forme des observations | ok | 12 entrées, préfixe 'train' |
| I-A.2 D5 — contrats d'instrument égaux au manifeste | ok | ok |
| I-A.3 bornes du préfixe exactement [début, T] | ok | ok |
| I-A.4 unicité des identités et univers fermé | ok | 12 identités, égales à l'univers |
| I-A.5 provenance de l'univers | ok | provenance 'unknown' (liste close § A.5) |
| I-A.6 amorçage du préfixe : séries de décision, sufficient recalculé | ok | ok |
| I-A.7 artefact de couverture | ok | ok |
| I-A.8 D2 — promotion en refus d'artefact sur la totalité | ok | D2 échoue sur 4/12 candidats — retirés, la chaîne continue (§ I.1 l.4) |
| I-A.fin aucune clause non assertable | ok | ok |

Entrée conforme ; 4 candidat(s) retiré(s) par D2 (ligne 4).

Diagnostics de candidats (D2) : 4

- `7ffd47bfa073f71862bb2bf92beebc5ddb8587b05a59e6e4962b7ca8fe46c95a` : séries insuffisantes 4h
- `be44ed223e9b1551a748c2e19147b8ab669858549c3443b07a9d7cbddb217c25` : séries insuffisantes 1w, 4h
- `dfc62d028a2cde5289f5e48368be83233778aea231b1cf41c13b2a8a257a94bf` : séries insuffisantes 1d, 4h
- `e00e5e4ae94dc53d60bde692e9de5fe6ed60cef29db02d487d08012c91bb3c64` : séries insuffisantes 1d, 1w, 4h

Portée du run : Essai d'instrument du producteur C3b (lot 3), aucune lecture économique. Fenêtre de conformité 2020-01-06 → 2020-12-28, hors campagne et entièrement antérieure au 2021-03-01 (garde-fou 6). Provenance « unknown » déclarée pour qu'aucun « validé » ne soit atteignable sur une fenêtre d'instrument (décision du 27/09) : les quatre paramétrages sont des représentants des classes C1, C2, C5, C6 (un par ensemble de decision_timeframes), tirés des cas-sondes du lot 1, sans rapport avec un résultat. Coûts par paire : ceux de config/pair_costs_b4.json pour la paire de déploiement (dette 24 sans objet ici) ; min_order_usdc 5.0 = valeur du rejeu, inerte sur le grid.
