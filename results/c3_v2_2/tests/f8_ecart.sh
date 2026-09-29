#!/bin/bash
# C3 v2.2, AM-11 (§ F.8) — écart entre les deux chemins du rendement géométrique, mesuré sur les séries des
# tests existants, aucune fixture neuve : sélection `cc.cagr_pct` (somme `math.fsum`, correctement arrondie)
# contre évaluation `cc.cagr_rows` aux indices identité (chemin `numpy` du § F.2 c). Lancé par `bash` depuis le
# dépôt. Aucun accès base. Sortie : f8_ecart.out ; rc=0 ssi chaque écart mesuré est sous la majoration écrite
# dans AM-11 : |ΔCAGR| ≤ (100 + |CAGR|) · (365 / n_jours) · 1,01 · n · u · Σ|log1p r| + 8 · ulp(CAGR).
set -o pipefail
set -u
unset VIRTUAL_ENV

ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
OUT=results/c3_v2_2/tests/f8_ecart.out

{
  echo "# f8_ecart — $(date -u +%FT%TZ)"
  echo "# HEAD $(git rev-parse --short HEAD) branche $(git branch --show-current)"
} > "$OUT"

poetry run python - >> "$OUT" 2>&1 <<'PY'
import math
import sys
from pathlib import Path

root = Path.cwd()
sys.path.insert(0, str(root / "tests"))
import numpy as np
from test_scripts import test_c3_common as fx  # séries des tests existants

import c3_common as cc  # chemin inséré par test_c3_common

U = 2.0 ** -53
series = []
series.append(("witness_returns(329)", fx.witness_returns(), fx.EVAL_DAYS))
for seed in range(1, 21):
    series.append((f"varying_returns({seed}, 329)", fx.varying_returns(seed), fx.EVAL_DAYS))
for pair in fx.PAIRS:
    for index in range(3):
        rec = cc.recompute_daily(fx.nav_path(pair, index), days=fx.PREFIX_DAYS)
        series.append((f"nav_path({pair}, {index}) -> rendements", list(rec.returns), fx.PREFIX_DAYS))

worst_ratio = 0.0
worst_abs = 0.0
worst_ulps = 0.0
ok = True
for label, returns, days in series:
    r = np.asarray(returns, dtype=float)
    n = r.size
    a = cc.cagr_pct(returns, days)
    b = float(cc.cagr_rows(np.log1p(r), np.arange(n)[None, :], days)[0])
    diff = abs(a - b)
    s_abs = float(np.sum(np.abs(np.log1p(r))))
    bound = (100.0 + abs(a)) * (365.0 / days) * 1.01 * n * U * s_abs + 8.0 * float(np.spacing(abs(a)))
    ulps = diff / float(np.spacing(abs(a))) if a != 0 else 0.0
    ratio = diff / bound
    ok = ok and diff <= bound
    worst_ratio = max(worst_ratio, ratio)
    worst_abs = max(worst_abs, diff)
    worst_ulps = max(worst_ulps, ulps)
    print(f"{label}: n={n} cagr_fsum={a!r} cagr_numpy={b!r} ecart={diff!r} ulps={ulps:.1f} majoration={bound!r}")
print(f"series={len(series)} ecart_max={worst_abs!r} ulps_max={worst_ulps:.1f} ecart_sur_majoration_max={worst_ratio!r}")
print(f"numpy={np.__version__} python={sys.version.split()[0]}")
sys.exit(0 if ok else 1)
PY
rc=$?
echo "rc=${rc}" >> "$OUT"
exit "$rc"
