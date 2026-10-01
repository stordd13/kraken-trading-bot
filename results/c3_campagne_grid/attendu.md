# Première campagne C3 comptée — famille `grid-atr-v4` : attendu déclaré avant le lancement

**Run compté, un seul lancement, aucun retry, aucun écart arbitré.** Ce run fait traverser pour la première fois à la
chaîne C3 la fenêtre de campagne, sous le protocole v2.3 et le manifeste gelé par Bruno le 2026-10-01. L'issue est
**déclarée ici avant le run** et **ne remonte que par la liste close** du § 6 : l'issue et la raison telles que la chaîne
§ L.2 les écrit, le statut compté dérivé de ces deux valeurs, des codes et des booléens. Rien d'autre du chemin
sélection n'est lu, commenté ou reporté : ni identité retenue, ni métrique, ni λ, ni porte, ni motif.

Cet attendu est committé avant le lancement, avec l'entrée 23 de `docs/RESEARCH_LOG.md`, au commit **S1**, qui est le
SHA du run. **Bruno le relit au SHA S1 complet, avec l'entrée 23 et le pilote (STOP 1)**, dont les deux littéraux
`--registry` comparés au caractère près (§ 3). Puis **Bruno crée `CAMPAIGN_UNLOCK`** et rejoue la vérification § 1 du
runbook du registre ; puis son GO de lancement nomme S1. **Rien ne tourne sur le serveur avant ce GO.**

- **Brief** : `agent/AGENT_C3_CAMPAGNE_GRID.md` (non suivi par décision, brief § 3). **Plan** : `plans/plan.md` (GO du
  2026-10-01 : décisions Q1-Q3, amendements A1-A5).
- **Modèle** : l'attendu de la conformité R-4 (`results/c3_racine_registre/conformite/attendu.md`), réécrit pour un run
  unique sur registre persistant.
- **Protocole** v2.3, sha256 `d030ab239de317f6cba89877d682338fa2001d2a63d231f1a86c519fe87a79e6`, inchangé.
- **Code** identique à `dev` @ `235461e8a4beac42ecb57cc75ab13e8d88dfac14` : diff vide sur `src/ scripts/ tests/ config/
  pyproject.toml poetry.lock .github skills/ agent/` et sur le protocole, les amendements et les contraintes
  (`tests/interdits_S1.out`). C'est le code de la conformité R-4 tenue au serveur le 01/10 (entrée 22, 10/10).

## 1. Fenêtre

- **Période** : `2021-03-01T00:00Z → 2026-06-29T00:00Z` (1 946 j), `F = 0,70`.
- **Ancrage** : `T = 2024-11-22T04:48:00Z` (0,70 × 1 946 j = 1 362,2 j de préfixe ; 583,8 j d'évaluation), recalculé
  par `c3_anchor`, jamais passé en paramètre ; vérifié en local sur le manifeste (`tests/manifest_check.out`).
- **Provenance** : `contaminated` — qualification du rapport gelé du rejeu (`results/rejeu_grid_report.md` § 10.3 :
  planchers du balayage re-choisis à la lumière de la campagne Binance, renoncement non corrigé).
- **Date de l'évaluation différée** : `2027-06-29T00:00:00+00:00`, 365,000000 j après la fin, déclarée parce que v2.3
  l'exige, **inerte ici** : la voie du § 10.1 ne s'ouvre que sur `inconclusif (F_CANNOT_SEPARATE)`, inatteignable sous
  `P_PROVENANCE` (§ 7). Aucun module ne lit de donnée à cette date.
- **Garde-fou 6** : levé par `CAMPAIGN_UNLOCK`, créé par Bruno (§ 4).

## 2. Manifeste

**Fichier** : `results/c3_campagne_grid/manifest.json`, sha256
`d422076b09292d8aeb2a6ae3f39b9c37325f23e954c05c6c83a8979255325041`, **copie à l'octet** du brouillon gelé
(`cmp`, `tests/manifest_check.out`) ; asserté par la garde du pilote.

Contenu, vérifié par `tests/manifest_check.sh` (`rc=0`) sans aucune lecture de données : protocole v2.3 ; famille
`grid-atr-v4` ; **96 candidats distincts** = `grok_grid_atr_adaptive_v4` × {`BTC/USDT`, `SOL/USDT`} ×
`min_spacing_pct` {0,015 ; 0,02 ; 0,025 ; 0,03} × `atr_multiplier` {1,5 ; 2,0 ; 2,5 ; 3,0} × `bear_protection_mode`
{none, 1w_only, 1d_only} ; paires de déploiement `*/USDC` (transposition déclarée, § A.6) ; `parent.is_root` ; fees
`bybit`, taker 0,25 %, coûts par paire du GATE B (`config/pair_costs_b4.json`) ; `min_order_quote 5.0` ; capital
`"1000"` ; graine 20261001, `B = 10000`, blocs {10, 21, 42}, niveau 0,95 ; `lambda_mode: prefix` ; seuils avec leur
classe ; les 8 estampilles 1 w dérivées citées par `run_scope`.

**`c3_anchor` en local**, pur, sans base, registre et sortie dans un répertoire temporaire hors du dépôt, supprimé
ensuite — **contrôle du manifeste, pas le run** (acté à la relecture, A4) : code 0, `T = 2024-11-22T04:48:00+00:00`,
préfixe 1 362,2 j, 96 candidats, variante `3159a90780ebbf8a` (`grid-atr-v4-campagne-2021-2026`) nouvelle au registre
temporaire.

## 3. Registre de campagne

Le registre persistant de la campagne (runbook `skills/registry.md` : un seul registre pour toutes les familles, sel à
la racine, créé par Bruno), en mode `chain`. Il est nommé **sur les deux seules lignes `--registry` du pilote** et nulle
part ailleurs ; **ni l'agent ni le pilote ne le lisent, ne le copient, ne le listent ni ne le testent** (aucun stat,
aucun sha, aucune taille).

- **Ancrage autonome** (étape préalable à l'évaluation) : **première inscription** de la variante,
  `registry.new_entry` vrai dans `pre/anchor.json` (booléen extrait par le pilote, § 6 item 5).
- **`c3_verdict.py chain`, étape 1** : la variante y est déjà, enregistrement recalculé égal : **idempotent**,
  `registry.new_entry` faux dans `chain/anchor.json` (§ 6 item 7).
- **Étape 6** : l'issue, la raison et le statut compté sont inscrits une fois ; la sortie de la chaîne porte alors la
  ligne de forme fixe `written … (issue inscrite, § A.6)` (D13 : ni valeur ni digest), constatée par un booléen.
- **Déclarés, jamais vérifiés** (non-lecture) : la racine préservée à chaque réécriture (R-4 : passthrough de
  `c3_anchor`, tests T1, T2-chaîne, T2-verdict) ; `compte: false` inscrit ; **aucune évaluation différée inscrite**
  (la voie ne s'ouvre pas : code et tests X4, N1).
- **Limites, dites** : (K3) si le fichier n'existait pas au chemin donné, `c3_anchor` en créerait un neuf, **sans sel**,
  sans erreur, et `new_entry` serait vrai comme dans le cas normal — seule parade, la vérification § 1 du runbook par
  Bruno à la création de `CAMPAIGN_UNLOCK` ; (A2) une faute de frappe dans un littéral `--registry` du pilote créerait
  en silence un registre ailleurs — seule parade, la **relecture au caractère près** au STOP 1 (`tests/interdits.sh`
  vérifie aussi mécaniquement que les deux lignes portent le chemin construit, sans remplacer la relecture) ;
  `anchor.json` sur registre persistant n'est pas bit-stable entre exécutions — un seul run, aucune comparaison.

## 4. `CAMPAIGN_UNLOCK` (décision Q2)

Créé par **Bruno**, à la main, entre STOP 1 et le GO, dans l'arbre du service :
`~/apps/kraken-trading-bot/results/c3b_producteur/CAMPAIGN_UNLOCK` (non suivi ; la garde d'arbre du producteur ignore les
non-suivis). Le producteur le cherche sous la racine du code exécuté, donc dans le clone créé au lancement.

- `tests/preflight.sh` constate sa **présence** dans l'arbre du service (existence seule, contenu jamais lu) ;
- `tests/launch.sh` le **copie** dans le clone juste après le `.env` et vérifie l'égalité par `cmp` (aucun sha, rien
  affiché) — un transport par script, jamais une création ;
- la garde du pilote constate sa présence dans le clone (`campaign_unlock=present`) ; après le run, présent
  (`campaign_unlock_after=present`) ;
- le postflight le constate présent, non touché, dans l'arbre du service. **Bruno le supprime après le merge**
  (re-verrouillage ; une campagne future est un nouveau geste).

L'agent ne le crée jamais, même temporairement : le dry-run local emploie un **marqueur de simulation** d'un autre nom.

## 5. Ce qui tourne

**Pilote** : `results/c3_campagne_grid/server/run_campagne.sh`, versionné à S1 et **exécuté depuis le clone** à ce SHA ;
il consigne lui-même son sha256 (`pilot_sha256`), que la relecture recalcule au blob S1. Repris du pilote R-4
(`tests/reprise.out`). **Une seule exécution**, `--workers 3`, sous `nice -n 10` (posé par `launch.sh`), `--now
2026-10-01T00:00:00+00:00` (date du gel ; entre aussi dans `first_registered_at`), `--campaign GRID_ATR_V4_2026`
(étiquette d'instrument, dette 21). **Arrêt au premier écart** : une étape ne tourne que si toutes les précédentes ont
rendu leur attendu ; sinon `<clé>=NOT_RUN` et `halted_at` nomme le premier écart ; aucune écriture au registre ne suit
un écart. Contrôles « après » inconditionnels.

```
c3b_prefix.py   --manifest M --output-dir out/prefix --workers 3 --now N
c3_anchor.py    --manifest M --registry <registre de campagne> --output out/pre/anchor.json --now N
c3_entry.py     … --output out/pre/entry.json --markdown out/pre/entry.md --now N
c3_benchmark.py … --output out/pre/benchmark.json --now N
c3_select.py    … --output out/pre/selection.json --markdown out/pre/selection.md --now N
c3b_evaluate.py --manifest M --anchor out/pre/anchor.json --selection out/pre/selection.json \
    --benchmark out/pre/benchmark.json --output-dir out/eval --now N
c3_verdict.py chain --manifest M --observations out/prefix/observations.json --coverage out/prefix/coverage.json \
    --candles out/prefix/candles.json --evaluation out/eval/evaluation.json \
    --benchmark-eval out/eval/benchmark_eval.json --candles-eval out/eval/candles_eval.json \
    --registry <registre de campagne> --out-dir out/chain --campaign GRID_ATR_V4_2026 --now N
```

**Environnement unique** : l'interpréteur du venv du service, `env PYTHONPATH="$REPO/src"` sur chaque invocation
Python ; `alembic current` sans `PYTHONPATH`, depuis l'arbre du service, avant et après.

**Durée** (plan § 1, le calcul) : préfixe ≈ 36-38 min à 3 workers (96 × 1 362,2 j = 43,6 × la conformité R-4 ; débit du
rejeu grid à 3 workers) ; après le préfixe ≤ 11 min ; central ≈ 45 min. Attente : sonde toutes les 120 s, 120 sondes
(plafond 4 h) ; la sonde n'imprime que `exit=`, le nombre de lignes de `status.txt` et la clé de sa dernière ligne.

## 6. Attendu, item par item — la liste close de ce qui remonte

Tout ce qui n'est pas dans cette table reste au serveur, archivé, **jamais versionné ni ouvert**. Les items sont
vérifiés par `server/verify_attendu.py` sur les seuls `status.txt`, `alembic_before.txt`, `alembic_after.txt` et
`pilot_exit.txt`.

| # | Clés de `status.txt` | Attendu |
|---|---|---|
| 1 | `guard`, `pilot_sha256`, `pilot_copy` | `guard=0` au SHA S1 (complet) ; `krakenbot` du clone ; `protocol=d030ab23…79e6` ; `manifest=d422076b…5041` ; **`campaign_unlock=present`** ; `pilot_sha256` = sha du blob à S1 ; copie du pilote 0. Les gardes exigent aussi un arbre suivi propre, `poetry.lock` et `pyproject.toml` égaux à ceux du service, un `.env`, et aucune sortie déjà présente |
| 2 | `alembic_before`, `alembic_after`, `alembic_same_head` | `0`, `0`, `0` ; deux fichiers identiques portant `c3bd1e7a0001 (head)` |
| 3 | `service_before`, `service_after`, `tree_after`, `campaign_unlock_after` | service inchangé (HEAD, `dirty=0`, `collector=active`, même `NRestarts`) ; arbre du clone propre ; `present` |
| 4 | `workers`, `prefix` | `3` ; `0 event=-`. **Code 0 ⟹ base en lecture seule assertée par Postgres** (`probe_database`, `SHOW transaction_read_only = on`), sinon `database_read_failed` et 2 ; de même pour l'item 6 |
| 5 | `pre_anchor`, `registry_new_entry_pre`, `pre_entry`, `pre_benchmark`, `pre_select` | `0` ; **`true`** (première inscription au registre) ; `0` ; `0` ; `0` |
| 6 | `eval` | `0 event=evaluated`, **jamais** `refusal_form_written` |
| 7 | `chain`, `chain_steps`, `chain_verified`, `violations_empty`, `replay_violations_empty`, `registry_new_entry_chain`, `issue_inscrite`, `extract` | `0` ; `anchor:0,entry:0,benchmark:0,select:0,continuity:0` ; `true` ; `true` ; `true` ; `false` (étape 1 idempotente) ; `true` ; `0`. **Cinq codes d'étape, pas six (A1)** : `run_chain` invoque exactement les cinq étapes de `c3_verdict.CHAIN_FILES` (`scripts/audit/c3_verdict.py:2016`) ; le code du verdict est celui de la chaîne elle-même (`chain=0`), pas un sixième pas — le « six » du brief § 2.2 le comptait comme une étape |
| 8 | `issue`, `raison`, `selection_descriptive` | **`inconclusif`**, **`P_PROVENANCE`**, et **compté : non**, dérivé de `(issue, raison)` par la table du § 10.1 (décision Q1, `verify_attendu.out`) ; `selection_descriptive=true` (le statut `SÉLECTION_DESCRIPTIVE` comparé par le pilote, jamais imprimé). **Tout autre triplet, y compris un triplet « meilleur », est un écart, donc un STOP — jamais une bonne surprise** |
| 9 | `interpreter` | `0` : les deux provenances nomment le `krakenbot` du clone |
| 10 | `halted_at`, toute clé | `-` ; aucune étape `NOT_RUN` |
| 11 | `pilot_exit.txt` | `0` |

**L'issue et la raison viennent du canal sanctionné** : la chaîne § L.2 que `c3_verdict chain` publie sur stdout (dix
champs ; inventaire du plan, K2). Le pilote n'en retient que la ligne au label exact `C3_GRID_ATR_V4_2026` (une
évaluation synthétique porterait `C3_SYNTH_` et ne correspondrait pas), contrôle sa forme (neuf champs nommés, dans
l'ordre du code), n'imprime que `verdict` et `raison`, chacun validé contre sa liste close du § H.1 (sinon
`hors_liste`), et compare `statut_selection` à `SÉLECTION_DESCRIPTIVE` sans l'imprimer. `verdict.json` n'est **pas**
ouvert pour l'issue ; il l'est, en machine, pour quatre contrôles comme aux conformités (`chain.verified`, violations,
violations de rejeu, codes d'étape), de même que les deux `anchor.json` pour `registry.new_entry` — validé à la
relecture.

**`compté` n'a aucun canal** hors du registre (`c3_verdict` l'inscrit avec l'issue et la raison, ne l'écrit ni sur
stdout ni dans `verdict.json`) : il est **dérivé, non lu**. La table du § 10.1 est recopiée du texte dans
`verify_attendu.py` et épinglée aux constantes `COUNTED` et `UNCOUNTED_IF_REMOVED_BY` du code (`tests/table_10_1.out`).
La ligne conditionnelle (`A_NO_ADMISSIBLE_CANDIDATE`) n'est pas dérivable sans lecture et rend `indéterminé` : un écart.

**Le rapport cite `verdict=` et `raison=` tels que la chaîne les écrit.** La chaîne complète (identité retenue,
continuité, variante, empreintes) reste archivée, jamais lue : limite déclarée au regard du § L.2 (« le rapport cite la
chaîne »), voulue par le brief.

## 7. Constats hérités, écrits en le sachant

- **(a)** Provenance `contaminated` : `P_PROVENANCE` (rang 2 du § H.1) précède toute autre raison ; `R0_INVALID_RUN`
  sort en code 2 sans publication. **Toute chaîne en code 0 sur ce manifeste publie donc `inconclusif (P_PROVENANCE)`** :
  le triplet ne porte aucune information économique ; `validé` et `réfuté` sont inatteignables ; la voie du § 10.1 ne
  s'ouvre pas. Un autre triplet signalerait un défaut d'instrument.
- **(b)** La sélection est calculée et publiée sous `SÉLECTION_DESCRIPTIVE` (§ A.5 : un calcul descriptif reste
  autorisé ; table de statut du § H.1) ; l'évaluation porte sur la configuration retenue, chemin sélection seul.
- **(c)** `P_PROVENANCE` n'est pas compté (`CONTRAINTES_POST_B4.md` § 10.1). Le registre portera, pour la famille
  `grid-atr-v4`, un verdict non compté ; l'ancrage de toute variante future de la famille le lira (§ A.6).
- **(d)** Arrêt au premier écart : un écart au préfixe laisse le registre vierge ; un écart après l'ancrage autonome y
  laisse un enregistrement sans verdict (une relance du même manifeste y serait idempotente). Toute relance est une
  décision de Bruno.
- **(e)** La décision consécutive — clôture de la famille grid par la clause de clôture § K.2 de
  `docs/rejeu_grid_prespec.md` — est une décision de gestion de Bruno, inscrite à l'entrée 23 **avant** le run, avec son
  auteur ; elle n'est jamais déduite du verdict (protocole § K.1).

## 8. Bornes des lectures

Ce run est le **premier du producteur et de la chaîne C3 sur la fenêtre de campagne**. Ces données sont déjà explorées
au sens du § D.1 (P6, P7, B4, rejeu grid) : la portée reste **rétrospective** (§ D.2). Lectures du producteur bornées :
au préfixe, `≤ T`, amorçage `≥ début − 400 j` ; à l'évaluation, `≤ fin = 2026-06-29T00:00Z`, amorçage `≥ T − 400 j`.
**La date différée (2027-06-29) n'est lue par aucun module comme une fenêtre.** Appuis, sans lecture d'artefact : le
code (`candles_artefact` refuse toute estampille `> fin`, lectures du préfixe bornées à `T`), les tests, les codes de
chaîne (`continuity = 0` impose `period = [T, fin]` ; la règle d'entrée de `candles_eval.json` refuse, en code 2, toute
estampille postérieure à la fin). Ce n'est pas un journal de requêtes.

## 9. Non-lecture

- **Jamais à l'écran** : les sorties des producteurs et de la chaîne (`.json`, `.md`), le registre, les journaux,
  `extract.err` ; aucun listing, aucune taille, aucun sha d'artefact ; **aucun sha d'archive** (la règle du `.tgz.sha256`
  des conformités ne se recopie pas).
- **Remonte au dépôt** : `status.txt` (codes, noms d'événements de la liste close, booléens, `issue` et `raison`),
  `pilot_exit.txt`, les deux `alembic current`, `verify_attendu.out` (items, triplet constaté, compté dérivé), et les
  sorties des scripts du run (`tests/preflight.out`, `launch.out`, `wait.out`, `fetch.out`, `archive.out`,
  `postflight.out`). Avant S2, la règle 64 hex d'`interdits.sh` est balayée sur les quatre fichiers rapatriés (A4).

## 10. Règle d'échec

Tout code différent de l'attendu, un triplet différent (« meilleur » compris), `chain.verified` faux, une violation, un
refus d'entrée, une garde en échec, un item de `verify_attendu.out` en écart, tout besoin de toucher au manifeste, au
code ou au texte : **STOP**, constat versionné (`status.txt` et les extraits), **répertoire serveur laissé en place, ni
archive ni suppression**, rien de relancé, **aucune lecture de diagnostic sans l'accord de Bruno**. Un run compté ne se
réessaie pas : toute relance est une décision de Bruno. **Un refus de preflight** (rien lancé, rien écrit, ni serveur ni
registre) se re-tente après l'accord de Bruno : ce n'est pas une relance du run compté (A5).

## 11. Les vérificateurs, prouvés avant de servir

- **`tests/manifest_check.out`** (`rc=0`) : § 2.
- **`tests/events.out`** (`rc=0`) : la liste close `EVENTS` du pilote égale celle du code (54 = 54).
- **`tests/pilot_dryrun.out`** (`rc=0`) : le pilote tourne dans un monde simulé (clone, faux interpréteur, faux
  `systemctl`, registre simulé, marqueur de simulation au lieu de `CAMPAIGN_UNLOCK`), six lignes substituées et
  comptées : conforme → 0 ; triplet « meilleur » → 1 ; forme de refus → 1 (chaîne `NOT_RUN`, registre simulé sans
  verdict) ; échec du préfixe → 1 (registre simulé jamais créé) ; violation de chaîne → 1 ; `new_entry` faux → 1 ; SHA
  faux → 2 ; sans marqueur → 2. Limite dite : `bash` local 3.2, serveur 5.
- **`tests/mutants_pilote.out`** (`rc=0`, détail d'exécution) : trois mutants temporaires du pilote (contrôle du triplet
  retiré, arrêt au premier écart désactivé, garde `CAMPAIGN_UNLOCK` inversée) font chacun échouer le dry-run ; pilote
  restauré, `cmp` à 0.
- **`tests/verify_adverse.out`** (`rc=0`) : `verify_attendu.py` rend 0 sur le témoin (le `status.txt` de la simulation
  conforme) et 1 sur chacun des **31 cas déviés**, avec exactement un item en écart.
- **`tests/table_10_1.out`** (`rc=0`) : la recopie du § 10.1 égale les constantes du code ; deux mutants de la recopie
  mordent ; `(inconclusif, P_PROVENANCE)` dérive « non compté ».
- **`tests/archive_dryrun.out`** (`rc=0`, détail d'exécution) : le corps distant d'`archive.sh` dans un monde simulé —
  conforme → archivé en lecture seule et clone supprimé ; `out` résiduel → rien supprimé ; archive présente, pilote non
  terminé, session tmux ouverte → refus avant tout déplacement, source intacte.
- **`tests/interdits_*.out`** et **`tests/interdits_adverse.out`** (`rc=0`) : § 3 du brief ; les deux cas du pilote
  (faute de frappe dans un littéral `--registry`, troisième ligne `--registry`) mordent.
- **`tests/lint.out`**, **`tests/reprise.out`** (`rc=0`).

## 12. Après le run

`fetch` (quatre fichiers) → règle 64 hex balayée (A4) → `verify` (11/11 exigé) → **seulement alors** `archive`
(`~/archive/c3_campagne_grid_<AAAAMMJJ>/out`, déplacé, lecture seule, jamais supprimé ; la seule suppression du
chantier est celle du clone `repo/`, sous gardes, A3) → `postflight` → rapport `report.md` et issue de l'entrée 23 →
**STOP 2**.

**Cérémonie de Bruno, après STOP 2** (listée au rapport, jamais exécutée par l'agent) : vérification des clés de racine
du registre (runbook § 1, dont la dernière clause `variants == {}` ne tient plus après la première inscription) ;
sauvegarde du registre (runbook § 2) ; merge ; clôture § K.2 effective au journal ; suppression de `CAMPAIGN_UNLOCK`.
