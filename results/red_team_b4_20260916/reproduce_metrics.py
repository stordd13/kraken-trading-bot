"""Read-only audit: execute archived metric method bodies on synthetic paths, no app imports/DB."""
from __future__ import annotations
import ast, json, math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[2]
text=(ROOT/'scripts/backtest.py').read_text()
tree=ast.parse(text)
ns=globals()
TradeSide=SimpleNamespace(BUY='buy',SELL='sell')
for node in tree.body:
    if isinstance(node,ast.ClassDef) and node.name=='BacktestMetrics':
        exec(compile(ast.Module(body=[node],type_ignores=[]),str(ROOT/'scripts/backtest.py'),'exec'),ns)
methods={}
for node in tree.body:
    if isinstance(node,ast.ClassDef) and node.name in ('BacktestEngine','GridBacktester'):
        method=next(n for n in node.body if isinstance(n,ast.FunctionDef) and n.name in ('calculate_final_metrics','_calculate_final_metrics'))
        exec(compile(ast.Module(body=[method],type_ignores=[]),str(ROOT/'scripts/backtest.py'),'exec'),ns)
        methods[node.name]=ns[method.name]

def make_state(step_minutes):
    start=datetime(2024,1,1,tzinfo=timezone.utc)
    curve=[(start+timedelta(minutes=step_minutes*i),Decimal(v)) for i,v in enumerate(('1000','700','2000','1900'))]
    return SimpleNamespace(metrics=BacktestMetrics(duration_days=step_minutes*3/1440),strategy_name='synthetic',equity_curve=curve,usdc_balance=Decimal('1900'),crypto_balance=Decimal(0),btc_held=Decimal(0),pairs_completed=0,liquidated_positions=0,total_fees=Decimal(0),_terminal_liquidation_done=True,_force_close_open_positions=lambda:None)

out={}
for name,method in methods.items():
    cases={}
    for step in (5,240,1440):
        state=make_state(step);method(state)
        cases[str(step)]={'max_drawdown_pct':state.metrics.max_drawdown_pct,'sharpe_ratio':state.metrics.sharpe_ratio,'sortino_ratio':state.metrics.sortino_ratio}
    assert cases['5']['max_drawdown_pct']==15
    assert cases['5']['sharpe_ratio']==cases['1440']['sharpe_ratio']
    out[name]=cases
out['synthetic_true_max_drawdown_pct']=30
out['annualization_factors_diagnostic']={'5m':math.sqrt(288),'4h':math.sqrt(6),'1d':1}

# Exact sequential net-of-buy-fee PF and fixed-trade sensitivity on available Bybit signal reference.
d=json.loads((ROOT/'results/b4_3_bybit_signal_A_post.json').read_text())
roundtrips=[]; pending=[]
for t in d['trades']:
    if t['side']=='buy':pending.append(t)
    elif t['side']=='sell':
        assert len(pending)==1
        buy=pending.pop(); raw=Decimal(t['pnl']); net=raw-Decimal(buy['fee'])
        roundtrips.append((raw,net,t))
assert not pending
calc_pf=lambda values:float(sum((x for x in values if x>0),Decimal(0))/-sum((x for x in values if x<0),Decimal(0)))
base_net=sum((v for _,v,_ in roundtrips),Decimal(0))
cost_sensitivity={}
for scale in (Decimal('.5'),Decimal('1'),Decimal('1.5')):
    pnl=base_net
    for _,_,t in roundtrips:
        if t['liquidity']=='taker':
            q=Decimal(t['amount_crypto']); p=Decimal(t['reference_price']); c=Decimal(t['spread_pct'])+Decimal(t['slippage_pct']); f=Decimal(t['fee_rate'])
            pnl+=q*p*c*(1-scale)*(1-f)
    cost_sensitivity[str(scale)]={'net_pnl':float(pnl),'return_pct':float(pnl/Decimal(d['capital'])*100)}
out['bybit_signal_reference']={'pair':d['pair'],'period':d['period'],'roundtrips':len(roundtrips),'pf_as_stored':d['metrics']['profit_factor'],'pf_excluding_buy_fees':calc_pf([v for v,_,_ in roundtrips]),'pf_net_all_fees':calc_pf([v for _,v,_ in roundtrips]),'net_pnl':float(base_net),'cost_sensitivity_fixed_trades':cost_sensitivity}
print(json.dumps(out,indent=2))
Path(__file__).with_name('metrics_evidence.json').write_text(json.dumps(out,indent=2))
