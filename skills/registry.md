# Runbook — Registre de campagne persistant (création, sauvegarde, non-lecture)

> Décisions R-1 à R-7 (conversation manifeste, 30/09). Tous les gestes de ce runbook sont faits par
> **Bruno, à la main, jamais par un agent** — même classe que `CAMPAIGN_UNLOCK`. Ce fichier ne contient
> aucun secret : il est versionnable, et sera commité comme livrable documentaire du micro-chantier
> « racine du registre » (R-4).

## Ordre des opérations (dépendance dure)

1. Micro-chantier R-4 **mergé** (l'ancrage préserve les clés de racine — sinon la première réécriture
   jette le sel, silencieusement).
2. § 1 — création du registre.
3. Gel du manifeste de la première campagne.
4. `CAMPAIGN_UNLOCK` (dernier geste, runbook distinct).

Après chaque run compté : § 2 (sauvegarde). En cas de registre suspect : § 3. En toutes circonstances : § 4.

## 1. Création (une fois)

Sur le serveur. La commande génère le sel **directement dans le fichier** : il n'apparaît ni à l'écran,
ni dans l'historique shell (l'historique garde la commande, jamais sa sortie — et aucun sel n'est tapé).

```bash
umask 077
mkdir -p ~/c3/registry
python3 - <<'EOF'
import json, pathlib, secrets
p = pathlib.Path.home() / "c3" / "registry" / "variants.json"
assert not p.exists(), "registre deja present - ne pas ecraser"
p.write_text(json.dumps({"salt": secrets.token_hex(32), "variants": {}}, indent=2) + "\n")
EOF
chmod 600 ~/c3/registry/variants.json
```

Vérification **par codes seulement** — le fichier n'est jamais affiché :

```bash
stat -c '%a %s' ~/c3/registry/variants.json
# attendu : 600 et une taille d'environ 100 octets
python3 -c 'import json, pathlib; d = json.load(open(pathlib.Path.home() / "c3/registry/variants.json")); print(sorted(d) == ["salt", "variants"] and len(d["salt"]) == 64 and set(d["salt"]) <= set("0123456789abcdef") and d["variants"] == {})'
# attendu : True — rien d'autre
```

Règles :
- Emplacement : `~/c3/registry/variants.json`, **hors de tout arbre git**, jamais sous `~/apps/` ni
  `~/docker/` (dette 23). Les pilotes de campagne le reçoivent en chemin absolu par `--registry`.
- **Un seul registre pour toutes les familles** (§ A.6, le champ `family` distingue).
- Le sel ne vit **que dans ce fichier et ses sauvegardes**. C'est lui qui rend tout digest du registre
  non inversible — et donc qui rend légitime l'usage de `sha256sum` au § 2 : sans sel, un digest du
  registre serait une poignée de brute-force (D13).

## 2. Sauvegarde (après chaque run compté)

Le registre est l'**unique porteur** du sel et, après une inscription différée, de l'empreinte
différée : le perdre, c'est perdre la sortie prospective. Cadence : quelques écritures par an — la
copie est un geste de la cérémonie de run, pas une tâche de fond.

```bash
# 1. Sur le laptop — copie datée (jamais d'écrasement : une copie corrompue par-dessus
#    l'unique sauvegarde serait la perte qu'on prévient)
mkdir -p ~/c3-backup && chmod 700 ~/c3-backup
scp <serveur>:~/c3/registry/variants.json ~/c3-backup/variants.json.$(date +%Y%m%d)
chmod 600 ~/c3-backup/variants.json.*

# 2. Vérification croisée — deux lignes de 64 hex à comparer à l'œil, fichier jamais ouvert
ssh <serveur> sha256sum '~/c3/registry/variants.json'
sha256sum ~/c3-backup/variants.json.$(date +%Y%m%d)

# 3. Copie froide — clé USB dédiée, même geste, même vérification par sha
```

- Pas de cloud tiers en clair : le contenu est un secret au sens plein — le manifeste de campagne,
  versionné, énumère les candidats ; registre exposé = configuration retenue brute-forçable par
  quiconque, pas seulement par nous.
- Les copies datées se gardent toutes (quelques centaines d'octets).

## 3. Registre suspect — restaurer, jamais réparer

Un registre corrompu **se constate par codes** (la canonicalisation à la lecture produit un code 1 ;
un refus d'entrée inattendu, un `chain.verified` faux) et **se restaure depuis la dernière sauvegarde
vérifiée**, par copie + `sha256sum` croisé. Il ne s'ouvre pas, il ne s'édite pas — pas même « juste
pour voir ». S'il faut comprendre une défaillance, c'est un chantier avec ses gates, sur une **copie
du registre dans un monde jeté**, jamais sur l'original, et la question de ce qui peut en être lu se
tranche avant, sur liste close.

Exposition soupçonnée du sel (affiché, loggé, copié en clair quelque part) : rotation possible par
cérémonie — le sel n'est engagé nulle part à l'extérieur du fichier — nouveau `secrets.token_hex(32)`
écrit en place par le même procédé que § 1, sauvegarde immédiate. Au moindre doute, faire.

## 4. Non-lecture et interdits (permanent)

- **Personne ne lit le registre, jamais, même pour debug.** La chaîne seule y accède, en machine.
- Aucun script, hors la chaîne, ne `cat`/affiche son contenu, un digest, ou sa **taille** (canal D13).
- Le chemin `~/c3/` n'apparaît jamais sous un arbre git ; `interdits.sh` des chantiers futurs l'étend :
  pas de lecture du registre, pas de digest imprimé, pas de listing de taille, chemin absent des dépôts.
- Les sauvegardes suivent les mêmes règles que l'original (600, jamais ouvertes, vérifiées par sha).

## Renvois

- R-4 (micro-chantier « racine du registre ») : préservation des clés de racine par l'ancrage, tests,
  adverse « sel jeté à la réécriture », test de la normalisation UTC de D2 (limite du lot 1) ; cadrage
  4 questions après le lot 2. Avant de le graver : vérifier qu'aucun test ni vérificateur n'épingle la
  racine exacte `{"variants"}` — si un le fait, trois lignes de v2.4 d'abord.
- D13 (chantier outillage v2.3, lot 1) : la ligne du verdict n'imprime plus le digest du registre ;
  `anchor.json.registry.sha256` reste (contrat de chaîne), rendu non inversible par le sel.
- Preuve de déterminisme de la campagne : `anchor.json` n'est **pas** identique au bit entre exécutions
  sur registre persistant (`registry.new_entry`, `registry.sha256` évoluent) — la liste des artefacts
  comparés du manifeste devra en tenir compte (ouvert de la conversation manifeste).
