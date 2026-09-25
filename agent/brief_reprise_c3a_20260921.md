# Brief de reprise C3a — session agent du 2026-09-21

> Message d'ouverture de la nouvelle session Claude Code. **Non committé** (liste fermée § L.4),
> comme l'addendum de passation et le script de repro. Ce brief **complète**
> `agent/c3a_protocole_chronologique_v2.md`, il ne le remplace pas ; en cas de doute,
> `docs/protocole_c3.md` (gelé au `d931293`) fait foi sur tout. Version intégrant la revue
> d'Astra du 21/09 — **arrêt strict à R1 avant toute implémentation**.

## 0. Mission et bornes de la session

- Reprise de C3a au tip courant de `feat/c3a-protocole` (`5e056e0` — code identique à `e358df9`,
  seuls les commits de passation s'intercalent). Assert
  `git branch --show-current == feat/c3a-protocole` avant chaque commit ; un seul acteur git ;
  une découverte annexe se **signale**, ne se traite pas.
- **Dans la session** : chantier 0 (gate court), puis `c3_anchor`, `c3_entry`, `c3_benchmark`,
  `c3_select`, `c3_continuity` et leurs tests — dont `test_c3_chronology` — puis la fin de
  chaîne § L.2, puis le rapport de session.
- **Hors session** (ne pas commencer, même « presque fini ») : docs de clôture
  (`skills/backtest.md`, `results/INDEX.md`, `ROADMAP.md`, `PROJECT_CONTEXT.md`,
  `docs/CODE_MAP.md`, blocs `C3A-INTERIM`), brief C3b, toute modification de
  `docs/protocole_c3.md`, tout moteur / runner / seuil, toute campagne, toute exécution de C3b.
- **Plan mode, quatre points d'arrêt** :
  - **R1** — plan proposé, arrêt strict jusqu'à validation humaine ;
  - **R2** — chantier 0 livré seul (diff court), arrêt, revue ;
  - **R3** — après `c3_select` + `test_c3_chronology` (le cœur de la garantie), arrêt, revue ;
  - **Fin** — `c3_continuity` + fin de chaîne + rapport, arrêt final. La suite (revue de code
    Astra/Claude, docs de clôture, brief C3b) se fait hors de cette session.

## 1. À lire avant toute ligne (dans l'ordre)

> **État du répertoire de travail, à préserver tel quel** : la passation est actuellement
> **supprimée du working tree** et l'addendum est **non suivi**. Ne rien restaurer, ne rien
> ajouter automatiquement (`git add`, `git restore`, `git clean` interdits sur ces fichiers) ;
> aucun commit ne doit embarquer cet état. La passation se lit avec
> `git show HEAD:agent/passation_c3a_20260920.md`.

1. `agent/passation_c3a_20260920.md` — **via `git show`, voir ci-dessus** — état, décisions
   figées (§ 4), dettes (§ 5), défauts récurrents (§ 6), règles acquises (§ 9)
2. `agent/c3a_protocole_chronologique_v2.md` — le brief v2 : cadre général, interdits, done
3. `docs/protocole_c3.md` — **la spécification** ; en particulier § A.5, § I-A, § I.1 (la table
   unique), § B, § C, § F.2, § H, § L.1 à L.5
4. Le code livré : `scripts/audit/c3_common.py`, `scripts/audit/c3_verdict.py`,
   `tests/test_scripts/test_c3_common.py`, `tests/test_scripts/test_c3_verdict.py`
   (scan AST, `OPTIONAL_FIELDS`, test paramétré I.1, fixtures)
5. `skills/backtest.md` (§ Métriques, § Replay, § validation) — lecture seulement

## 2. Chantier 0 — gate court avant les modules

Objet : solder les constats de la revue croisée Claude/Astra du 21/09 qui portent sur le code
existant. Diff volontairement petit, livré seul, revu avant toute suite (R2).

a) **Contrôle `B == BOOTSTRAP_B` dans le verdict.** La constante existe (`c3_common.py:113`,
   § F.2 (b)) sans aucun site d'application ; le précédent du contrôle est au rejeu
   (`rejeu_validate_analysis.py:247`). Sémantique **deux codes**, implémentée et testée dans les
   deux sens :
   - `B` cohérent avec `len(delta_stars) + discarded` mais `≠ BOOTSTRAP_B` → **code 2** (refus
     d'entrée : l'artefact ne satisfait pas le contrat § F.2 (b)), rien n'est écrit ;
   - `B` contredit par les compteurs → **code 1** (désaccord recalculé, § I.1 l.15), comme
     aujourd'hui.
   **Interprétation proposée** : `B` cohérent mais différent de 10 000 relève du refus de
   contrat, code 2. Cette qualification est **explicitement validée à R1** ; aucune extension
   normative n'est introduite par un commentaire ou par `skills/backtest.md` — la norme reste le
   protocole, l'outillage documente son comportement sans le prescrire.
b) **Fixtures conformes au niveau verdict complet.** Tout test qui passe par `decide()` / `main()`
   avec un artefact prétendu conforme utilise `B = BOOTSTRAP_B` (réplications générées
   programmatiquement, pas de littéraux). Les tests isolés de primitives numériques gardent leurs
   petits échantillons **en le disant** (ils ne représentent pas un artefact C3 conforme).
   `B_TEST = 400` (`test_c3_verdict.py:41`) disparaît des chemins verdict-complet.
c) **`REASON_SCOPE` (`c3_common.py:323`) : suppression.** `F_NOT_ESTIMABLE` a deux portées dans
   I.1 (ligne 6 : candidat ; ligne 13 : run) — un dict raison→portée est faux par construction.
   Retirer aussi sa mention dans la docstring de `c3_verdict.py` (l.11) et l'assert de cohérence
   (`test_c3_verdict.py:280`). Si une raison forte de le garder apparaît : arrêt et signalement,
   jamais un branchement naïf.
d) **`BLOCKING_RUN_REASONS` (`c3_verdict.py:54`) : décision par constante.** Soit un site
   d'application réel, justifié et testé, soit suppression avec ses asserts (`test:281-282`).
   Ne pas brancher pour brancher.
e) **Textes périmés.** Aligner commentaires et docstrings sur la sémantique effective :
   absent / nul / mal typé = code 2 ; non-fini / hors-domaine = code 1 (§ I.1 l.15). Site connu :
   `c3_common.py:167-168` ; recenser les autres par grep. Ajouter `--anchor` à l'usage documenté
   (`c3_verdict.py:23-30` ; l'option est `required=True` à la l.369).
f) **Ne pas rouvrir** : `diagnostic.issue_calculee_puis_invalidee` (acté en revue) ; le
   comportement « exit 2 laisse lisible un verdict antérieur » (traité à la fin de chaîne, § 4
   ci-dessous, pas dans le chantier 0).

## 3. Les cinq modules — consignes en plus du protocole

L'ordre est celui du § L.1 : `c3_anchor`, `c3_entry`, `c3_benchmark`, `c3_select`,
`c3_continuity`. Chaque module implémente sa section du protocole avec la convention § L.4
(pur, lecture seule, JSON in/out, aucun accès DB, `--now` injectable, codes I.1 uniquement).
Ce qui suit ajoute les consignes issues de la revue croisée, rien d'autre.

**`c3_entry`** — schéma d'`entry` explicite, qui distingue **structurellement** :
- le **motif de refus de l'artefact** (portée artefact / run — I.1 lignes 2 et 5) ;
- les **diagnostics de candidats** (portée candidat — I.1 lignes 3-4 et 6), qui laissent la
  chaîne continuer.
`ok=True` accompagné de diagnostics candidats non vides est **légitime** (ligne 4). Une fois ce
contrat écrit, ajouter côté verdict le **test adverse** des combinaisons incohérentes *selon ce
contrat* — pas de règle « toute raison non nulle interdit ok=True ». Livrable réel : le refus de
l'artefact du rejeu, motif `D_WARMUP_PREFIX`, sous `results/c3a_entry_validation/` avec hash
source (décision figée, passation § 4) — jamais un verdict sur la famille grid.

**`c3_benchmark`** — § C. Dette 15(c) : traitement **défini** ; un benchmark encore désaligné est
**interdit d'usage décisionnel** (descriptif seulement, comme au rejeu).

**`c3_select`** — le **statut de sélection est calculé, jamais recopié**, par une table explicite
(provenance × résultat de sélection, abstention comprise), conforme à I.1 ligne 7
(`contaminated` / `unknown` + configuration retenue ⇒ `SÉLECTION_DESCRIPTIVE`, `validé`
inatteignable). Le verdict **recoupe à la consommation** : statut déclaré ≠ statut dérivable =
violation. Attention : la réciproque (`clean` ⇒ jamais `SÉLECTION_DESCRIPTIVE`) n'est **pas**
dans le texte gelé — c'est la table de `c3_select` qui la fixe. **La table complète est présentée
à R1** (notamment les cas `clean` et abstention) et validée avant implémentation ; même
discipline que pour `B` — aucune extension normative silencieuse.
Lignes 3 à 6 d'I.1 ajoutées au test paramétré (déjà au done du brief v2).

**`c3_continuity`** — § B, les **cinq clauses** (départ à plat à l'ancrage, absence de
réinitialisation aux frontières internes, liquidation costée, amorçage, première exécution),
chacune avec l'état de sa vérifiabilité — « non vérifiable » est une réponse admissible, une
preuve fausse ne l'est pas — **sans entrée réelle en C3a** (§ L.1, étape 5). Lire § B.1 sur la
frontière à ne pas confondre : la clause 1 est satisfaite **par** le moteur neuf que la clause 2
interdit en cours de run.

**`test_c3_chronology`** — chronologie forte : préfixe seul vs même préfixe + futurs différents →
admissibilité, scores, classement complet et choix / abstention **identiques**, **plus le
contrôle négatif** prouvant que le test détecte un scoreur fuyant.

## 4. Fin de chaîne — § L.2 complet

- `build_verdict_string` (`c3_verdict.py:278`) passe aux **neuf champs** : ajout de l'état de la
  continuité, de l'identité de variante (portée par l'artefact de `c3_anchor`, registre de
  variantes) et du sha256 des observations.
- Test d'intégration : **présence ET correspondance aux entrées** de chaque champ — pas un
  comptage à neuf.
- La chaîne d'orchestration **exige le code de succès** de chaque étape et **vérifie les
  empreintes** avant de consommer `verdict.json` — c'est ce qui neutralise « exit 2 laisse
  lisible un verdict antérieur ». Les empreintes détectent des discordances ; elles ne prouvent
  pas que l'invocation courante a réussi, et le test le reflète.
- **Le plan (R1) nomme, dans la liste fermée § L.4, le site de ce contrôle et son test
  d'intégration** — dont le cas d'un ancien verdict présent après l'échec de l'invocation
  courante. Aujourd'hui, aucun fichier ne le porte explicitement ; la liste L.4 est close
  (l'allonger serait un amendement au protocole), donc le site est choisi **dans** la liste et
  justifié au plan.

## 5. Hors périmètre — explicitement

- **Schéma d'évaluation intact** : bornes déclarées, une seule distribution `delta_stars`, pas
  d'export des six distributions (L, appariement) ni des deux Δ̂ observés. **Recommandation
  issue de la revue du 21/09, à faire approuver** : clarification normative datée sur les six
  distributions et la frontière de confiance, avant leur implémentation en C3b. Le schéma actuel
  reste provisoire ; **cette session ne clôt pas cette question**. Ne rien « améliorer » ici.
- Aucune modification de `docs/protocole_c3.md`. Une fixture qui révèle une incohérence du texte
  gelé → **arrêt et signalement**, jamais une modification pour faire passer un test.
- Docs de clôture et brief C3b : session séparée, après revue du code.

## 6. Règles acquises, non négociables

- Tout accès à un champ obligatoire passe par **l'accesseur strict de `c3_common`** — aucune
  logique de présence réécrite à la main.
- Tout statut **dérivable des preuves disponibles** est recalculé, jamais recopié ; un désaccord
  est une violation. Les déclarations non dérivables (la provenance notamment) sont exigées
  explicites et strictement typées.
- Finitude **et domaine** vérifiés avant toute comparaison (NaN, ±inf, rendement ≤ −1).
  `math.log1p(-1.0)` lève en Python : la garde de domaine est nécessaire, pas prudente.
- Aucun `bool(…)` sur une donnée externe, aucun `.get(clé, défaut)` sur un champ obligatoire dans
  `c3_*.py` — gardé par le test de scan de source (AST).
- Les tests couvrent **chaque classe d'erreur** (déclarations contradictoires dans les deux sens,
  clés absentes, `null`, types faux dont chaînes `"false"`, non-finis, hors domaine) et
  contiennent un **témoin sain** — et **le témoin sain est lui-même conforme au contrat** :
  un témoin non conforme mélange plusieurs défauts ; chaque contre-exemple doit être isolé à
  partir d'un témoin conforme (leçon du 21/09 — les constats 1 et 2 de la revue ont dû être
  reproduits à `B = 10 000` pour être établis). Chaque test asserte **l'issue interdite** autant
  que l'issue attendue.
- Codes de sortie conformes à I.1, **vérifiés par le test paramétré ligne à ligne**. Une
  violation **empêche la publication du verdict** : artefact diagnostic possible, explicitement
  invalide, sans chaîne citable.
- Diff de contrôle vide hors la liste fermée § L.4. « Ajout pur » vaut pour les tests hors-C3 ;
  les `test_c3_*.py` sont les fichiers du chantier et s'itèrent normalement.
- Le rapport décrit ce que les artefacts contiennent, pas ce que tu as voulu y mettre.
- Blocs `C3A-INTERIM` : ne pas y toucher dans cette session (clôture séparée).

## 7. Rapport de fin de session

- État du done du brief v2, en distinguant ce qui relève de la clôture (session séparée).
- Liste des **interprétations d'outillage validées à R1**, consignées telles quelles — au
  minimum : artefact diagnostic écrit en code 1 (I.1 muette) ; `B ≠ BOOTSTRAP_B` classé code 2 ;
  la table provenance × statut de `c3_select` ; toute autre interprétation prise en route.
  Leur documentation à la clôture (session séparée) **décrit** le comportement de l'outillage
  sans introduire d'extension normative — la norme reste le protocole.
- Point **§ L.5** : le diff depuis `f585e8b` (dernier SHA de déterminisme documenté) contient un
  changement `pyproject.toml` (exclusions Ruff) → l'option 2 de L.5 n'est **pas littéralement
  disponible**. Par défaut, prévoir l'**option 1** (24 tests de déterminisme sur le serveur au
  SHA livré, recette C2), sauf décision humaine **écrite** traitant l'écart. Le rapport le dit
  explicitement, il ne le sous-entend pas.
- `pytest -q` vert, `ruff` vert, `mypy src/` ≤ 64 (baseline).

## 8. Commits attendus (indicatif, atomiques)

- `fix(c3): chantier 0 — contrôle B=BOOTSTRAP_B, constantes mortes, textes périmés (+ tests)`
  (2-3 commits si le diff le justifie ; le contrôle B et ses tests peuvent vivre seuls)
- `feat(c3): c3_anchor + tests`
- `feat(c3): c3_entry + tests + refus de l'artefact rejeu (results/c3a_entry_validation/)`
- `feat(c3): c3_benchmark + tests`
- `feat(c3): c3_select + tests (I.1 lignes 3-6 au paramétré)`
- `test(c3): chronologie forte + contrôle négatif`
- `feat(c3): c3_continuity + tests`
- `feat(c3): chaîne de verdict § L.2 complète + test de correspondance`
