"""Archive US display-price history and settlements, without inventing depth/fills."""
import argparse
import hashlib
import json
import time
import urllib.parse
from datetime import date, timedelta
from pathlib import Path
from .core import number, stamp
from .sources import PublicSource, normalize_market


def validate_history(data, start, end):
    rows = data['history']
    if not isinstance(rows, list) or len(rows) > 20000:
        raise ValueError('Price history row limit exceeded')
    output = []; previous = None
    for row in rows:
        at = stamp(row['timestamp'])
        yes, no = number(row['longPrice']), number(row['shortPrice'])
        if not 0 <= yes <= 1 or not 0 <= no <= 1:
            raise ValueError('Display price outside probability bounds')
        if previous is not None and at <= previous:
            raise ValueError('Duplicate or unordered price history')
        previous = at
        if start <= at <= end:
            output.append({'timestamp':at, 'yes_display_price':yes, 'no_display_price':no})
    return output


def collect(root, start, end):
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    if not 1 <= (last-first).days+1 <= 31 or last >= date.today():
        raise ValueError('Require 1-31 completed weather dates')
    root = Path(root); root.mkdir(parents=True, exist_ok=False)
    source = PublicSource(root/'receipts', max_requests=1250)
    deadline = time.monotonic()+900
    markets = []; seen = set(); errors = []; complete = False
    for offset in range(0, 1000, 100):
        query = {'categories':'climate', 'closed':'true', 'endDateMin':start+'T00:00:00Z',
                 'endDateMax':(last+timedelta(days=2)).isoformat()+'T00:00:00Z', 'limit':100, 'offset':offset}
        data, received, _ = source.get('https://gateway.polymarket.us/v1/markets?'+urllib.parse.urlencode(query))
        batch = data['markets']
        for raw in batch:
            if raw['id'] in seen: raise ValueError('Overlapping inventory pages')
            seen.add(raw['id'])
            try:
                market = normalize_market(raw, received)
                if start <= market['date'] <= end: markets.append(market)
            except Exception as exc:
                errors.append({'stage':'rules','id':str(raw['id']),'error':str(exc)[:180]})
        if len(batch)<100: complete=True; break
    if len(markets)>600: raise ValueError('More than 600 target contracts; narrow the interval')
    (root/'markets.json').write_text(json.dumps(markets,indent=2),encoding='utf-8')
    counts={'markets':len(markets),'markets_with_prices':0,'price_points':0,'settlements':0,'pre_day_prices':0}
    with (root/'market-history.jsonl').open('x',encoding='utf-8') as out:
        for market in markets:
            if time.monotonic()>deadline:
                errors.append({'stage':'deadline','error':'Collection reached 900-second bound'}); break
            row={'market':market,'historical_depth_available':False,'wallet_signals_available':False,
                 'fill_simulation_eligible':False,'rules_first_seen_verified':False}
            try:
                # Documented 30-day profile: three-hour display prices, never executions.
                q={'symbol':market['slug'],'fixedInterval':'INTERVAL_1M','fidelity':180}
                data, received, hashed = source.get('https://gateway.polymarket.us/v1/price-history?'+urllib.parse.urlencode(q))
                begin=stamp(market['day_start']); close=stamp(market['close_at'])
                points=validate_history(data,begin-86400,close)
                row.update(prices=points,prices_received_at=received,prices_receipt_hash=hashed,
                           price_semantics='Book-derived display prices, normally YES ask and NO one-minus-bid; no quantity or trade identity')
                counts['markets_with_prices']+=bool(points);counts['price_points']+=len(points)
                counts['pre_day_prices']+=sum(p['timestamp']<begin for p in points)
            except Exception as exc:errors.append({'stage':'prices','slug':market['slug'],'error':str(exc)[:180]})
            try:
                data, received, hashed = source.get('https://gateway.polymarket.us/v1/markets/'+urllib.parse.quote(market['slug'],safe='')+'/book')
                book=data['marketData'];stats=book['stats'];settlement=stats['settlementPx'];at=stamp(stats['settlementSetTime'])
                value=number(settlement['value'])
                if book['marketSlug']!=market['slug'] or book['state'] not in ('MARKET_STATE_EXPIRED','MARKET_STATE_CLOSED','MARKET_STATE_TERMINATED') or settlement['currency']!='USD' or value not in (0,1) or not stamp(market['close_at'])<=at<=received:
                    raise ValueError('Unverified binary USD settlement identity/state/time')
                row['settlement']={'yes_payout':value,'published_at':at,'received_at':received,'receipt_hash':hashed}
                counts['settlements']+=1
            except Exception as exc:errors.append({'stage':'settlement','slug':market['slug'],'error':str(exc)[:180]})
            out.write(json.dumps(row,allow_nan=False)+'\n');out.flush()
    report={'start':start,'end':end,'created_at':time.time(),'inventory_complete':complete,**counts,'errors':errors,
            'requests':source.count,'historical_trades_simulated':False,'historical_depth_available':False,
            'public_wallet_source_found':False,'first_seen_availability_verified':False,
            'price_history_docs':'https://docs.polymarket.us/api-reference/price-history/get-price-history',
            'limits':'Supplemental market archive only. Display prices have no depth. Current rules lack historical first-seen proof. Private reports require separate institutional authentication. No invented fills, wallet activity or P&L.',
            'files':{n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in ('markets.json','market-history.jsonl')}}
    (root/'summary.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('out','start','end'):p.add_argument('--'+name,required=True)
    a=p.parse_args(); print(json.dumps(collect(a.out,a.start,a.end),indent=2))


if __name__=='__main__':main()
