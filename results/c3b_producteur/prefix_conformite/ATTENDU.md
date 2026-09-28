# C3b lot 3 — attendu de conformité, déclaré avant le lancement

**Fenêtre d'instrument, aucune lecture économique.** Ce run vérifie que le producteur fabrique des entrées que la
chaîne C3 accepte. Il ne dit rien de la famille grid. Aucun nombre de `c3_benchmark` ni de `c3_select` n'est lu,
commenté ou reporté comme résultat.

Écrit et committé avant le lancement, avec la ligne 15 de `docs/RESEARCH_LOG.md` et le manifeste. Le run serveur se
fait au SHA de ce commit. Brief `agent/AGENT_C3B_PRODUCTEUR.md` § « Lot 3 » (critère de fin) ; plan du lot validé le
2026-09-27.

## Ce qui est lancé

- **Manifeste** : `results/c3b_producteur/prefix_conformite/manifest.json` (sha256 au rapport).
  - Fenêtre `2020-01-06T00:00Z → 2020-12-28T00:00Z`, `F = 0,70`, donc `T = 2020-09-11T21:36:00Z` (0,70 × 357 j =
    249,9 j), préfixe `train`.
  - Base : `exchange = binance`, exécution 5 min, séries 4 h / 1 j / 1 w.
  - Fees `bybit` (taker 0,25 %). Coûts par paire : ceux de `config/pair_costs_b4.json` pour la paire de déploiement
    USDC (§ A.6).
  - `min_order_usdc 5.0` ; provenance `unknown`, variante racine `c3b-lot3-conformite-prefixe-2020`.
- **Univers : 12 candidats** `grok_grid_atr_adaptive_v4`, 4 paramétrages × `BTC/USDT`, `ETH/USDT`, `SOL/USDT`. Il y a
  un paramétrage par ensemble de `decision_timeframes` (rapport SOL/D2 § 3.1) ; chacun est tiré des cas-sondes de
  `test_warmup_at.py` et porte sa surcharge `decision_timeframes` :

  | Classe | Paramètres | Séries de décision |
  |---|---|---|
  | C1 | `{}` | `1d, 1w, 4h` |
  | C2 | `{"bear_protection_mode": "1w_only", "bias_1d": 0}` | `1w, 4h` |
  | C5 | `{"bear_protection_mode": "none"}` | `1d, 4h` |
  | C6 | `{"bear_protection_mode": "none", "bias_1d": 0}` | `4h` |

- **Serveur** : dans `~/runs/c3b_prefix/`, le producteur tourne deux fois — run1 `--workers 4`, puis run2
  `--workers 1`. Viennent ensuite, sur la sortie de run1, `c3_anchor` (registre neuf), `c3_entry`, `c3_benchmark` et
  `c3_select`. `alembic current` est relevé avant et après.

## Attendu, item par item, avec sa dérivation

1. **Producteur : code 0 aux deux exécutions.**
   - `observations.json`, `candles.json` et `coverage.json` ont le **même sha256** entre run1 et run2. Comme run1
     utilise 4 workers et run2 un seul, l'égalité prouve aussi que la sortie ne dépend pas de l'ordre d'exécution.
   - 12 entrées dans `observations.json`.
   - `T = 2020-09-11T21:36:00Z` dans `prefix_run.json`.
   - **0** estampille `ohlc_derived` dans `(début, T]` : les 24 rows dérivées datent de 2022 et 2025
     (`RESEARCH_LOG` entrée 13).
2. **`c3_anchor` : code 0**, avec le même `T` recalculé. Validé en local sur le manifeste avant le commit.
3. **`c3_entry` : code 0.** I-A.1 à I-A.8 sont `ok`, et **aucune clause n'est non assertable** : `exec_interval` est
   porté par chaque entrée et la couverture est fournie et évaluée. I-A.5 note `unknown`.
   - **D2 échoue à I-A.8 sur les 4 candidats SOL**, sur toutes leurs séries de décision : C1 `[1d, 1w, 4h]`, C2
     `[1w, 4h]`, C5 `[1d, 4h]`, C6 `[4h]`, chaque fois `loaded 0`. La raison : SOL n'a aucune donnée avant le
     2020-08-11 (première 5 min le `2020-08-11T06:05Z`, inventaire du 23/09). La portée est le candidat (§ I.1 l.4),
     et la chaîne continue.
   - **BTC et ETH sont amorcés sur leurs 8 candidats.**
     - 1 w : 52 estampilles `≤ 2020-01-06` depuis la première, le `2019-01-14`, pour 50 exigées
       (`backtest.py:420-425`).
     - Aucun trou 1 j ni 1 w en 2019.
     - Aucun trou 4 h dans les 15 jours d'amorçage : les trous 4 h de BTC et d'ETH (deux bougies le 2019-05-15,
       une le 2020-02-19, `results/data_inventory_usdt_2019_20260923/inventory.md`) sont hors de
       `[2019-12-22, 2020-01-06]`.
4. **`c3_benchmark` : code 0.** SOL est `E_NO_BENCHMARK`, faute de bougie 5 min au `2020-01-06T00:05Z` (première
   estampille d'exécution strictement après le début, § C.3). L'issue de BTC et d'ETH n'est **pas déclarée**.
5. **`c3_select` : code 0**, avec une sélection **descriptive** (`P_PROVENANCE`, § I.1 l.7, provenance `unknown`).
   - Pour les candidats SOL, la première porte en échec est **D1** et la paire est `DESCRIPTIF`. En 5 min, SOL
     couvre 31 jours sur les 249 du préfixe, sous les 97 %.
   - L'issue de BTC et d'ETH (candidat retenu, abstention, raison) n'est **ni déclarée ni lue**.
6. **`alembic current`** est identique avant et après : `c3bd1e7a0001 (head)`. Le producteur lit en lecture seule
   assertée par Postgres.
7. **Toutes les lectures du producteur sont bornées à `≤ T = 2020-09-11T21:36Z`.** L'amorçage le plus ancien remonte
   à `début − 400 j`. **Aucune donnée de la fenêtre de campagne (`2021-03-01 → 2026-06-29`) n'est lue.**

## Règles en cas d'écart

- Tout écart à un item est un **constat** écrit au rapport. Aucune relance n'a lieu avant son diagnostic.
- Un correctif du producteur est un commit de plus, et il repasse par Bruno avant tout nouveau lancement.
- Seule une panne du pilote lui-même (par exemple un code 127, `poetry` absent du PATH) se relance après correction
  du pilote.
- Chaque lancement est consigné, avec son `status.txt`.
