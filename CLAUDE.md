# CLAUDE.md — Routeur pour agents

> Ce fichier dit **où lire**. Le détail vit dans `skills/` et `docs/`, chargés à la demande.
> État du projet → `PROJECT_CONTEXT.md` · Où est quoi dans le code → `docs/CODE_MAP.md` · Phases → `ROADMAP.md`.

## Le projet en deux phrases

Bot de trading spot automatisé multi-pair (BTC/ETH/SOL contre USDC) sur **Bybit EU**, 8 stratégies
orchestrées par un router avec risk management centralisé, déployé sur Hetzner (collector Bybit actif,
trader masqué). **B4 est close (15 sept, tag `v2.8.0-b4-3-campaign`) : zéro sélection sous les critères codés — et
l'audit red-team du 16/09 a invalidé l'instrument de mesure (addendum B4). Instrument réparé : C1 (métriques,
`v2.9.0-c1-metrics`) et C2 (replay, `v2.10.0-c2-replay`) mergés ; rejeu grid clos `inconclusif` (20/09). **C3a mergée
(23/09, `v2.11.0-c3a-protocole`)** : outillage complet, artefact du rejeu **refusé à l'entrée**. **Protocole amendé en
v2.1 (23/09, `docs/amendements_c3_v2.1.md`, sha256 `9300f4e5…4129`)** sur `feat/c3-amendements-v2.1`, merge sous
décision humaine. Phase suivante : C3b (producteur conforme ; mesure SOL/D2 et modes lisant le 1 w avant le manifeste de la première
campagne) ; aucune sélection, rien à trader ; R&D sur le papier
(`docs/CONTRAINTES_POST_B4.md`), tout run inscrit à `docs/RESEARCH_LOG.md`, aucune sélection hors
`docs/protocole_c3.md`.** Les backtests tournent sur les 8.7M rows Binance
end-stampées en DB avec le modèle de fees Bybit (maker 0.10 % / taker 0.25 %) et les coûts par paire mesurés (GATE B).

## Routage : type de tâche → fichier à lire

| Tâche | Lire |
|---|---|
| DB : connexion, query, migration, backup/restore TimescaleDB | `skills/database.md` |
| Backtest (unitaire, P6, P7 grid search, métriques, fees) | `skills/backtest.md` |
| Nouvelle stratégie ou modification d'une stratégie | `skills/new_strategy.md` |
| Risk management (sizing, SL ATR, types d'ordres) | `skills/risk_management.md` |
| Serveur Hetzner : SSH, systemd, tmux, réactivation | `skills/deployment.md` |
| Connecteur / API Bybit EU (B1–B3) | `skills/bybit.md` |
| Données historiques Binance (base de backtest) | `skills/binance_import.md` |
| Bug, tunnel SSH, migration qui hang | `skills/troubleshooting.md` |
| Flux d'un trade, multi-pair, conventions de code | `docs/architecture.md` |
| Localiser un module / une fonction | `docs/CODE_MAP.md` |
| Résultats de backtests (quoi est où, verdicts) | `results/INDEX.md` |
| **Nouvelle idée de stratégie** (filtre d'entrée, ticket § 6 sur le papier avant tout code) | `docs/CONTRAINTES_POST_B4.md` |
| **Audit red-team B4 / portée des conclusions** | `results/red_team_b4_20260916/RAPPORT_RED_TEAM_B4.md` (+ addendum en tête de `results/B4_bybit_backtest_report.md`) |
| **Comment une configuration est sélectionnée** (protocole v2.1 — spécification de TOUTE sélection future) | `docs/protocole_c3.md` (+ `docs/amendements_c3_v2.1.md`) |
| **Critère d'arrêt** (clôture de famille, alpha-stop projet, kill-switch live) | `docs/CONTRAINTES_POST_B4.md` § 10 |
| **Brief du chantier C3a** (périmètre, gates, décisions figées) | `agent/c3a_protocole_chronologique_v2.md` |
| **Outillage C3** (chaîne `c3_*.py`, codes de sortie, règles appliquées et leur section d'origine v2.1, seul run réel) | `skills/backtest.md` § « Validation C3 » |
| **Rapport de session C3a** (revues Fin, conventions, exigences C3b accumulées) | `agent/rapport_session_c3a_20260922.md` |
| Briefs de chantier en cours | `agent/` |
| **Journal des essais** (obligatoire avant tout run) | `docs/RESEARCH_LOG.md` |

> **Protocole C3 v2.1 (amendé le 23 sept 2026 — `docs/amendements_c3_v2.1.md`, sha256
> `9300f4e53bfd36633df6524c2d7ad168a732739ca3dd1765c024cc8a3ccd4129`).** `docs/protocole_c3.md` spécifie **toute**
> sélection future et ne se modifie que par amendement daté (v2.0 gelée au `d931293` : historique C3a). **Aucune
> sélection ne se fait hors de ce document.** v2.1 : rejeu complet du tirage § F.2 par la chaîne (égalité au bit,
> environnement `{python, numpy, machine, libc}`), E2 conjonctive, c3 non normalisée → `inconclusif
> (R1_NOT_NORMALISED)`, bloc de liquidation contradictoire → violation, évaluation réelle admise avec `flat_start_proof`,
> `invocation.single_call` et `first_fill_at` (§ L.1). L'outillage `scripts/audit/c3_*.py` (7 modules, 932 tests)
> est décrit dans `skills/backtest.md` § « Validation C3 ». Sa seule sortie réelle reste un refus (livrable C3a,
> manifeste v2.0). **Aucune campagne existante ne peut traverser la chaîne** sans un producteur conforme (C3b), dont
> v2.1 fixe le contrat ; `validé` / `réfuté` deviennent atteignables sur données réelles par ce chemin et par aucun
> autre. Critère d'arrêt pré-enregistré : `docs/CONTRAINTES_POST_B4.md` § 10.

## Règles d'or (absolues)

1. **Lire le code existant** (et le skill concerné) avant d'écrire.
2. **Decimal** pour tous les prix et montants, jamais float. **UTC** pour tous les timestamps.
3. **structlog** pour les logs (jamais print / logging stdlib). Imports absolus `from krakenbot...`.
4. **Filtre exchange via `settings.exchange_name`**, jamais de littéral `'binance'` / `'bybit'` dans
   le code de production. Seuls les backtests lisent explicitement `exchange='binance'`.
5. **Batcher les inserts SQL** (1000 rows par batch, jamais > 5000 par execute).
6. **Ne jamais réimporter** des données déjà en DB : vérifier d'abord (`skills/database.md`).
7. **Paper avant live**, 3+ ans de backtest avant paper. **Aucun paper Bybit sans un candidat validé sous le
   protocole C3** (`docs/protocole_c3.md`, sélection chronologique, fees Bybit) — B4 (fees Bybit) reste le
   prérequis d'**instrument**, il n'est plus le critère de sélection.
8. **Fichiers protégés** : `MultiStrategyRouter`, `GeminiGlobalRiskManager`, `ExecutionEngine` —
   pas de modification sans raison explicite et review humain. Ne jamais bypasser le `GlobalRiskManager`.
9. **Jamais de commit** de `.env`, credentials ou API keys.
10. **Jamais de merge sur `main`** sans passer par `dev`. `pytest` + `ruff` verts avant tout commit.
11. **Pas de migration Alembic lourde via le tunnel SSH** : sur le serveur, services stoppés.

## Commandes essentielles

```bash
poetry run pytest -q                                        # tests (avant tout commit)
poetry run ruff check . --fix && poetry run ruff format .   # lint + format
poetry run python -m krakenbot                              # bot (paper) — connecteur Bybit : B1
poetry run python -m krakenbot.collector                    # collector — Bybit WS : B2
poetry run python scripts/backtest.py --strategy grok_supertrend_4h --pair BTC/USDC \
    --exchange binance --fees bybit --days 1095 --capital 1000   # backtest unitaire (--fees obligatoire)
poetry run python scripts/run_p6_backtests.py --fees bybit --workers 8   # 24 combos P6 (resume auto, --serial, --force)
poetry run python scripts/run_p7_grid_search.py --phase 1 --fees bybit --workers 8   # P7 : --phase 1 | 2 | report
poetry run python scripts/dashboard.py                      # dashboard Dash
```

`--exchange binance` désigne la **source de données** (8.7M rows Binance), pas l'exchange cible.
`--fees {bybit,binance,kraken}` est **obligatoire** (B4.2) et désigne le **modèle de fees** appliqué par les
moteurs (maker/taker/spread/slippage), indépendant de la source de données ; `binance` = 0.075 % flat des
résultats P6/P7 historiques, `bybit` = cible de production. Détails : `skills/backtest.md`.

## Conventions git

- Branche de travail `feat/<phase>-<sujet>` depuis `dev`, PR vers `dev`.
- Commits atomiques, préfixes `feat|fix|refactor|docs|chore|test(scope)`.
- Régénérer `docs/CODE_MAP.md` à chaque merge sur `dev` (méthode dans son en-tête).
- Pendant qu'un chantier agent est actif, toute intervention humaine passe par un worktree séparé
  (`git worktree add ~/wt-human dev`) — jamais de checkout/commit humain dans le tree d'un agent.
- Tout agent : assert `git branch --show-current == <branche du chantier>` avant chaque commit.
- Un bloc GO contenant des écritures git part vers exactement une session, nommée.

## Règles agent — tests de contrat et vérifications (acquises en C3a, 22/09)

1. **Tout test de contrat naît adverse** : constaté **rouge** contre le code du tip précédent avant le correctif ;
   pour une tranche neuve, écrit avec son cas adverse et constaté rouge contre un état qui ne l'implémente pas. Un
   test vert dès l'écriture ne prouve rien — cinq défauts ont tenu dans 92 tests verts-avant (revue Fin C3a).
2. **Le témoin sain est lui-même conforme au contrat** : la fixture « saine » d'un test adverse satisfait toutes les
   clauses qu'elle exerce, sinon le test compare deux non-conformités.
3. **L'attendu d'un test se dérive de la table ou du texte, appui cité** (section, ligne) — jamais de
   l'implémentation. Rouge-avant prouve qu'un test mord, pas que son attendu est juste : un paramétré recopié du
   code est un verrou posé sur le défaut. Les tables du texte sont recopiées dans le test et **épinglées** aux
   constantes du code par un test d'égalité, jamais l'inverse.
4. **`set -o pipefail` sur toute vérification pipée** (`pytest … | tail`, `… | tee`) : sans lui le code de sortie est
   celui du dernier filtre, et un rouge passe (incident C3a, commit 4, amendé en `bd81b87`).
5. **Précédence par ordre de constat** : après une violation constatée, la violation prime (diagnostic, code 1) sur
   tout refus ou issue non définie survenant ensuite — **sauf lecture inachevable** (preuve obligatoire absente ou mal
   typée constatée après : code 2, rien publié, violations sur stderr). Un contrat refusé **avant toute lecture** reste
   un refus 2. Section d'origine : protocole § I.1 v2.1 (ordre de constat) ; comportement de l'outillage :
   `skills/backtest.md` § « Validation C3 ».
