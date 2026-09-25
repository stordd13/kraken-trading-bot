# Mesure SOL/D2 — timeframes de décision de `grok_grid_atr_adaptive_v4` et amorçage au 2021-03-01

> **Mesuré le 2026-09-25 sur le serveur, lecture seule.** Brief : `agent/agent_sol_d2_1w_modes.md`. Protocole :
> `docs/protocole_c3.md` v2.1 (sha256 `9300f4e5…4129`). Artefact : `warmup_2021-03-01.json` (sha256
> `566beeb457309d5a17a1bc167087a17b6c76becb463551256efd68b4017dd35d`), produit par `scripts/audit/warmup_at.py` au
> commit `c38d718`. Tout chiffre de mesure cité ici se lit dans ce JSON ; les lignes de code sont citées au SHA
> `c38d718`, où `src/`, `scripts/backtest.py` et `docs/` sont identiques à `98b3e50` (`git diff --stat 98b3e50 c38d718
> -- src scripts/backtest.py docs` vide). **Aucune simulation, aucune sélection, aucune écriture en base.**

## 0. En tête — faits nouveaux

1. **L'axe « `bias_1d ≠ 0` » est faux ; `grid_levels` est un axe.** `_get_directional_bias`
   (`src/krakenbot/strategies/grok_grid_atr_adaptive_v4.py:224-249`) calcule `half = grid_levels // 2` (`:235`) et
   `int(float(self.bias_1d) * half)` (`:238`, `:242`), puis borne par `max(1, ·)` (`:249`). Exécutée sur la méthode
   réelle :
   - `bias_1d ≠ 0` **n'est pas suffisant** : `grid_levels = 12`, `bias_1d = 0,1` → `int(0,6) = 0`, partage (6, 6) sous
     tout régime ; `regime_1d` ne décide rien ;
   - `bias_1d ≠ 0` **n'est pas nécessaire** : `grid_levels` impair (13), `bias_1d = 0` → le bras bear rend (7, 6)
     contre (6, 7) pour les autres régimes ; `regime_1d` décide.

   Le troisième axe est `bias_live(grid_levels, bias_1d)` : la méthode n'est pas constante sur le domaine de
   `get_regime` (§ 3.2). **Conséquence pour C3b : la méthode de classe `decision_timeframes` prend `grid_levels` en
   entrée**, et classe par l'oracle, pas par une forme fermée. La parenthèse illustrative du § A.8 l.515
   (« `bear_protection_mode` et `bias_1d` décident si `regime_1d` et la porte 1 w vivent ») est incomplète ; la règle
   normative qu'elle illustre (liste « dérivée de ses paramètres effectifs », l.513-516) tient. **Candidat amendement
   v2.2 daté, à regrouper avec la re-passe Astra** — non tranché ici ; liste au § 8.1 (avec une seconde imprécision,
   l.605-606), dettes producteur au § 8.2.
2. **Dette C3b, consignée sans correctif.** `:131` lit `pause_1w_strong_bear` sans coercition de type ; `:384` en
   prend la vérité Python. Une chaîne `"false"` dans un manifeste JSON est vraie : la porte 1 w vit sur un candidat
   que son auteur croyait sans protection. Constaté par la sonde (§ 9, cas « pause 'false' en chaîne » → classe C2).
   **Le producteur C3b doit refuser un type non booléen à l'entrée.** (§ 8.2-1)
3. **BTC et ETH : aucun `fail`.** Rien de nouveau de ce côté : toutes leurs séries sont `sufficient` au 2021-03-01.
4. **SOL 1 w : 29 bougies, première le 2020-08-17, prête le 2021-07-26** — les trois chiffres du § A.8 l.603-604
   (calculés à la main) sont retrouvés par la mesure (§ 6).

## 1. Chronologie, commandes, environnement

Branche `feat/c3b-sol-d2` depuis `dev` @ `98b3e50` (choix de Bruno : branche puis merge, pas de commit direct sur
`dev`). Plan relu et amendé par Bruno le 25/09 (GO avec trois remarques : `class_of` par l'oracle ; dette de
coercition ; fait nouveau → amendement v2.2).

| Étape | Commit / instant (UTC) | Objet |
|---|---|---|
| 1 | `c38d718` | `feat(audit): warmup_at — amorçage C2 mesuré à une date, lecture seule` — script + 93 tests |
| 1 | 11:00:12 → 11:24:56 | suite complète locale : 24 échecs `_full` par coupure du tunnel (§ 9.3) |
| serveur | 11:33 | bundle `98b3e50..feat/c3b-sol-d2` (sha256 `aa95e92e…f229`, identique Mac / serveur) |
| serveur | 11:37:31 | 1ᵉʳ lancement **nul** — défaut de ma commande de lancement (`bash` au lieu de `bash -lc`) : `poetry` hors du PATH, **chaque étape a échoué à l'exécution de `poetry` lui-même** (code 127, `poetry: command not found` dans `alembic_before.txt`) ; aucun processus Python n'a démarré, donc **aucune connexion ni lecture en base**, aucun JSON, pas de `transaction_read_only` à consigner. Codes : `server/launch1_poetry_absent/status.txt` ; brut dans l'archive |
| serveur | 11:38:16 → 11:39:19 | relance sous `bash -lc`, même pilote (sha256 inchangé) : `alembic current` → `warmup_at` (code 0) → `alembic current` |
| serveur | 11:39:19 → 12:51:10 | 24 `_full` de déterminisme, même SHA, même session : **`full=0`**, 24/24 (§ 9.4) |
| 2 | ce commit | `docs(results): mesure SOL/D2 et classes decision_timeframes au 2021-03-01` — rapport, JSON, preuves serveur, extrait |

**Checkout isolé** `~/runs/sol_d2/repo` (convention `skills/deployment.md`, § « Convention chantier serveur ») :
clone local de l'arbre du service (`~/apps/kraken-trading-bot`, `dev` @ `98b3e50`, propre, jamais touché), commit du
chantier par `git bundle`, HEAD **détaché** sur `c38d7183315ed9b28ce7cb859ed8262a03095143` (d'où `branch: ""` dans la
provenance du JSON), `.env` copié depuis le service, `.venv` propre au répertoire (`poetry install` rc 0,
Python 3.12.3). Base en accès **local** (`localhost:5432`), aucun tunnel. Collector actif, aucun `systemctl`.

**Pilote** `server/run_sol_d2.sh` (sha256 `300fb2f11c30cd4bec1bf418dc1a0eb64694d1117720c1f2f7a866bafd9f191e`, relu
par Bruno avant lancement) : `set -o pipefail`, pas de `set -e` ; `unset SCHEDULER_PAIRS SCHEDULER_INTERVALS
VIRTUAL_ENV` ; refus (code 2) si HEAD ≠ `c38d718` ou arbre suivi sale ; chaque sortie passée par `tee` lue par
`${PIPESTATUS[0]}` ; codes par étape dans `server/status.txt` ; second `alembic current` inconditionnel ; `_full`
sautés seulement si `warmup_at` sort en 2, les 24 tournent même après un échec. Lancement :
`tmux new -d -s sol_d2-20260926 "bash -lc \"bash /home/bruno/runs/sol_d2/run_sol_d2.sh\""`.

```bash
poetry run python scripts/audit/warmup_at.py --output /home/bruno/runs/sol_d2/out/warmup_2021-03-01.json
```

**Lecture seule** : garantie par Postgres, pas seulement par le code — chaque connexion pose
`default_transaction_read_only = on` (`ReadOnlyDatabaseManager`), `transaction_read_only = on` asserté et écrit dans
le JSON. **`alembic current` inchangé** : `c3bd1e7a0001 (head)` avant et après (`server/alembic_before.txt`,
`server/alembic_after.txt`), mêmes valeurs lues par le script dans `alembic_version` au début et à la fin
(`database.alembic_version_before/after`). Aucune requête d'écriture, aucune migration.

**`~/runs/sol_d2/` supprimé le 2026-09-25 à 13:30:27Z** (`rm -rf`), après vérification, dans cet ordre (condition de
Bruno : pas de suppression sur la foi d'un `scp` qui a rendu 0) : (1) l'archive `~/archive/sol_d2_20260925/sol_d2_server_runs_20260925.tgz`
se relit — `sha256sum -c` OK, `tar -tzf` 88 entrées, et son contenu extrait est identique aux sources (`diff -r` sur
`out/`, `out_launch1_poetry_absent/`, `cmp` du pilote) ; l'archive du journal local redonne `7792be0a…` après
décompression ; (2) les 53 fichiers de `server/` (hors pilote et tentative nulle, vérifiés à part) ont des sha256
identiques à ceux du serveur, de même que le JSON (`566beeb4…`), le pilote (`300fb2f1…`) et le `status.txt` de la
tentative nulle (`4ebe4e65…`) ; tous les fichiers du § 11 sont présents, 24/24 combos. La session tmux
`sol_d2-20260926` s'était fermée seule à la fin du pilote (12:51:10Z). Arbre du service inchangé (`98b3e50`, propre),
collector actif. Les bruts restent dans `~/archive/sol_d2_20260925/` (§ 9.3, § 9.4).

## 2. Table A — ce que la stratégie lit

Quatre appels à l'analyzer, tous dans `_handle_ohlc`, sur les seules bougies 4 h (`:373-375`), après les gardes
`_running` / prix / analyzer (`:363-378`).

| Ligne | Appel | TF | Exécuté | Alimente |
|---|---|---|---|---|
| `:383` | `get_regime("1w")` | 1 w | chaque décision 4 h, inconditionnellement | porte de pause si `pause_1w_strong_bear` (`:384`, log de la pause `:397`) ; sinon logs seulement (`:425` à la reprise, `:462`) |
| `:405` | `get_regime("1d")` | 1 d | si `bear_protection_1d_enabled` (`:404`) | porte de pause 1 d (`:406`) |
| `:428` | `get_atr(self.atr_period, "4h")` | 4 h | hors pause | porte HOLD si `None` ou `<= 0` (`:429-440`) ; espacement (`:442`) |
| `:443` | `get_regime("1d")` | 1 d | hors pause, ATR disponible | biais directionnel : `_build_grid` (`:473`, `:516`) → `_get_directional_bias` (`:267`) si `bias_live` ; sinon logs seulement (`:446`, `:462`) |

Aucune autre lecture : `_calculate_spacing` (`:211-222`) ne lit que ses arguments, `_build_grid` (`:251-315`) et
`_recalculate_grid` (`:498-537`) reçoivent `regime_1d` de `:443`, `on_trade_filled` et le sizing lisent l'état de la
grille (`_grid_spacing`, `order_size_usdc`), jamais l'analyzer. Le 5 m alimente les remplissages et
`analyzer.update` (`scripts/backtest.py:2991-2992`) mais aucune porte : le prix d'une décision est la clôture de la
bougie 4 h elle-même (`:367`). La liste (appel, TF) est épinglée au source par test (§ 9.1).

## 3. Table B — classes d'équivalence de `decision_timeframes`

### 3.1 La table

Axes = **flags effectifs**, jamais le mode. `(pause_1w, bear_1d) = (vrai, vrai)` est inatteignable : le setter
(`:137-152`) ne pose jamais les deux, et `bear_protection_1d_enabled` n'est lu d'aucun paramètre (`:132`) ; un mode
invalide lève (`:149`). Il reste **six classes**. TF lus : `{1d, 1w, 4h}` dans toutes.

| Classe | `pause_1w` | `bear_1d` | `bias_live` | Modes qui y mènent | TF lus | TF de décision |
|---|---|---|---|---|---|---|
| C1 | vrai | faux | vrai | `1w_only` ; `None` + `pause_1w_strong_bear` vrai (défaut `:131`) | 1d, 1w, 4h | **{1d, 1w, 4h}** |
| C2 | vrai | faux | faux | idem | 1d, 1w, 4h | **{1w, 4h}** |
| C3 | faux | vrai | vrai | `1d_only` | 1d, 1w, 4h | **{1d, 4h}** |
| C4 | faux | vrai | faux | `1d_only` | 1d, 1w, 4h | **{1d, 4h}** |
| C5 | faux | faux | vrai | `none` ; `None` + `pause_1w_strong_bear` faux | 1d, 1w, 4h | **{1d, 4h}** |
| C6 | faux | faux | faux | idem | 1d, 1w, 4h | **{4h}** |

Les défauts de classe (`grid_levels = 12`, `bias_1d = 0,2`, `pause_1w_strong_bear = True`, `atr_period = 14`) sont
en **C1** (JSON `strategy.class`). Le balayage P7 (`scripts/p7_grids.py`, `GRID_ATR_GRID`) ne fait varier ni
`grid_levels` ni `bias_1d` : ses trois modes tombent en C1, C3 et C5 — constat, pas choix d'univers (§ A.5).

### 3.2 Le troisième axe : `bias_live(grid_levels, bias_1d)`, par l'oracle

**Définition (mesure)** : `bias_live` est vrai si et seulement si `_get_directional_bias`, exécutée non liée sur
`(grid_levels, bias_1d)`, n'est pas constante sur le domaine de `get_regime` — les cinq valeurs de `MarketRegime`
et `None` (`src/krakenbot/indicators/multi_timeframe.py:750-777`). C'est ce que fait `warmup_at.bias_live`, et ce
que `class_of` utilise (remarque de Bruno au GO : la forme fermée passe par `float`, les clamps font exception).

**Explication (non normative)** : pour `grid_levels ≥ 2`, `bias_live ⟺ int(float(bias_1d) × (grid_levels // 2)) ≠ 0
ou grid_levels impair` — vérifié contre l'oracle sur `grid_levels ∈ [2, 40]` × onze valeurs de `bias_1d` (dont 0,
0,1, 0,16, 0,17, 0,3 et −0,2). **Elle est fausse à `grid_levels = 1`** : `half = 0`, les clamps `max(1, ·)`
(`:249`) rendent (1, 1) sous tout régime, `bias_live` est faux alors que la forme dit « impair, vivant ». La
classmethod C3b devra classer par l'oracle, comme ce script.

### 3.3 L'axe `pause_1w` est la vérité Python de l'attribut

`class_of` lit `bool(strategy.pause_1w_strong_bear)` parce que `:384` teste `self.pause_1w_strong_bear and …` : la
classe suit ce que la stratégie **fait**, y compris sur une chaîne `"false"` (vraie). C'est la dette du § 0.2.

## 4. Liste statique ≠ liste de décision, et ce que fait le moteur

**`indicator_requirements`** (`scripts/backtest.py:420-425`) déclare pour la stratégie, **quel que soit le mode** :
`atr 4h (atr_period)`, `regime 1d`, `regime 1w` — liste statique `{1d, 1w, 4h}`, besoins `4h = 14`, `1d = 50`,
`1w = 50` (`:305`), identiques pour toute classe (JSON `requirements`). Écart à la liste de décision
(`static_minus_decision`) :

| C1 | C2 | C3 | C4 | C5 | C6 |
|---|---|---|---|---|---|
| ∅ | {1d} | {1w} | {1w} | {1w} | {1d, 1w} |

**C'est le fait que C3b doit absorber** : la liste statique sert à pré-enregistrer et à amorcer (C2, R2) ; elle ne
peut pas servir à D2, qui ne lit que les TF de décision (§ A.8 l.452). La méthode de classe par candidat (ROADMAP,
exigences C3b, l.143) est ce qui les sépare.

**Quand `sufficient == False`, le moteur ne refuse rien.** `load_context_series` rend un rapport
(`scripts/backtest.py:519-531`) ; le moteur grid le range (`:3075`), l'imprime avec le drapeau `INSUFFICIENT`
(`:3699`) et l'exporte (`:3826`, runners P6/P7) — le run continue. **D2 (`scripts/audit/c3_entry.py:473-513`) est la
seule barrière.** Et le défaut n'est pas bruyant côté stratégie : tant que la 50ᵉ bougie 1 w n'est pas passée,
`get_regime("1w")` rend `None` (`multi_timeframe.py:768-771`), `None == "strong_bear"` est faux à `:384`, et la
**porte 1 w reste ouverte en silence**.

## 5. Étape 2 — bornes de forme de `decision_timeframes`

Ensembles triés que la méthode de classe C3b devra rendre (JSON `classes[].decision_tfs`) :

| Classe | `decision_timeframes` |
|---|---|
| C1 | `["1d", "1w", "4h"]` |
| C2 | `["1w", "4h"]` |
| C3, C4, C5 | `["1d", "4h"]` |
| C6 | `["4h"]` |

Quatre ensembles distincts (`decision_shape.distinct_sets`). **Aucune classe ne rend un ensemble vide**
(`empty_classes: []`, § A.8 l.521 : une liste vide serait une erreur d'entrée) ; **le 4 h est partout**
(`classes_without_4h: []`) — la porte HOLD de l'ATR (`:429-440`) vit dans toute classe, même quand l'espacement est
bridé par `min_spacing_pct` / `max_spacing_pct`.

## 6. Étape 3 — amorçage mesuré au 2021-03-01

**Arguments** — ceux du moteur grid, épinglés par test (§ 9.1) : `end = T = 2024-11-22T04:48:00Z`, recalculé par
`cc.anchor_of(2021-03-01, 2026-06-29)` (§ A.3 l.237-238) et comparé à l'ancrage déclaré ; chargeurs de
`GridBacktester` (`scripts/backtest.py:3035-3054`), `exchange = 'binance'` ; `window_start` (`:2424-2426`) :

| TF | `window_start` | `required` | origine |
|---|---|---|---|
| 5 m | 2021-03-01 (= `start`) | 0 | **pas une série de contexte** : chargé sur `[start, end]` par `_load_candles` (`:2880` → `:3022-3033`), absent des besoins ; mesuré par la même fonction avec `required = 0` — **D1 le couvre, D2 non** |
| 4 h | 2021-02-14 | 14 | `start − 15 j` ; `atr_period` des défauts de classe |
| 1 d | 2020-06-24 | 50 | `start − 250 j` ; régime |
| 1 w | 2020-01-26 | 50 | `start − 400 j` ; régime |

**Mesure** (règle C2 réelle, `load_context_series` ; `sufficient` recoupé par `cc.warmup_sufficient`, identique
partout) :

| Paire | TF | required | loaded | extended_by | stale | gap | sufficient | first | last | prête le |
|---|---|---|---|---|---|---|---|---|---|---|
| BTC/USDT | 5 m | 0 | 1 | 0 | 0 | 0 | ✓ | 2021-03-01 00:00 | 2021-03-01 00:00 | — |
| BTC/USDT | 4 h | 14 | 91 | 0 | 0 | 0 | ✓ | 2021-02-14 00:00 | 2021-03-01 00:00 | 2021-02-16 04:00 |
| BTC/USDT | 1 d | 50 | 251 | 0 | 0 | 0 | ✓ | 2020-06-24 | 2021-03-01 | 2020-08-12 |
| BTC/USDT | 1 w | 50 | 58 | 0 | 0 | 0 | ✓ | 2020-01-27 | 2021-03-01 | 2021-01-04 |
| ETH/USDT | 5 m | 0 | 1 | 0 | 0 | 0 | ✓ | 2021-03-01 00:00 | 2021-03-01 00:00 | — |
| ETH/USDT | 4 h | 14 | 91 | 0 | 0 | 0 | ✓ | 2021-02-14 00:00 | 2021-03-01 00:00 | 2021-02-16 04:00 |
| ETH/USDT | 1 d | 50 | 251 | 0 | 0 | 0 | ✓ | 2020-06-24 | 2021-03-01 | 2020-08-12 |
| ETH/USDT | 1 w | 50 | 58 | 0 | 0 | 0 | ✓ | 2020-01-27 | 2021-03-01 | 2021-01-04 |
| SOL/USDT | 5 m | 0 | 1 | 0 | 0 | 0 | ✓ | 2021-03-01 00:00 | 2021-03-01 00:00 | — |
| SOL/USDT | 4 h | 14 | 91 | 0 | 0 | 0 | ✓ | 2021-02-14 00:00 | 2021-03-01 00:00 | 2021-02-16 04:00 |
| SOL/USDT | 1 d | 50 | 202 | 0 | 0 | 0 | ✓ | 2020-08-12 | 2021-03-01 | 2020-09-30 |
| SOL/USDT | 1 w | 50 | **29** | 0 | 0 | 0 | **✗** | **2020-08-17** | 2021-03-01 | **2021-07-26** (`short_by` 21) |

« Prête le » = `ready_at`, estampille de la `required`-ième bougie chargée. Aucune extension arrière n'a été
nécessaire (`extended_by = 0` partout) ; SOL 1 w ne pouvait pas en bénéficier : aucune bougie 1 w avant le
2020-08-17.

**Contrôles** (JSON `controls`, tous `ok`) :

| Contrôle | Attendu | Observé | Source de l'attendu |
|---|---|---|---|
| SOL 1 w au début du préfixe | 29, première 2020-08-17 | 29, 2020-08-17 | § A.8 l.603-604 |
| rows `ohlc_derived` dans un historique d'amorçage | 0 | 0 | les 8 estampilles reconstruites (2022-06-06 … 2025-03-03, 24 rows, 1 w, trois paires — JSON `ohlc_derived`) sont toutes postérieures au 2021-03-01 ; intersection faite sur les estampilles chargées `<= start`, paire × intervalle |
| `count(*)` `exchange = 'binance'` | 11 952 996 | 11 952 996 | `results/reconstruction_1w_2022_2025/evidence/independent_counts.txt:1` |
| `alembic_version` avant / après | `c3bd1e7a0001` / idem | `c3bd1e7a0001` / idem | brief § Validation |

**Recoupement (non bloquant, demandé par Bruno)** : `ready_at` SOL 1 w = **2021-07-26**, égal à la date calculée à
la main au § A.8 l.604. Le chiffre du protocole est juste.

## 7. Étape 4 — table C (D2 = ET des `sufficient` sur les TF de décision)

**SOL survit dans C3 à C6, sort dans C1 et C2, l'ensemble survivant n'est pas vide.** Au 2021-03-01, SOL 4 h et SOL
1 d sont `sufficient` — 4 h : 91 bougies pour 14 requises ; 1 d : 202 pour 50, première le 2020-08-12, sans trou ni
retard (§ 6) — ; seul SOL 1 w ne l'est pas (29 pour 50). Seules les classes dont le 1 w est un TF de décision
tombent. BTC et ETH passent dans les six classes.

| Classe | TF de décision | BTC/USDT | ETH/USDT | SOL/USDT |
|---|---|---|---|---|
| C1 | 1d, 1w, 4h | pass | pass | **fail(1w: 29/50)** |
| C2 | 1w, 4h | pass | pass | **fail(1w: 29/50)** |
| C3 | 1d, 4h | pass | pass | pass |
| C4 | 1d, 4h | pass | pass | pass |
| C5 | 1d, 4h | pass | pass | pass |
| C6 | 4h | pass | pass | pass |

**Sur SOL** : C1 et C2 sortent — **toute configuration dont la porte de pause 1 w vit** (`pause_1w_strong_bear`
vrai : mode `1w_only`, ou mode `None` avec le défaut de classe), quel que soit son biais. C3 à C6 survivent : modes
`1d_only` et `none`, avec ou sans biais vivant. **L'ensemble des classes survivantes n'est pas vide.**

**Ce que « fail » veut dire pour un candidat, en clair.** Un candidat C1 ou C2 sur SOL ne se contente pas de rater un
critère d'admissibilité : lancé au 2021-03-01, il tournerait ses **21 premières semaines** (jusqu'au 2021-07-26,
`short_by` 21) avec sa protection bear hebdomadaire **désactivée sans le savoir** — `get_regime("1w")` rend `None`,
la comparaison de `:384` est fausse, la grille ne se met jamais en pause (§ 4). Le moteur l'imprimerait
`INSUFFICIENT` et continuerait. La configuration simulée ne serait pas celle que le candidat décrit : c'est la
justification concrète de D2 (§ A.8 l.501-511), à porter telle quelle à la conversation manifeste.

**Sur BTC et ETH** : `pass` partout, comme attendu — aucun fait nouveau.

## 8. Protocole — ce qu'il dit, ce que le manifeste devra déclarer (cité, non tranché)

- **Portée de D2 : le candidat** (§ A.8 l.452 ; définition des portées l.443-447). Un candidat SOL retiré par D2 ne
  retire **pas** la paire (ce que ferait une clause de portée paire, comme D1).
- **Promotion** (§ I.1, ligne 4, l.1816 ; ligne 5, l.1817 ; règle l.1832-1835) : D2 sur **une partie** des
  candidats → ils sortent, code 0, la chaîne continue ; D2 sur **la totalité** des candidats de l'artefact → refus
  d'artefact `D_WARMUP_PREFIX`, code 2, aucun classement. Les candidats SOL de C1 et C2 relèvent de la ligne 4 : ils
  sortent, les autres restent. **SOL est partiel** si l'univers porte au moins un candidat SOL de C3-C6, **absent**
  s'il n'y porte que des candidats C1/C2. La ligne 5 ne s'appliquerait qu'à un artefact dont **tous** les candidats
  échouent D2 : BTC et ETH passant dans toutes les classes (§ 7), un artefact qui porte au moins un candidat BTC ou
  ETH n'y tombe pas. Le protocole dit « partiel ou absent » (l.605-606) ; la mesure ne choisit pas l'univers.
- **Ce que le manifeste devra déclarer** :
  - `decision_timeframes` **par stratégie ou par candidat** (surcharge) — § A.8 l.517-519, forme lue par
    `scripts/audit/c3_common.py:1323-1329` (par stratégie) et `:1348-1358` (surcharge par candidat, jamais vide).
    **Une déclaration unique par stratégie ne peut pas être juste pour un univers grid qui couvre plus d'une classe**
    (quatre ensembles distincts, § 5) : la surcharge par candidat est la forme qui le permet, et le désaccord avec la
    liste exportée par l'observation est une violation (§ I.1 ligne 15 ; `c3_entry.py:489`) ;
  - **les 8 estampilles 1 w dérivées**, lues dans `ohlc_derived` (ROADMAP, exigences C3b, l.155-159) — aucune n'entre
    dans un amorçage au 2021-03-01 (§ 6) ; six tombent dans le préfixe (couverture D1), deux dans la période évaluée.
- **Ce que le manifeste ne devra pas faire** : déplacer le début du préfixe pour sauver SOL (au 2021-07-26 ou après).
  La fenêtre de la première campagne est déclarée et « ne bouge plus » (§ A.3 l.263-277) ; le choix de fenêtre est
  « un second levier de shopping » (l.275) ; changer de fenêtre est une nouvelle campagne, et une autre fenêtre sur la
  même famille relève de la clôture de famille et du « zéro retry-tuning » (`docs/CONTRAINTES_POST_B4.md` § 10.1,
  l.190-192, l.208). C'est un choix d'univers et de campagne (§ A.5, § A.6), **pas une conséquence de cette mesure**.

### 8.1 Candidats amendement v2.2 (protocole) — à regrouper avec la re-passe Astra, non tranchés ici

1. **§ A.8 l.515 — incomplet.** La parenthèse illustrative « pour la famille grid : `bear_protection_mode` et `bias_1d`
   décident si `regime_1d` et la porte 1 w vivent » omet `grid_levels` : `regime_1d` décide si et seulement si
   `_get_directional_bias` n'est pas constante sur le domaine de `get_regime` (§ 3.2), ce qui dépend de
   `(grid_levels, bias_1d)` — `bias_1d ≠ 0` n'est ni suffisant ni nécessaire (§ 0.1). La règle normative qu'elle
   illustre (l.513-516 : liste dérivée des paramètres effectifs par une méthode de classe) tient.
2. **§ A.8 l.605-606 — imprécis.** « **absent** si tous les modes de la famille **lisent** le 1 w » raisonne en modes
   qui lisent ; or le code lit le 1 w dans **tous** les modes (`:383`, inconditionnel) et ne le fait décider que là
   où la porte de pause vit (`:384`). Le critère de D2 est « alimente une porte de décision » (l.452) : c'est la
   formulation que la phrase devrait porter.

### 8.2 Dettes C3b (producteur) — pas le protocole

1. **Coercition de `pause_1w_strong_bear`.** `:131` le lit sans coercition de type et `:384` en prend la vérité
   Python : une chaîne `"false"` dans un manifeste JSON est vraie, la porte 1 w vit sur un candidat déclaré sans
   protection (constaté par la sonde, § 9.1). **Le producteur doit refuser un type non booléen à l'entrée.**
2. **Entrées de la méthode de classe.** `decision_timeframes` prend `grid_levels` en entrée (conséquence de 8.1-1) et
   classe `bias_live` **par l'oracle** — la méthode réelle sur le domaine de `get_regime` —, jamais par la forme
   fermée (`float`, clamps à `grid_levels = 1`, § 3.2), comme `warmup_at.class_of`.

## 9. Validation

### 9.1 Tests — `tests/test_scripts/test_warmup_at.py`, 93 tests, aucun ne touche la base

Choix de Bruno : aucun test base, donc aucun marqueur `db` (il n'existe pas : `pyproject.toml:109-113`,
`--strict-markers`) ; la partie base n'est exercée qu'au run serveur, par les contrôles internes du script.

- **Épinglés au moteur** : `GridBacktester` rejoué avec un enregistreur à la place de `_load_context_series` →
  `(tf, interval, window_start, start, end)` identiques pour 4 h / 1 d / 1 w, `_warmup_needs` = `required_by_tf` ;
  5 m chargé par `_load_candles` sur `[start, end]` ; chargeurs du script = chargeurs du moteur (mêmes appels).
- **Épinglés au comportement** (table B) : sonde sur `_handle_ohlc` — instance neuve, analyzer bouchon, 6 × 6 × 3
  combinaisons d'entrées (régime 1 w, régime 1 d, ATR `None` / 0 / 0,5), zéro `logger.error` exigé ; un TF décide
  s'il existe une combinaison où le faire varier change `(_paused, _grid_initialized, niveaux)`. Treize jeux de
  paramètres, dont les témoins G = 13 / b = 0 (C1), b = 0,1 et b = 0,16 (C2, C6), G = 1 (C6) et la chaîne `"false"`
  (C2). Chaque cas : `class_of` = classe attendue, TF lus = {1d, 1w, 4h}, TF qui décident = `decision_tfs`.
- **Attendus du texte** : fenêtre et T (§ A.3), besoins (brief, § A.8, `backtest.py:305`), 29 / 2020-08-17 /
  2021-07-26 (§ A.8), historique `<= start` (§ A.4 l.287-289), format `fail(tf: loaded/required)`.
- **Rouge-avant** : 17 mutants temporaires du script, **tous rouges**, fichier restauré — fenêtre 1 w 399 j,
  `bias_live = bias_1d ≠ 0`, `class_of` par forme fermée, D2 sur toutes les séries, historique `< start`, contrôle SOL
  neutralisé, `exchange` bybit, fenêtre 5 m déplacée, 0 du 5 m retiré, rows dérivées sans intervalle / sans paire,
  C2 qui lirait le 1 d, table A altérée, alembic sans tête attendue, `ready_at` sur l'historique, libellé sans gap,
  `sufficient` non recoupé. **Défaut trouvé par moi-même** : au premier passage, le mutant « sans l'intervalle »
  survivait — mes témoins partageaient une estampille que l'ensemble absorbait ; témoin corrigé, mutant « sans la
  paire » ajouté.
- `ruff check` / `ruff format --check` verts ; `MYPYPATH=src:scripts:scripts/audit mypy --follow-imports=silent
  scripts/audit/warmup_at.py` vert (strict ; la CI ne passe pas mypy sur `scripts/audit`).

### 9.2 Essai à sec

`main` contre une base injoignable : code 2, aucun JSON ; sur un script non committé : code 2 (`uncommitted_tree`).
_(Au premier essai, j'ai lu `exit=0` : c'était le code du `tail` de mon pipe — l'incident qui a fixé la règle
`PIPESTATUS` du pilote.)_

### 9.3 Suite complète locale — occurrence d'instabilité tunnel

`24 failed, 2938 passed, 6 skipped in 1482.41s` (11:00:12 → 11:24:56Z, arbre = contenu de `c38d718`). Les 24 échecs
sont **tous** `tests/test_scripts/test_run_p6_determinism.py::test_determinism_parallel_vs_serial_full[combo0…23]`.
Signature : combo0, dernière activité à 11:22:35Z (`grid_terminal_liquidation`), puis à **11:23:48Z**
`job_failed … asyncpg.exceptions.ConnectionDoesNotExistError: connection was closed in the middle of operation` dans
le passage parallèle (`:218`) ; combo1-23, en 70 ms à partir de 11:23:48.28Z, `database_connection_failed …
[Errno 61] Connect call failed ('127.0.0.1', 5433)` dès le passage série (`:210`). Le port répondait de nouveau
ensuite. Les trois tests de la dette tunnel nommés par Bruno (`test_grid_atr_v4_backward_compat_hash[binance|bybit]`,
`test_c2_replay_fidelity_db`) sont **verts**.

**Consignation (Bruno)** : occurrence d'**instabilité du tunnel** (coupure en cours de run), **distincte** du hash
divergent 2/2844 du 24/09 — les deux ne sont pas fusionnés dans la dette. Brut hors git (règle de Bruno : un
fichier de 26 Mo resterait dans l'historique de chaque clone) : `~/archive/sol_d2_20260925/pytest_full_20260925_local.log.gz`
sur le serveur, sha256 du non-compressé `7792be0a16b37b4e62208dc49ffe48374245c8527118d210dd391831befa6e90` dans le
`.sha256` voisin, vérifié après décompression. Extrait dans le dépôt : `evidence/pytest_full_20260925_local.extract.txt`
(résumé final, les 24 échecs tronqués à leur ligne d'erreur réseau, estampilles 11:23:40-50Z), produit par
`evidence/extract_pytest_log.py`.

### 9.4 Les 24 `_full` sur le serveur — condition du merge

Même SHA (`c38d718`), même session tmux, lancés par le pilote après le second `alembic current` (décision Bruno :
`warmup_at` d'abord ; les `_full` conditionnent le **merge**, pas le commit ; les 24 tournent même après un échec).
Fenêtre **11:39:19 → 12:51:10Z (71 min 51 s)**, **`full=0`** : les 24 JUnit portent `tests=1 failures=0 errors=0
skipped=0` (`server/full/combo0.xml` … `combo23.xml`), codes par combo dans `server/status.txt`. Commande par combo :
`nice -n 5 poetry run pytest -p no:cacheprovider -q --durations=0 --junitxml=comboN.xml
"tests/test_scripts/test_run_p6_determinism.py::test_determinism_parallel_vs_serial_full[comboN]"`.

Durées d'appel par combo (s) : 241.76, 247.67, 196.65, 56.12, 54.61, 43.22, 57.90, 56.61, 46.38, 50.26, 49.22, 39.61,
52.93, 53.01, 41.96, 341.35, 337.88, 255.12, 312.94, 313.84, 237.41, 412.52, 417.57, 315.05 — profil du 24/09
(`results/reconstruction_1w_2022_2025/determinism_server/README.md`).

**Lecture pour la dette tunnel** : sur le serveur, base locale, les 24 passent ; en local, les 24 sont tombés sur une
coupure du tunnel (§ 9.3). Les échecs locaux du 25/09 relèvent de l'**instabilité du tunnel**, pas du déterminisme ;
cette occurrence ne dit rien du hash divergent 2/2844 du 24/09, qui reste ouvert et distinct.

Journaux : les sorties serveur font 244 Ko en tout (`combo*.log` < 400 o chacun sur un succès) — versionnées telles
quelles sous `server/`, la règle « extrait dans le dépôt, brut archivé » étant faite pour les journaux lourds ; le
brut est **aussi** archivé : `~/archive/sol_d2_20260925/sol_d2_server_runs_20260925.tgz` (sorties, tentative nulle,
pilote ; 88 entrées ; sha256 `03ab36f863ece9cad40f24311daef4d9dba34dffdabceea9f0629a58d8bf9ebe` dans le `.sha256`
voisin).

## 10. Hors périmètre, noté

- `git_provenance` est dupliquée (12 lignes) entre `reconstruct_1w.py` et `warmup_at.py` : celle de
  `reconstruct_1w` hache son propre chemin. **À factoriser dans `scripts/audit/_common.py` au prochain script
  d'audit** ; pas de dette numérotée (décision Bruno).
- `default_strategy` instancie la stratégie avec des settings minimaux (`trading.pair`,
  `default_order_amount_eur`) ; le second n'est passé que parce que `__init__` le lit — il ne pèse sur aucune
  mesure. Un attribut de plus lu par `__init__` ferait lever l'instanciation et tomber les tests : voulu.
- Le moteur tourne aux défauts de classe pour cette stratégie (décision B.2a : les clés YAML `grid_atr_*` ne
  matchent pas son nom, `scripts/backtest.py:2372`, `:2379-2382`). Non traité ici.
- La classmethod `decision_timeframes`, l'univers de candidats, les dettes 21 / 24 / tunnel : hors périmètre (brief).

## 11. Fichiers de ce dossier

| Fichier | Contenu |
|---|---|
| `report.md` | ce rapport |
| `warmup_2021-03-01.json` | l'artefact de `warmup_at.py` au `c38d718` (sha256 `566beeb4…d35d`) — source de tout chiffre de mesure |
| `server/run_sol_d2.sh` | le pilote (sha256 `300fb2f1…191e`) |
| `server/status.txt` | un code par étape : garde, alembic avant, `warmup_at`, alembic après, `combo0…23`, `full`, bornes |
| `server/run.log`, `server/warmup_at.log` | journal du pilote, sortie de `warmup_at` (contrôles, `d2_summary`, sha256 du JSON) |
| `server/alembic_before.txt`, `server/alembic_after.txt` | `alembic current` : `c3bd1e7a0001 (head)` |
| `server/full/combo0…23.{log,xml}` | sortie pytest et JUnit de chaque `_full` |
| `server/launch1_poetry_absent/status.txt` | la tentative nulle de 11:37:31 (toutes étapes en 127) |
| `evidence/pytest_full_20260925_local.extract.txt` | extrait de la suite locale (§ 9.3) ; brut archivé sur le serveur |
| `evidence/extract_pytest_log.py` | l'extracteur (`python extract_pytest_log.py <brut> 2026-09-25T11:23:40Z 2026-09-25T11:23:50Z`) |
