# Première campagne C3 comptée — famille `grid-atr-v4` : constat d'arrêt au run (2026-10-01)

**Le run compté s'est arrêté à l'étape `c3_entry` autonome, en code 1. Aucune issue n'a été produite. Rien n'a été
relancé, archivé ni supprimé ; rien n'a été lu au-delà des quatre fichiers de la liste close.** Règle d'arrêt : brief
§ 4, attendu § 10. La suite est une décision de Bruno (§ 6).

## 1. Ce qui a tourné

- **Preflight** (2026-10-01T17:14:36Z, `rc=0`, `tests/preflight.out`) : service `235461e`, 0 ligne sale ; collector
  actif, `NRestarts=0` ; 5 915 Mo disponibles (plancher 5 000) ; `CAMPAIGN_UNLOCK` présent dans l'arbre du service ;
  aucun répertoire de run, aucune archive du jour, aucune session tmux.
- **Lancement** (`tests/launch.out`, `rc=0`) : au SHA S1 `cd4b17715a0dada8aa812df0e722072df6f0989b`, à 17:14:54Z,
  session `c3-campagne-grid-20261001`, sous `nice -n 10` ; pilote du clone = blob S1 (`3bbfd9fc…85e4`) ;
  `CAMPAIGN_UNLOCK` transporté de l'arbre du service au clone, `cmp` à 0.
- **Fin du pilote** : 17:58:36Z, **code 1** ; constatée par la 23ᵉ sonde, à 17:59:36Z (`tests/wait.out` : clés seules).
- **Rapatriement** (`tests/fetch.out`, `rc=0`) : `status.txt`, `pilot_exit.txt`, `alembic_before.txt`,
  `alembic_after.txt`, identiques au serveur ; leurs seules empreintes de 64 hex sont celles du pilote, du protocole et
  du manifeste (règle A4 tenue).

## 2. Ce que dit la liste close (`server/status.txt`)

| Clé | Valeur |
|---|---|
| `guard` | `0` au SHA S1, `krakenbot` du clone, protocole `d030ab23…79e6`, manifeste `d422076b…5041`, `campaign_unlock=present` |
| `pilot_sha256`, `pilot_copy` | `3bbfd9fc…85e4` (blob S1), `0` |
| `alembic_before`, `alembic_after`, `alembic_same_head` | `0`, `0`, `0` — `c3bd1e7a0001 (head)`, fichiers identiques |
| `workers`, `prefix` | `3` ; **`0 event=-`**, fin à 17:58:34Z (43 min 40 s pour 96 × 1 362,2 j) |
| `pre_anchor`, `registry_new_entry_pre` | **`0`**, **`true`** : la variante est inscrite au registre de campagne |
| `pre_entry` | **`1`** |
| `pre_benchmark`, `pre_select`, `eval`, `chain`, `extract`, `interpreter` | `NOT_RUN` (arrêt au premier écart) |
| `halted_at` | `pre_entry` |
| `service_after`, `tree_after`, `campaign_unlock_after` | identique à `service_before` (`235461e`, `dirty=0`, collector actif, `NRestarts=0`) ; `0` ; `present` |
| `pilot_exit.txt` | `1` |

`server/verify_attendu.out` : **4 items sur 11 tenus** (1 gardes, 2 base, 3 service, 4 préfixe). Les écarts 5 à 11 sont
le code 1 de `c3_entry` (item 5) et l'arrêt qui s'ensuit (items 6 à 11). Triplet constaté : `issue=absent`,
`raison=absent`, compté `indéterminé` — **aucune issue n'existe**.

## 3. Ce que signifie le code 1 — par le texte, sans lecture

Protocole § I.1, ligne 15 : code 1 = « auto-contrôle d'instrument en défaut » — « c'est une violation, pas un
résultat ». `c3_entry` écrit toujours sa validation : sur une violation, un artefact diagnostic (`invalide`). **La nature
de la violation n'est pas lue.** Elle est au serveur, dans `out/pre/entry.json`, `out/pre/entry.md` et
`out/logs/entry.log`. Ces fichiers sont du chemin sélection : ils ne s'ouvrent pas sans l'accord de Bruno, et ce qui en
serait lu se tranche avant, sur liste close (§ 6).

## 4. État du registre de campagne — déduit des codes, jamais lu

- **L'ancrage autonome a inscrit la variante** `3159a90780ebbf8a` (`grid-atr-v4-campagne-2021-2026`) :
  `registry_new_entry_pre=true`. Son enregistrement porte `first_registered_at = 2026-10-01T00:00:00+00:00` (`--now`).
- **La chaîne n'a pas tourné** : aucune issue, aucun statut compté, aucune évaluation différée n'est inscrit.
  L'enregistrement est **sans verdict**.
- **Conséquences mécaniques** (code, § A.6), énoncées sans les appliquer :
  - l'ancrage (`stop_criterion`) ne compte que les enregistrements qui portent un verdict, et la famille `grid-atr-v4`
    n'en porte aucun ;
  - une relance du **même** manifeste serait idempotente à l'ancrage (enregistrement recalculé égal), et
    `registry_new_entry_pre` y vaudrait `false`, contre `true` attendu par cet attendu-ci. C'est le cas prévu à
    l'attendu § 7 (d).
- Racine (sel) préservée à la réécriture de l'ancrage (R-4) : déclaré, jamais vérifié.
- **Le registre a changé** (première inscription) : sa sauvegarde (runbook § 2) et la vérification de ses clés de
  racine (runbook § 1, sans la clause `variants == {}`) relèvent de la cérémonie de Bruno.

## 5. Ce qui n'a pas été fait (règle d'arrêt)

- **Aucune relance.**
- **Aucune archive, aucune suppression** : `~/runs/c3_campagne_grid/campagne/` reste en place au serveur — le clone, le
  `.env` copié, la copie de `CAMPAIGN_UNLOCK` et `out/`.
- **Aucune lecture de diagnostic** : quatre fichiers rapatriés, aucun journal, aucun artefact ouvert, aucun listing, ni
  taille ni sha d'artefact.
- **Pas de postflight** : il suppose l'archive faite. L'état du service et de la base est celui que le pilote a relevé
  à 17:58:36Z (§ 2). Tunnel constaté fermé (`tests/tunnel.out`).
- **Jalon du § 10.2 : non atteint par ce run**, faute de verdict.

## 6. Ce qui attend la décision de Bruno

- **La lecture de diagnostic** : faut-il en faire une, et laquelle ? Les messages de violation de `c3_entry` peuvent
  porter des identités de candidats ou des valeurs : la liste de ce qui peut remonter se tranche avant toute lecture.
  Exemple : la seule liste des clauses I-A en violation et leur nombre, extraite par heredoc, sans identité ni valeur.
- **La suite du run** : relance après diagnostic et correction, ou autre. L'attendu de toute relance serait à
  redéclarer (au minimum `registry_new_entry_pre` ; le statut de ce run au regard du § 10.1 — aucun verdict inscrit —
  est à trancher).
- **Le répertoire du run au serveur** (en place) et `CAMPAIGN_UNLOCK` (présent dans l'arbre du service et dans le clone).
- **La cérémonie du registre** (§ 4).
