# Seconde campagne C3 comptée — famille `grid-atr-v4`, relance unique après correction d'instrument : rapport (2026-10-02)

**Le run compté a tenu son attendu, 11 items sur 11. Issue publiée par la chaîne : `inconclusif (P_PROVENANCE)`, non
compté** — le triplet déclaré avant le run (`attendu.md` § 6, entrée 24). Aucun écart. Rien n'a été lu du chemin
sélection hors de la liste close. C'était la relance unique du § 10.1 (décision de Bruno) : plus aucune relance pour la
famille grid. La suite appartient à Bruno (§ 5).

## 1. Ce qui a tourné

| Pas | Heure (UTC, 2026-10-02) | Résultat | Preuve |
|---|---|---|---|
| GO de lancement nommant S1 `fb253db18ecd5bf5f9e01b54cebfdb565479f55e` | — | après la CI verte sur S1 (tentative 1, `tests/ci_status_S1.out`), la relecture de Bruno (STOP 1), la création de `CAMPAIGN_UNLOCK` et le contrôle du registre réel par Bruno (`attendu.md` § 4 : `True`) | — |
| Archive-préalable du run v1 | 07:51:02 | `rc=0` : sonde à 0 (même périphérique, formes GNU), tous les codes du corps à 0 ; `out/` v1 déplacé vers `~/archive/c3_campagne_grid_20261001/out`, en lecture seule, jamais ouvert ; clone v1 supprimé | `tests/archive_prealable.out` |
| Preflight (lecture seule) | 07:51:08 | `rc=0` : service `235461e`, 0 ligne sale ; `run_dir` absent ; `jour_lancement=20261002` (A1') ; 5 987 Mo disponibles ; collector actif, `NRestarts=0` ; `CAMPAIGN_UNLOCK` présent | `tests/preflight.out` |
| Lancement | 07:51:26 | `rc=0` : clone au SHA S1, pilote du clone = blob S1 (`a1e47f35…`), `CAMPAIGN_UNLOCK` transporté (`cmp` à 0), session `c3-campagne-grid-20261002`, `nice -n 10` | `tests/launch.out` |
| Fin du pilote | 08:36:41 | **code 0** (constaté à la 24ᵉ sonde, 08:38:06 ; sondes : clés seulement) | `tests/wait.out` |
| Rapatriement | 08:38 | les quatre fichiers de la liste close, identiques au serveur | `tests/fetch.out` |
| Règle 64 hex | 08:38 | tenue : seules empreintes des fichiers rapatriés, celles du pilote, du manifeste gelé et du protocole | `tests/interdits_fetch.out` |
| Vérification de l'attendu | 08:38 | **11/11** | `server/verify_attendu.out` |
| Archive du run v2 | 08:39:03 | `rc=0` : `out/` déplacé vers `~/archive/c3_campagne_grid_20261002/out`, en lecture seule, vérifié par codes, aucun sha ; clone v2 supprimé | `tests/archive.out` |
| Postflight (lecture seule) | 08:39:08 | `rc=0` : `~/runs/c3_campagne_grid` absent ; aucune session du chantier ; les deux archives présentes, en lecture seule, sans `repo/` ni `.env` ; service `235461e`, 0 ligne sale ; collector actif, `NRestarts=0` ; `alembic` `c3bd1e7a0001 (head)` ; `CAMPAIGN_UNLOCK` présent | `tests/postflight.out` |

Tunnel constaté fermé au G0 et après le run (`tests/tunnel.out`) : il n'a pas servi.

## 2. Ce que dit la liste close (`server/status.txt`)

| Clé | Valeur |
|---|---|
| `guard` | `0` au SHA S1, `krakenbot` du clone, protocole `d030ab23…79e6`, manifeste `b757c45b…4f11`, `campaign_unlock=present` |
| `pilot_sha256`, `pilot_copy` | `a1e47f35…69ed2` (blob S1), `0` |
| `alembic_before`, `alembic_after`, `alembic_same_head` | `0`, `0`, `0` — `c3bd1e7a0001 (head)`, fichiers identiques |
| `workers`, `prefix` | `3` ; **`0 event=-`**, fin à 08:35:35 (44 min 09 s pour 96 × 1 362,2 j ; 43 min 40 s au v1) |
| `pre_anchor`, `registry_new_entry_pre` | **`0`**, **`true`** : la variante v2 est inscrite, nouvelle au registre |
| `pre_entry`, `pre_benchmark`, `pre_select` | `0`, `0`, `0` |
| `eval` | **`0 event=evaluated`** (08:36:27) |
| `chain`, `chain_steps` | **`0`** (08:36:40) ; `anchor:0,entry:0,benchmark:0,select:0,continuity:0` |
| `chain_verified`, `violations_empty`, `replay_violations_empty` | `true`, `true`, `true` |
| `registry_new_entry_chain`, `issue_inscrite` | `false` (étape 1 idempotente), `true` |
| `issue`, `raison`, `selection_descriptive` | **`inconclusif`**, **`P_PROVENANCE`**, `true` |
| `extract`, `interpreter`, `halted_at` | `0`, `0`, `-` |
| `service_after`, `tree_after`, `campaign_unlock_after` | identique à `service_before` (`235461e`, `dirty=0`, collector actif, `NRestarts=0`) ; `0` ; `present` |
| `pilot_exit.txt` | `0` |

## 3. L'issue, par le canal sanctionné

- **La chaîne § L.2** publiée par `c3_verdict chain` porte, au label `C3_GRID_ATR_V4_2026`, **`verdict=inconclusif`** et
  **`raison=P_PROVENANCE`**. Ce sont les deux seuls champs lus ; le statut de sélection est comparé à
  `SÉLECTION_DESCRIPTIVE`, sans être imprimé. La chaîne complète (identité retenue, continuité, variante, empreintes)
  reste archivée, jamais lue — limite déclarée au regard du § L.2 (« le rapport cite la chaîne »), voulue par le brief.
- **Compté : non**, dérivé de `(inconclusif, P_PROVENANCE)` par la table du § 10.1 recopiée et épinglée au code
  (`tests/table_10_1.out`) ; dérivé, non lu. L'inscription `compte` au registre est déclarée, jamais vérifiée.
- **Ce que l'issue dit, et ce qu'elle ne dit pas** : sous provenance `contaminated`, toute chaîne en code 0 publie ce
  triplet (§ H.1, rang 2). Il ne porte **aucune information économique** : ni `validé` ni `réfuté` n'étaient
  atteignables, la voie prospective du § 10.1 ne s'ouvrait pas. Ce run prouve que l'instrument traverse la fenêtre de
  campagne de bout en bout avec un verdict réel ; il ne dit rien de la famille.

## 4. Registre de campagne — déduit des codes, jamais lu

- L'ancrage autonome a inscrit la variante v2 (`registry_new_entry_pre=true`), dont le parent, la variante v1, était
  déjà au registre ; l'étape 1 de la chaîne l'a trouvée égale (`registry_new_entry_chain=false`) ; l'étape 6 a inscrit
  l'issue (`issue_inscrite=true`).
- **Déclarés, jamais vérifiés** : le statut `compte: false` inscrit avec l'issue ; **aucune évaluation différée
  inscrite** ; la racine (le sel) préservée à chaque réécriture ; la variante v1 toujours sans verdict.
- **Le registre a changé** (inscription de v2 et de son verdict) : sa sauvegarde et la vérification de ses clés de racine
  relèvent de la cérémonie de Bruno (§ 5).

## 5. Ce qui attend Bruno

- **Cérémonie du registre** : vérification des clés de racine (runbook § 1 sans `variants == {}` ; le contrôle de
  l'attendu § 4 ne vaut plus, le registre portant désormais deux variantes), puis sauvegarde datée (runbook § 2).
- **Merge** de `feat/c3-campagne-grid-v2` (C0 `765fc19`, S1 `fb253db`, S2 et S3 au tip).
- **Clôture § K.2 effective au journal** (`docs/rejeu_grid_prespec.md` § K.2, décision de gestion inscrite à
  l'entrée 24 avant le run). Sa portée au regard du § 10.2 relève de cette clôture.
- **Suppression de `CAMPAIGN_UNLOCK`** dans l'arbre du service, après le merge (re-verrouillage).
- **Jalon du § 10.2** : premier verdict réel de la famille grid, produit le **2026-10-02** (chaîne à 08:36:40Z), avant
  l'échéance du 2027-01-31 — consigné à l'issue de l'entrée 24.

## 6. Écarts

**Aucun.** Rien n'a été relancé ; aucun refus de preflight ; aucune lecture de diagnostic ; aucun fichier hors de la
liste close n'a été ouvert ; aucune empreinte d'artefact ni d'archive calculée ni versionnée.
