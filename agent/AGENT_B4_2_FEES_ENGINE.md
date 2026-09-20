# AGENT B4.2 — Modèle de fees maker/taker du moteur de backtest

> Deuxième brief de B4 (après B4.1, re-stamp Binance, tag `v2.6.0-b4-1-binance-restamp`).
> Mode : **plan mode** — audit read-only du code, puis plan complet soumis au GATE 1
> avant toute modification. Travail **local uniquement** (DB en lecture via tunnel pour
> les runs de référence) : pas de serveur, pas d'écriture DB, réversible par git.

---

## 0. À lire avant tout (dans cet ordre)

1. `CLAUDE.md` (routeur + règles d'or)
2. `PROJECT_CONTEXT.md` — § 5 (fees Bybit, CRITIQUE), § 9 dettes **2** et **9**
3. `skills/backtest.md`
4. `results/B4_1_timestamp_restamp_report.md` — invariant 6 (backtest de référence
   post-re-stamp = baseline de régression de ce brief)
5. `docs/CODE_MAP.md` (entrée `backtest.py` + points d'attention 5 et 9)

Code à auditer (les numéros de ligne datent du tag B3 — les revérifier sur `dev`) :
- `scripts/backtest.py` — sélection des fees `BacktestEngine.__init__` (~:227-230) et
  `GridBacktester.__init__` (~:1665-1668) ; sites maker/taker du moteur signal
  (~:559-565, ~:840-846) ; les 6 sites `self.fees.maker` du GridBacktester
  (~:1882, :1925, :2016, :2064, :2313, :2347) ; rollover dans `_execute_short_signal`
  (~:837-962) ; chemin `is_multi` ; `_check_directional_pause` ;
  `load_dotenv` à l'import (:18-22)
- `src/krakenbot/config/settings.py` — `ExchangeFees` (:556), `bybit_defaults` (:601)
- Appelants à plomber : `scripts/run_p6_backtests.py`, `scripts/run_p7_grid_search.py`,
  `scripts/run_p6_walkforward.py`, `scripts/dashboard.py` (`run_backtest_in_thread`)

## 1. Contexte

- Les deux moteurs choisissent les fees sur le paramètre `exchange`, qui désigne la
  **source de données** : `exchange == "binance"` → `binance_defaults(use_bnb=True)`
  (maker = taker = 0.075 %), sinon `ExchangeFees()` nu (= Kraken). Conséquence : il est
  aujourd'hui **impossible** de backtester « données Binance, fees Bybit », qui est la
  doctrine du projet (décision permanente n° 2 de `ROADMAP.md`).
- Fees Bybit EU vérifiées compte : **maker 0.10 % / taker 0.25 %**. Les sorties
  SL / trailing / timeout / crash sont des ordres MARKET = taker. Le moteur signal
  distingue déjà maker/taker (limit fill → maker, sinon taker + spread + slippage) ;
  le **GridBacktester facture maker sur ses 6 sites de fill, sorties comprises**.
- Baseline de régression (B4.1, invariant 6, données re-stampées, fees flat Binance) :
  `grok_supertrend_4h BTC/USDC --days 1095 --capital 1000` →
  **return +2.42 %, Sharpe 0.25, PF 1.56, MaxDD 2.17 %, 46 trades**.

## 2. Objectif

Découpler le **modèle de fees** de la **source de données**, appliquer maker et taker
aux bons sites de fill dans les deux moteurs, et livrer une suite de tests à zéro
échec — sans changer d'un bit le comportement du moteur à modèle de fees identique.

## 3. Hors scope — STRICT

- Aucun re-run P6/P7 (B4.3) : uniquement les runs de référence et de validation listés ici.
- Révision risk management (max positions, daily loss dynamique, plancher) : B4.3.
- Aucune modification des stratégies ni des fichiers protégés
  (`MultiStrategyRouter`, `GeminiGlobalRiskManager`, `ExecutionEngine`).
- Aucune écriture DB, aucun accès serveur, pas de `deploy.yml`.
- Valeurs de spread par paire : la **capacité** est dans ce brief, les **valeurs**
  attendent la mesure nocturne (entrée de B4.3). Défauts globaux inchangés.
- Toute tâche annexe découverte : consignée au rapport, pas faite.

## 4. Étape 0 — Runs de référence AVANT tout changement

Sur `dev` HEAD intact, capturer et versionner (JSON/logs dans `results/`) :
- Le run baseline signal ci-dessus (§ 1) — doit reproduire les chiffres B4.1.
- Un run GridBacktester de référence (config `grok_grid_atr_adaptive_v4` BTC, mêmes
  données, paramètres par défaut), métriques complètes + nombre de fills par type.

Ces sorties sont la cible bit-exacte de l'invariant de régression (§ 7.1). Le
déterminisme est acquis depuis P6.7 — un écart entre deux runs identiques est un
STOP, pas une tolérance.

## 5. Étape 1 — Audit read-only + plan (livrable du GATE 1)

Le plan soumis au GATE 1 contient obligatoirement :

a) **Table de classification des sites de fill**, pour les deux moteurs :
   site (fichier:ligne) → type d'ordre simulé (limit/market) → fee correcte
   (maker/taker) → fee actuellement appliquée → écart. Chaque site du GridBacktester
   est justifié par le mécanisme de la stratégie (les fills de grille sont des LIMIT ;
   les sorties SL/crash sont des MARKET), pas par supposition.
b) **Design du découplage** : paramètre `fee_model` distinct de `exchange` dans les
   deux constructeurs, flag CLI `--fees {bybit,binance,kraken}` **obligatoire**
   (absence → erreur explicite, cohérent avec `exchange_name` ; pas de défaut
   silencieux), mapping vers les factories `ExchangeFees.*_defaults`. Plomberie dans
   les 4 appelants (runners P6/P7, walk-forward, dashboard — le dashboard passe
   explicitement `bybit`).
c) **Spread/slippage surchargeables par paire** : mécanisme simple (dict
   `pair → (spread, slippage)` injectable, défaut = valeurs globales du modèle),
   exposé en CLI ou config. Comportement par défaut strictement inchangé.
d) **Sort du rollover** : il vit dans `_execute_short_signal` (chemin short/margin).
   Vérifier s'il est mort en spot (les stratégies short ont été supprimées en B0.5) :
   preuve d'atteignabilité à l'appui. Mort → suppression avec le chemin ; vivant →
   paramétré dans `ExchangeFees`. Décision au gate, pas d'initiative.
e) **`settings.exchange_fees`** : clarifier la frontière (fees de trading live/paper
   vs fees de backtest sélectionnées par `--fees`) — proposition au gate : câbler ou
   documenter la séparation, pas d'état ambigu.
f) **Chemins morts** : suppression de `is_multi` (dette 9) et
   `_check_directional_pause`, avec preuve de non-atteignabilité.
g) **Fix racine des 4 tests ordre-dépendants** : `load_dotenv()` s'exécute à l'import
   de `backtest.py` (:22) et pollue `os.environ` pour toute la session pytest.
   Node IDs :
   - `tests/test_config/test_settings.py::TestExchangeNameRequired::test_live_mode_requires_keys_of_selected_exchange`
   - `tests/test_config/test_settings.py::TestExchangeNameRequired::test_bybit_credentials_by_role`
   - `tests/test_connectors/test_bybit_rest.py::TestInit::test_live_without_trade_key_raises`
   - `tests/test_strategies/test_grid_atr_v4_backward_compat.py::test_grid_atr_v4_backward_compat_hash`
   Fix visé : plus d'effet de bord à l'import (déplacer `load_dotenv` dans les entry
   points), **après analyse des appelants** — `run_p6_backtests.py`,
   `run_p7_grid_search.py`, `run_p6_walkforward.py` chargent leur propre `.env`,
   vérifier qu'aucun chemin ne dépendait de l'effet de bord de l'import. Traiter
   aussi le `ERROR at teardown` (`ResourceWarning`) sur
   `test_grid_atr_v4_backward_compat_hash` (consigné en B4.1, annexe du rapport).

### ⛔ GATE 1 — STOP
Plan + table de classification + décisions d/e soumis à Bruno. **Aucune modification
de code avant le GO.**

## 6. Étape 2 — Implémentation

Dans l'ordre : fix dotenv (commit isolé, suite verte) → découplage `--fees` +
plomberie appelants → classification maker/taker GridBacktester → capacité spread
par paire → suppressions des chemins morts validées au gate. Tests unitaires pour :
sélection du modèle de fees, erreur en absence de `--fees`, application maker vs
taker par type de site (les deux moteurs), overrides par paire.

## 7. Validation (tous obligatoires)

1. **Régression iso-fees (l'invariant central)** : les runs de l'étape 0, rejoués
   post-refactor avec `--fees binance` (flat BNB), reproduisent **bit-exact** les
   sorties de référence — métriques ET liste des trades. Tout écart = STOP + analyse,
   pas d'arrondi toléré.
2. **Run `--fees bybit`** (mêmes données) : sur le détail des trades, chaque entrée
   limit facturée 0.10 %, chaque sortie market 0.25 % + spread + slippage —
   vérifiable trade par trade dans la sortie. Idem GridBacktester : les fills de
   grille à 0.10 %, les sorties market à 0.25 %.
3. **Absence de `--fees`** → erreur explicite (test dédié), y compris via les runners.
4. **Suite complète : 0 échec, 0 error**, dans un ordre quelconque (la démontrer sur
   au moins deux ordres d'exécution distincts), teardown propre. 6 skips DB tolérés.
5. `ruff check` + `ruff format` propres ; mypy : aucune erreur nouvelle (référence
   B3 : 35 sur `src/`).
6. Les chemins supprimés n'apparaissent plus nulle part (`grep` propre).

## 8. Docs (même branche, après validation)

- `skills/backtest.md` : nouveau flag `--fees`, doctrine maker/taker, overrides par
  paire, exemples de commandes.
- `CLAUDE.md` : commandes essentielles mises à jour (`--exchange binance --fees bybit`).
- `PROJECT_CONTEXT.md` : dettes 2 et 9 → résolues ; § 5 pointe le mécanisme.
- `docs/CODE_MAP.md` : régénéré au merge (méthode de l'en-tête).

## 9. Livrables (critère de fin)

1. `results/B4_2_fees_engine_report.md` — table de classification, décisions de gate,
   preuves de régression iso-fees (diff vide), extraits de trades `--fees bybit`,
   sorties des validations 3-6.
2. Runs de référence versionnés (étape 0) + leurs rejouements post-refactor.
3. Code : découplage `--fees`, classification corrigée, overrides par paire, chemins
   morts supprimés, dotenv fixé — sur `feat/b4-2-fees-engine` depuis `dev`.
4. Suite de tests à zéro échec connu.

## 10. Commits attendus (atomiques)

- `fix(scripts): remove import-time dotenv side effect from backtest`
- `feat(backtest): decouple fee model from data-source exchange (--fees)`
- `fix(backtest): apply taker fees to market exits in GridBacktester`
- `feat(backtest): per-pair spread/slippage overrides`
- `refactor(backtest): remove dead is_multi and short/rollover paths` (selon gate)
- `docs(project): resolve debts 2 and 9, update backtest skill`

PR vers `dev` après STOP final. **Jamais de push sur `main`.**

## 11. Garde-fous absolus

- Régression iso-fees non négociable : à modèle de fees identique, le moteur produit
  des sorties identiques. C'est ce qui sépare « refactor » de « nouveau moteur ».
- Fichiers protégés intouchés ; aucune écriture DB ; `.env`/credentials jamais commités.
- Toute décision d/e prise sans gate, tout écart de régression, tout comportement
  non couvert par le plan validé : **STOP et remonter**.

### ⛔ STOP final
Rapport complet → review humaine avant PR vers `dev`. Clôture de phase standard
(review → merge → CODE_MAP → push vérifié → tag `v2.7.0-b4-2-fees-engine` → zip).
