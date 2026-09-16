"""Rebuild offline UML component figures using only the Python standard library."""
from html import escape
from pathlib import Path
import textwrap

ROOT = Path(__file__).resolve().parent
COMMON_TOP = [
    ('Observed inputs', ['US contracts, books and timestamps', 'Recorded frames or public capture', 'NWS forecast for LLM arms']),
    ('Chronological replay', ['engine.replay / Session worker', 'Decision time and evidence cutoffs', 'One isolated run per strategy']),
    ('Strategy dispatcher', ['Strategy.decide(...)', 'Frozen per-run configuration', 'New protocol: availability gate', 'Then market and book checks']),
]
COMMON_END = [
    ('Decision and risk policy', ['Entry / owned-inventory exit / skip', 'Cost-aware sizing and price limits', 'LLM arms: selected risk profile']),
    ('Paper fill and account', ['Account.fill on a later book', '$50 initial cash / $40 reserve', 'Recheck depth, costs and exposure', 'Final venue settlement only']),
    ('Audit and presentation', ['Run journal and call/retrieval audits', 'Checkpoints and acceptance receipts', 'Dashboard results and export', 'Paper outcomes; no live orders']),
]
ARMS = [
    ('01-control', '1. Deterministic control',
     [('Verified reference signals', ['Configured public wallet only', 'Exact US contract + rules mapping', 'New, timely and deduplicated']),
      ('Structural and quote checks', ['core.quote / complete_partition', 'Full weather-day interval required', 'Basket legs share the same interval', 'Copy tolerance OR complete basket']),
      ('Control-mode policy', ['Copy OR basket; separate runs', 'Basket: complete YES partition', 'Discovery spread >= $0.03', 'No model calls'])],
     ['Copying is unhedged. Basket fills model an ideal all-legs-fill scenario.',
      'Intent delay: 2 seconds; expiry: 60 seconds. Fill-time basket spread must remain >= $0.02.']),
    ('02-fixed', '2. Fixed LLM with RAG',
     [('EvidenceStore', ['SQLite FTS5 + weather analogues', 'Prior station-days available as of t', 'Immutable evidence revisions']),
      ('Context and protocol diagnostics', ['At least 10 causal history days', 'Complete 23-25 hour forecast path', 'Peak times and temperature changes', 'Half-degree bin sensitivity', 'Market prices excluded']),
      ('Fixed inference policy', ['One medium-tier / medium-effort call', 'CloudModel -> configured cloud API', 'Versioned forecasting guidance', 'Budget, schema and citation gates'])],
     ['Cloud inference is optional and requires local credentials, tariff and budget configuration.',
      'The fixture model replaces inference in demo mode. Delay includes measured or fixture latency.']),
    ('03-adaptive', '3. Adaptive LLM routing with RAG',
     [('EvidenceStore', ['Same retrieval as fixed LLM', 'Station/time filters and analogues', 'Immutable evidence revisions']),
      ('Context and protocol diagnostics', ['Same validated evidence as arm 2', 'History count and residual spread', 'Bucket distance and forecast revision', 'Hourly change and bin sensitivity', 'Market prices excluded']),
      ('Router and inference policy', ['Four base + two protocol features', 'Small/low, medium/medium, large/high', 'At most one escalation to large/high', 'Versioned forecasting guidance', 'Budget + schema + citation gates'])],
     ['Routing is deterministic; the LLM cannot change risk limits or the shared budget.',
      'Score 0 -> small; 1-2 -> medium; 3-6 -> large. Final interval width > 0.40 forces abstention.']),
    ('04-polyswarm', '4. PolySwarm-inspired ensemble',
     [('EvidenceStore', ['Same station/time retrieval', 'Prior forecast/outcome pairs', 'Relevant rules and research notes']),
      ('Shared context and diagnostics', ['Full-day path and causal history', 'Peak timing and half-degree stress', 'Same evidence and protocol guidance', 'No prices or other persona outputs', 'Stateless sequential requests']),
      ('Ensemble inference policy', ['Medium-tier / medium-effort calls', 'Confidence-capped weighted mean', '70% consensus + 30% market midpoint', 'Abstention / disagreement gates'])],
     ['Persona calls are sequential within one worker; separate strategy workers may overlap.',
      'Any persona abstention or probability standard deviation > 0.15 blocks entry. Not a full paper replication.']),
]


def text(x, y, value, size=15, weight='normal', fill='#202020'):
    return f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{fill}">{escape(value)}</text>'


def component(x, y, title, lines):
    out = [f'<g><rect x="{x}" y="{y}" width="330" height="175" fill="white" stroke="#333" stroke-width="1.4"/>',
           text(x+16, y+24, '«component»', 12, fill='#555'),
           text(x+16, y+51, title, 17, 'bold'),
           f'<path d="M{x+303} {y+13}h14v20h-14z M{x+298} {y+17}h10v5h-10z M{x+298} {y+25}h10v5h-10z" fill="white" stroke="#333"/>',
           f'<path d="M{x} {y+64}h330" stroke="#aaa"/>']
    offset = y+86
    for line in lines:
        for segment in textwrap.wrap(line, 43):
            out.append(text(x+16, offset, segment, 13))
            offset += 18
    assert offset <= y+181, (title, offset)
    return ''.join(out)+'</g>'


def flow(path, x, y, label):
    return f'<path d="{path}" fill="none" stroke="#444" stroke-width="1.3" stroke-dasharray="5 4" marker-end="url(#arrow)"/>'+text(x,y,label,11,fill='#444')


def render(slug, title, middle, notes):
    nodes = COMMON_TOP+middle+COMMON_END
    if slug == '01-control':
        nodes = list(nodes)
        nodes[0] = ('Observed inputs', ['US contracts, books and timestamps', 'Public wallet signals with mapping', 'Recorded frames or public capture'])
        nodes[6] = ('Deterministic sizing policy', ['Copy size / basket budget / skip', 'Reference limit or payoff spread', 'No LLM risk-profile controls'])
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="1140" height="995" viewBox="0 0 1140 995" role="img" aria-labelledby="title desc">',
           f'<title id="title">{escape(title)}</title><desc id="desc">UML logical component view. Dashed directional connectors carry information between components. No live execution adapter.</desc>',
           '<defs><marker id="arrow" markerWidth="9" markerHeight="9" refX="8" refY="4" orient="auto"><path d="M1 1L8 4L1 7" fill="none" stroke="#444"/></marker></defs>',
           '<rect width="1140" height="995" fill="#fff"/><g font-family="Arial, Helvetica, sans-serif">',
           text(30,42,title,27,'bold'), text(30,72,'UML component view / new real-data protocol: weather-methods-20260916-v1',15),
           text(30,97,'Dashed arrows: «flow» information connectors. Boxes are logical responsibilities, not deployment nodes.',12,fill='#555')]
    for i, (name, lines) in enumerate(nodes):
        svg.append(component(30+(i%3)*375,125+(i//3)*260,name,lines))
    svg += [flow('M360 210H405',363,201,'frame'), flow('M735 210H780',740,201,'call'),
            flow('M945 300V385',956,345,'dispatch'),
            flow('M570 300V385',581,345,'as of t'),
            flow('M360 470H405',363,460,'data'), flow('M735 470H780',738,460,'context'),
            flow('M945 560V609H195V645',473,599,'validated forecast / deterministic candidate'),
            flow('M360 730H405',360,720,'intent'),flow('M735 730H780',740,720,'audit')]
    svg += [text(30,873,'COMMON EXECUTION BOUNDARY',13,'bold'),
            text(30,899,'Protocol requires t >= 2026-09-16 17:07:01 UTC. Sample demos retain the original protocol. No live orders.',14)]
    for i,note in enumerate(notes): svg.append(text(30,927+i*24,note,13))
    svg.append('</g></svg>')
    (ROOT/(slug+'.svg')).write_text(''.join(svg),encoding='utf-8')


def main():
    for arm in ARMS: render(*arm)
    links=''.join(f'<a href="#{s}">{escape(t)}</a>' for s,t,_,_ in ARMS)
    figures=''.join(f'<section id="{s}"><h2>{escape(t)}</h2><a href="{s}.svg" target="_blank">Open vector figure</a><img src="{s}.svg" alt="{escape(t)} UML component diagram"></section>' for s,t,_,_ in ARMS)
    html='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Weather Lab — Architecture UML</title><style>
    *{box-sizing:border-box}body{margin:0;background:#111;color:#eee;font:16px/1.6 Arial,Helvetica,sans-serif}main{max-width:1200px;margin:auto;padding:32px 24px}h1{font-size:32px;margin:0}h2{font-size:23px}p{max-width:900px;color:#ccc}a{color:inherit;text-underline-offset:4px}nav{display:flex;gap:12px 28px;flex-wrap:wrap;border-block:1px solid #555;padding:20px 0;margin:28px 0}section{margin:46px 0}img{display:block;width:100%;height:auto;margin-top:18px}footer{border-top:1px solid #555;padding:22px 0;color:#bbb}@media print{body{background:white;color:black}nav{display:none}section{break-before:page}a,p,footer{color:black}}
    </style><main><h1>Weather Lab / Architecture UML</h1><p>Four implemented paper-trading architectures with the weather-methods-20260916-v1 protocol. Component views show responsibilities and information flow. Each strategy has an isolated account and shares the same validation and fill rules.</p><p><a href="../ARCHITECTURE-UML.md">Detailed sequence diagrams and source map</a> · <a href="https://github.com/burdena0/weather-lab-polymarket-us/blob/main/docs/ARCHITECTURE-UML.md">Read rendered sequence diagrams on GitHub</a></p><nav>'''+links+'</nav>'+figures+'''<footer>Real-data decisions require the protocol availability date and full-day forecast diagnostics. Original sample demos omit the new protocol. Daily RAG collection is a separate Sol / low scheduled task. Apple Weather / NWS is currently a separate comparison study. It is not wired into strategy forecasts. Cloud access and phone setup remain configuration prerequisites; these figures do not establish live inference, fills or profitability.</footer></main></html>'''
    (ROOT/'index.html').write_text(html,encoding='utf-8')


if __name__=='__main__': main()
