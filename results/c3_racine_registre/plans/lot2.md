# C3 — Racine du registre (R-4), lot 2 : conformité rejouée, porte par invariance — exécution du plan (GO reçu)

## 0. GO reçu (01/10)

GO du lot 2 donné par Bruno le 2026-10-01, sur le § 7 du plan approuvé (`plans/plan.md`, L1 à L7), après le rapport du
lot 1 (`lot1/README.md`, tip `56c65aaf8d14e6c70a4dcc66f321a83bb785d817`, CI verte en tentative 1). Ce document ne décide
rien de neuf : il dit comment L1-L7 s'exécutent, sur le modèle du lot 2 de l'outillage v2.3
(`results/c3_outillage_v2_3/plans/lot2.md`, troisième rejeu). **Ce qui n'est pas écrit en L1-L7 est marqué « détail
d'exécution » et relu par Bruno au STOP 1.** Le lot n'écrit aucun code ; tunnel jamais ouvert ; aucun registre
persistant, aucun sel réel, `~/c3/` ni touché ni créé, `CAMPAIGN_UNLOCK` jamais créé.

## 1. Constats de lecture

| # | Constat | Effet |
|---|---|---|
| L-K1 | Le lot 1 ne change que `c3_anchor.py` (passthrough de racine) et des tests ; sur les registres neufs de la conformité, la racine ne porte que `variants` : `load_registry` et `register` y rendent exactement ce qu'ils rendaient à `313eb00` | items et codes de l'attendu v2.3 inchangés ; les 23 artefacts restent la liste comparée |
| L-K2 | Le manifeste v2.3 (`24bde67d…565a`) porte déjà le protocole v2.3 et `deferred_evaluation.date` ; seuls `research_log_entry`, `run_scope`, `variant_id` changent (L2) | `manifest_check.sh` réécrit : delta = ces trois chemins réécrits, rien d'ajouté ni de retiré |
| L-K3 | La porte n'est pas rejouée (L5) : les pilotes, scripts et vérificateurs de la porte v2.3 (`run_gate.sh`, `verify_gate.sh`, simulations de porte du dry-run) n'ont pas d'objet ici | non repris ; `pilot_dryrun.sh` et `verify_adverse.sh` réduits à la conformité (détail d'exécution, déclaré) |
| L-K4 | Le 30/09, la conformité v2.3 a archivé sous `~/archive/c3_outillage_v2_3_conf_20260930/` | noms du chantier distincts (L4) |

## 2. Exécution de L1-L7

| # | Ce qui s'exécute |
|---|---|
| L1 | Le run se fait au SHA **S1**, le commit qui porte manifeste, attendu, pilote, vérificateur, scripts et entrée 22 ; code identique au tip du lot 1, prouvé par `interdits_lot2.sh` (diff vide contre `56c65aa` sur le code, les tests, la configuration, les docs gelées) |
| L2 | `conformite/manifest.json` = le manifeste v2.3 avec trois lignes réécrites, mise en forme identique ; `manifest_check.sh` : ajouté ∅, retiré ∅, réécrit exactement `{research_log_entry, run_scope, variant_id}` ; `protocol_sha256` = v2.3 ; écart de la date différée = 365 j ; `c3_anchor` local (hors dépôt) code 0, `T = 2020-09-11T21:36:00+00:00` |
| L3 | `conformite/attendu.md` : items 1-10 et leurs codes repris de l'attendu v2.3 ; § « Ce que ce chantier change » |
| L4 | `variant_id` `c3-racine-registre-conformite-2020` ; `--campaign RACINE_REGISTRE_CONF` (étiquette d'instrument) ; `--now 2026-10-01T00:00:00+00:00` (date de S1) ; runs `~/runs/c3_racine_registre/conf/{repo,out}` ; archive `~/archive/c3_racine_registre_conf_<AAAAMMJJ>/` ; tmux `c3-racine-registre-conf-<AAAAMMJJ>` |
| L5 | `tests/invariance_porte.sh` : (a) fichiers changés depuis `c62acb4` ⊆ liste déclarée ; (b) diff vide contre `313eb00` et `c62acb4` sur `src/ config/ pyproject.toml poetry.lock .github/`, `scripts/` hors `c3_anchor.py`, `tests/` hors les trois fichiers C3 ; (c) `c3_anchor` importé seulement par `c3_verdict` et des tests C3 ; (d) **détail d'exécution** : modules du dépôt chargés à la collecte du module `_full` (`pytest --collect-only` avec un greffon jetable hors du dépôt), aucun `c3_*`. Lancé à S1 et au tip final |
| L6 | Entrée 22 du journal à S1, avant lancement, insérée comme l'entrée 21 (avant « Essais à venir ») ; scripts repris du lot 2 v2.3 par substitutions comptées (`reprise_lot2.out`) ; `events.sh`, `pilot_dryrun.sh` (4 simulations de conformité), `verify_adverse.sh` (témoin + 22 cas) prouvés avant S1 ; **STOP 1** ; puis preflight → launch → wait → fetch → verify → archive → postflight |
| L7 | `report.md` au commit de clôture, avec l'issue de l'entrée 22 et un ajout aux « Essais à venir » ; STOP 2, merge par Bruno |

**Ce qui remonte** (comme v2.3, D3) : codes et booléens ; aucun sha d'artefact du chemin sélection. Règle 64 hex du lot
2 : table d'Adoption ∪ sha256 d'un fichier du chantier (`results/c3_racine_registre/**`, `skills/registry.md`, le brief)
∪ sha256 du manifeste v2.3 comparé ∪ sha d'archive consigné dans un `*.tgz.sha256` du chantier.

**Écart à l'attendu** (comme v2.3, D7) : STOP, répertoire serveur laissé en place, seuls `status.txt`,
`pilot_exit.txt` et les deux `alembic` remontent ; aucune lecture de diagnostic sans l'accord de Bruno.

## 3. Commits (branche assertée, message par `-F`, `interdits_lot2.sh <étiquette>` avant chacun)

| Commit | Contenu | Poussé |
|---|---|---|
| G0 (geste) | `tunnel.sh state` → fermé attendu | — |
| **C0** `docs(results)` | ce document ; `tests/interdits_lot2.sh`, `interdits_lot2_adverse.sh` et leurs sorties | non |
| **S1** `docs(research)` — **SHA du run** | manifeste, attendu, pilote, `verify_attendu.py`, scripts de procédure et de preuve et leurs sorties d'avant lancement, `invariance_porte_S1.out`, entrée 22 | oui, CI lue |
| **STOP 1** | relecture de Bruno au SHA S1 complet → **GO de lancement nommant S1** | |
| **S2** `docs(results)` | preuves de la conformité, archive, postflight, invariance au tip, `report.md`, issue de l'entrée 22 | oui, CI lue |
| **S3** `docs(results)` | `ci_status_S2.out` | oui ; CI de S3 au message |
| **STOP 2** | rapport final, relecture de Bruno, **merge par Bruno** | |

## 4. Règle d'arrêt

Tout code hors attendu, `chain.verified` faux, une violation, trois exécutions non identiques, un item en écart, un
besoin de code, une garde du preflight en échec, un écart d'invariance de la porte → STOP, constat versionné, rien de
relancé « pour voir ». Seule une panne du pilote lui-même (127, chemin) se relance, après correction par un commit
repassé par Bruno.
