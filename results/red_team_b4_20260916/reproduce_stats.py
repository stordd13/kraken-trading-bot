"""Offline reproduction; no DB, no strategy execution, no repository writes."""
from pathlib import Path
import sys,json,math,statistics,collections
root=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(root/'scripts'))
import p7_report as r
p1=json.loads((root/'results/B4_P7_phase1_cross_validate.json').read_text())
p2=json.loads((root/'results/B4_P7_phase2_walk_forward.json').read_text())
sel=json.loads((root/'results/B4_P7_final_selection.json').read_text())
flags=r.collect_flags(p1)+r.collect_flags(p2)
a=r.aggregate_walk_forward(p2)
fresh=r.build_selection(a,sel['benchmarks'],r.ineligible_configs(flags))
out={'exact_all_verdicts':fresh['all_verdicts']==sel['all_verdicts'],'exact_selected':fresh['selected_for_paper']==sel['selected_for_paper'],'n_phase1':len(p1),'n_phase2':len(p2),'n_aggregates':len(a),'n_flags':len(flags),'scenarios':{},'quarters':[],'zero_trades':[]}
for scenario in ('original','TF_factor_diagnostic'):
 aa=r.aggregate_walk_forward(p2)
 if scenario=='TF_factor_diagnostic':
  for x in aa.values():
   f=math.sqrt(288) if 'grid' in x.strategy else 1 if 'dca' in x.strategy else math.sqrt(6)
   x.mean_sharpe_oos*=f;x.mean_sharpe_train*=f
 vs=[r.apply_selection_criteria(x,sel['benchmarks']) for x in aa.values()]
 out['scenarios'][scenario]={'passing':sum(v.passed for v in vs),'criterion_pass_counts':[sum(v.criteria[i].passed for v in vs) for i in range(7)],'verdicts':[v.to_dict() for v in vs]}
for s in sorted(set(v['strategy'] for v in p2.values())):
 es=[v for v in p2.values() if v['strategy']==s]
 out['zero_trades'].append({'strategy':s,'train_zero':sum(v['train']['total_trades']==0 for v in es),'test_zero':sum(v['test']['total_trades']==0 for v in es),'tests':len(es),'test_pf_inf':sum(math.isinf(v['test']['profit_factor']) for v in es)})
for combo in sorted(set((v['strategy'],v['pair']) for v in p2.values())):
 es=[v for v in p2.values() if (v['strategy'],v['pair'])==combo]
 for w in range(1,9):
  z=[v for v in es if v['window_idx']==w]
  out['quarters'].append({'combo':combo,'window':w,'period':z[0]['period'],'return_median':statistics.median(v['test']['total_return_pct'] for v in z),'return_min':min(v['test']['total_return_pct'] for v in z),'return_max':max(v['test']['total_return_pct'] for v in z),'trades':sorted(set(v['test']['total_trades'] for v in z)),'sharpe_median_original_units':statistics.median(v['test']['sharpe_ratio'] for v in z)})
print(json.dumps(out,indent=2))
