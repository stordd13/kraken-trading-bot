# Addendum à la note de passation C3a — revue Claude du 2026-09-21

> À coller en ouverture de la nouvelle conversation, **avec** `passation_c3a_20260920.md` (version
> actualisée le 21/09) et le script `repro_c3_verdict_e358df9.py`. **Non committé** : la note du repo
> ne se modifie qu'après consensus avec Astra ; ni cet addendum ni le script n'entrent dans le repo
> (liste fermée § L.4).

## État vérifié (ne pas refaire)

- Zip `krakenbot-src-v2_10_0-c2-replay-28-g5e056e0.zip` : code identique à `e358df9` ; le seul écart
  avec `5ee4b1f` est la note de passation.
- Les 7 fichiers du Project (`CLAUDE.md`, `PROJECT_CONTEXT.md`, `ROADMAP.md`, `CODE_MAP.md`,
  `CONTRAINTES_POST_B4.md`, `protocole_c3.md`, `c3a_protocole_chronologique_v2.md`) sont identiques
  octet pour octet à ce zip. La note uploadée est celle du zip.
- `test_c3_common` + `test_c3_verdict` : 122 tests verts (Python 3.12.3, hors poetry).
- Corrections `e358df9` confirmées sur le code : violation → exit 1, artefact `invalide: true`,
  `verdict` / `raison` / `verdict_string` à `null` ; preuve manquante → exit 2, rien d'écrit. La table
  I.1 est muette sur l'écriture d'un artefact en code 1 : convention d'outillage compatible, à
  écrire dans `skills/backtest.md` à la clôture. Pas d'arrêt-signalement.
- Le GO d'Astra (point de reprise, pas la chaîne) **tient** : aucun point ci-dessous n'est une
  régression de `e358df9`, et `validé` / `réfuté` sont inatteignables sur données réelles avant C3b.

## Constats sur `c3_verdict.decide()` au `e358df9` — reproduits par le script, non testés dans le repo

| # | Entrée | Obtenu | Classement |
|---|---|---|---|
| 1 | `entry.ok=True` + `entry.reason="D_WARMUP_PREFIX"` | `validé` | **défaut net** — `reason` jamais lu |
| 2 | `SÉLECTION_DESCRIPTIVE` + provenance `clean` | `validé` | **défaut net** — statut dérivable de la provenance (§ A.5, I.1 l.7), non recoupé |
| 3 | `B=2` | `validé` | **défaut net** — § F.2 (b) fixe 10 000 ; `BOOTSTRAP_B` sans site d'application ; `DISCARDED_MAX=10` n'a de sens qu'à ce B ; fixtures à `B_TEST=400` |
| 4 | Chaîne de verdict | 6 champs | **écart de spec** — § L.2 en exige 9 (manquent : état de la continuité, identité de variante, sha256 des observations) ; aucun test sur L.2 |
| 5 | Tous Δ\* < 0, six bornes déclarées +1.0 | `validé` | **décision de schéma, pas un défaut** — bornes non dérivables du schéma actuel. Sous-spécification du protocole gelé à signaler : E2 porte sur « la distribution de Δ\* », il y en a six ; le code en lit une |

Mineurs : exit 2 laisse lisible un `verdict.json` antérieur (le verdict ne hache pas ses entrées) ;
`diagnostic.issue_calculee_puis_invalidee` porte le mot « validé » dans un artefact invalide ;
docstring de `c3_verdict` qui invoque `REASON_SCOPE` alors que `decide()` ne lit ni `REASON_SCOPE`
ni `BLOCKING_RUN_REASONS` ; trois docstrings disent encore « non-fini = code 2 » (le code fait 1,
conforme à I.1 l.15) ; `--anchor` absent de l'usage documenté.

## En attente

1. **Contre-vérification par Astra** des constats 1 à 5 (script fourni).
2. **Décision Bruno + Astra** sur le constat 5 (frontière de confiance sur les bornes, E2 sur les six
   distributions) — consignée dans le brief C3b, pas codée en C3a ; schéma d'évaluation marqué
   « provisoire, non contractuel » à la clôture.

## Proposition de rattachement au brief du nouvel agent (après consensus, à confirmer au cadrage)

- **Chantier 0**, gate court avant les cinq modules : `B == BOOTSTRAP_B` + fixtures à 10 000 ;
  docstrings périmées ; `BLOCKING_RUN_REASONS` / `REASON_SCOPE` branchés ou supprimés.
- **Avec `c3_entry`** : schéma d'`entry`, cohérence `ok` / `reason`, test adverse côté verdict.
- **Avec `c3_select`** : statut de sélection recalculé depuis la provenance (en plus des lignes 3 à 6
  de I.1 déjà prévues).
- **Fin de chaîne** : test assertant les neuf champs du § L.2.

## Cadrage 4 questions — lecture de Claude, non encore confirmée par Bruno

Nouvel agent ; plan mode, arrêt après `c3_select` + `test_c3_chronology` (plus le gate du chantier
0) ; **réserve sur le scope** : docs de clôture et brief C3b dans une **session séparée**, après
revue du code par Astra et Claude (le défaut le plus récurrent du projet est la prose qui décrit ce
que l'artefact ne porte pas) ; fin = done du brief + règles acquises de la note + § L.5 + les
quatre ajouts ci-dessus.
