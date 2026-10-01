#!/bin/bash
# C3 racine du registre — inventaire-filet (brief § 3.1, runbook « Renvois ») : recenser tout test, fixture ou
# vérificateur qui épingle la RACINE EXACTE du registre (`{"variants"}` seul, égalité de clés de racine, schéma fermé).
# Si un épinglage normatif existe : STOP (trois lignes de v2.4 d'abord, décision de Bruno).
# Périmètre : tests/ entier, scripts/audit/*.py, et les vérificateurs et pilotes de la conformité v2.3, repris au lot 2
# (results/c3_outillage_v2_3/{conformite,gate_L5,tests}, hors mutants_lot1.sh : chantier clos, ne retourne pas).
# Méthode : grep de motifs (littéral de racine, égalité au registre entier, clés de racine, octets ou sha du registre),
# puis CHAQUE occurrence est classée par une table déclarée ci-dessous (fichier + fragment de ligne, jamais un numéro de
# ligne) ; toute occurrence non classée, ou classée « normatif », fait sortir rc=1.
# Usage : bash inventaire_filet.sh <étiquette>. Sortie : inventaire_filet_<étiquette>.out.
set -o pipefail
set -u
LABEL="${1:?étiquette}"
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
OUT=results/c3_racine_registre/tests/inventaire_filet_${LABEL}.out
RAW=$(mktemp)
{
  echo "# inventaire-filet — $LABEL — $(date -u +%FT%TZ)"
  echo "# HEAD $(git rev-parse HEAD) branche $(git branch --show-current)"
} > "$OUT"
PAT='\{ *"variants" *:|\{ *'"'"'variants'"'"' *:|== *\{ *"variants"|\b(registry|reg|raw|registre)\b[^#]*\.keys\(\)'
PAT="$PAT"'|\b(set|sorted|list|len)\((registry|raw|reg)\)|(variants\.json|registry|registry_path)"?\]?\)?\.read_bytes\(\)'
PAT="$PAT"'|file_sha256\([^)]*(registry|variants|REGISTRY)|read_json\([^)]*(registry|variants|REGISTRY)[^)]*\) *(==|!=)'
PAT="$PAT"'|\b(set|sorted|list|len)\((cc\.|rc\.)?(read_json|json\.loads?)\([^)]*(registry|variants|REGISTRY)'
VPAT='variants\.json|--registry|registry'
{
  grep -rnE "$PAT" tests scripts/audit --include='*.py'
  grep -rnE "$PAT|$VPAT" results/c3_outillage_v2_3/conformite results/c3_outillage_v2_3/gate_L5 \
    results/c3_outillage_v2_3/tests --include='*.py' --include='*.sh' | grep -v '^results/c3_outillage_v2_3/tests/mutants_lot1\.sh:'
} | LC_ALL=C sort -u > "$RAW"
echo "occurrences=$(grep -c . "$RAW")" >> "$OUT"
python3 - "$RAW" >> "$OUT" <<'PY'
import sys

#: Table de classement, déclarée : (fichier, fragment de la ligne, classe, motif). Classes : `defaut` (le code à
#: corriger, § 3.2), `octets_inchanges` (un registre non réécrit — idempotence, violation, refus), `type_de_variants`
#: (refus d'un `variants` mal typé), `contrat_de_chaine`, `variants_seul` (lecture de `variants`, jamais de la racine),
#: `entre_executions` (registres neufs comparés entre exécutions d'un même run), `simulation` (monde simulé, son propre
#: écrivain), `hors_sujet` (un autre « registre »). Aucune classe `normatif` : une occurrence qui épinglerait la racine
#: n'a pas de ligne ici et sort en NON CLASSÉE.
TABLE = [
    ("scripts/audit/c3_anchor.py", 'return {"variants": {}}', "defaut", "registre absent : racine neuve, rien à préserver (inchangé)"),
    ("scripts/audit/c3_anchor.py", 'return {"variants": dict(variants)}', "defaut", "lecture / idempotence : la racine est jetée (§ 3.2)"),
    ("scripts/audit/c3_anchor.py", 'return {"variants": updated}', "defaut", "écriture : la racine est jetée (§ 3.2)"),
    ("scripts/audit/c3_anchor.py", 'registry: dict[str, Any] = {"variants": {}}', "defaut", "valeur initiale de main, jamais écrite (succès seul)"),
    ("scripts/audit/c3_anchor.py", '"sha256": cc.file_sha256(registry_path)', "contrat_de_chaine", "anchor.json.registry.sha256 (D13, rendu non inversible par le sel)"),
    ("tests/test_scripts/test_c3_anchor.py", 'registry_after_1 = (tmp_path / "variants.json").read_bytes()', "octets_inchanges", "idempotence (§ A.6)"),
    ("tests/test_scripts/test_c3_anchor.py", 'assert (tmp_path / "variants.json").read_bytes() == registry_after_1', "octets_inchanges", "idempotence (§ A.6)"),
    ("tests/test_scripts/test_c3_anchor.py", "altered = registry_path.read_bytes()", "octets_inchanges", "enregistrement altéré non réécrit"),
    ("tests/test_scripts/test_c3_anchor.py", "assert registry_path.read_bytes() == altered", "octets_inchanges", "enregistrement altéré non réécrit"),
    ("tests/test_scripts/test_c3_anchor.py", """write_text('{"variants": [1, 2]}'""", "type_de_variants", "variants non mapping : refus 2"),
    ("tests/test_scripts/test_c3_anchor.py", 'assert len(cc.read_json(tmp_path / "variants.json")["variants"]) == 1', "variants_seul", "nombre d'enregistrements, jamais la racine"),
    ("tests/test_scripts/test_c3_anchor.py", 'registry_before = cc.file_sha256(case / "variants.json")', "octets_inchanges", "refus N2 : registre inchangé"),
    ("tests/test_scripts/test_c3_anchor.py", 'unchanged = cc.file_sha256(case / "variants.json") == registry_before', "octets_inchanges", "refus N2 : registre inchangé"),
    ("tests/test_scripts/test_c3_verdict.py", 'assert cc.file_sha256(w["registry"]) not in first.out + first.err', "octets_inchanges", "D13 : digest non imprimé (aucune racine lue)"),
    ("tests/test_scripts/test_c3_verdict.py", 'before = cc.file_sha256(w["registry"])', "octets_inchanges", "discordance : registre non réécrit"),
    ("tests/test_scripts/test_c3_verdict.py", 'assert cc.file_sha256(w["registry"]) == before', "octets_inchanges", "discordance : registre non réécrit"),
    ("tests/test_scripts/test_c3_verdict.py", """w["registry"].write_text('{"variants": [1]}'""", "type_de_variants", "variants non mapping : la chaîne s'arrête à l'ancrage"),
    ("tests/test_scripts/test_c3_verdict.py", "registry_before = cc.file_sha256(REAL_REGISTRY)", "octets_inchanges", "livrable v2.0 : refusé au sha du protocole avant load_registry"),
    ("tests/test_scripts/test_c3_verdict.py", "assert cc.file_sha256(REAL_REGISTRY) == registry_before", "octets_inchanges", "livrable v2.0 inchangé"),
    ("tests/test_scripts/test_c3_verdict.py", "assert cc.file_sha256(registry) == registry_before", "octets_inchanges", "copie du livrable v2.0 inchangée"),
    ("tests/test_indicators/test_multi_pair_registry.py", "assert len(registry) ==", "hors_sujet", "registre d'indicateurs multi-paires, sans rapport"),
    ("scripts/audit/bybit_q5_ws_capture.py", "if len(raw) <= 6", "hors_sujet", "message WebSocket brut, sans rapport"),
    ("results/c3_outillage_v2_3/tests/pilot_dryrun.sh", "registry", "simulation", "registre simulé du dry-run, son propre écrivain ; ne lit pas la sortie de l'outil"),
    ("results/c3_outillage_v2_3/tests/manifest_check.sh", "variants.json", "entre_executions", "registre jeté d'un ancrage local, jamais relu"),
    ("results/c3_outillage_v2_3/tests/manifest_check.sh", "registre et sortie dans un répertoire temporaire", "entre_executions", "commentaire : registre jeté"),
    ("results/c3_outillage_v2_3/conformite/server/run_conformite.sh", "variants.json", "entre_executions", "registres neufs par exécution, comparés au bit entre exécutions"),
    ("results/c3_outillage_v2_3/conformite/server/run_conformite.sh", "registry_copy_", "entre_executions", "code de la copie du registre"),
    ("results/c3_outillage_v2_3/conformite/server/run_conformite.sh", "registre", "entre_executions", "commentaires de procédure"),
    ("results/c3_outillage_v2_3/conformite/server/run_conformite.sh", "--registry", "entre_executions", "argument de la chaîne"),
    ("results/c3_outillage_v2_3/conformite/server/verify_attendu.py", "variants.json", "entre_executions", "artefact de la liste des 23, comparé entre exécutions"),
    ("results/c3_outillage_v2_3/conformite/server/verify_attendu.py", "registry_copy_", "entre_executions", "code de la copie du registre"),
    ("results/c3_outillage_v2_3/tests/interdits_adverse.sh", "variants.json", "simulation", "cas dévié d'interdits (artefact interdit)"),
    ("results/c3_outillage_v2_3/tests/interdits_lot2_adverse.sh", "variants.json", "simulation", "cas dévié d'interdits (artefact interdit)"),
    ("results/c3_outillage_v2_3/tests/interdits_lot2_adverse.sh", "registre", "simulation", "commentaire du cas dévié"),
    ("results/c3_outillage_v2_3/tests/interdits_adverse.sh", "registre", "simulation", "commentaire du cas dévié"),
    ("results/c3_outillage_v2_3/tests/interdits.sh", "variants", "simulation", "motif d'artefact interdit"),
    ("results/c3_outillage_v2_3/tests/interdits_lot2.sh", "variants", "simulation", "motif d'artefact interdit"),
    ("results/c3_outillage_v2_3/tests/non_divulgation.sh", "registry", "contrat_de_chaine", "contrôle D13 (aucun digest du registre imprimé)"),
    ("results/c3_outillage_v2_3/tests/non_divulgation.sh", "registre", "contrat_de_chaine", "contrôle D13 (commentaire)"),
]

bad = 0
counts: dict[str, int] = {}
for raw in open(sys.argv[1], encoding="utf-8").read().splitlines():
    if not raw:
        continue
    path, line, text = raw.split(":", 2)
    hit = next((t for t in TABLE if t[0] == path and t[1] in text), None)
    if hit is None:
        print(f"NON CLASSÉE {path}:{line} {text.strip()[:140]}")
        bad = 1
        continue
    counts[hit[2]] = counts.get(hit[2], 0) + 1
    print(f"{hit[2]:<18} {path}:{line} — {hit[3]}")
print("par_classe=" + " ".join(f"{k}:{v}" for k, v in sorted(counts.items())))
print(f"normatif=0 non_classees={'0' if not bad else '≥1'}")
print("constat=" + ("aucun épinglage normatif de la racine" if not bad else "occurrence non classée : STOP"))
sys.exit(bad)
PY
rc=$?
rm -f "$RAW"
echo "rc=$rc" >> "$OUT"
exit $rc
