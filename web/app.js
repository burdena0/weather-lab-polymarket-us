const strategies = [
  ['wallet_control','Wallet control','Deterministic copy or strict basket arbitrage'],
  ['fixed_llm','Fixed model','Fixed effort / RAG'],
  ['adaptive_llm','Adaptive model','Model routing / RAG'],
  ['polyswarm','PolySwarm','Persona ensemble / RAG']
];
let state, busy=false;
function currentResults(){return state.session?state.session.results:state.latest}
const $=id=>document.getElementById(id);
function el(tag,text,cls){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n}
function money(v){return v===null||v===undefined?'—':new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',minimumFractionDigits:2,maximumFractionDigits:4}).format(v)}
function notice(text,error=false){$('notice').textContent=text;$('notice').className=error?'error':''}
function disable(value){busy=value;document.querySelectorAll('button').forEach(b=>b.disabled=value)}
async function refresh(){const r=await fetch('/api/state');if(!r.ok)throw Error('Cannot read local dashboard state');state=await r.json();render()}
async function post(path,body,raw=false){if(busy)return;disable(true);try{const r=await fetch(path,{method:'POST',headers:{'X-WeatherLab-CSRF':state.csrf,'Content-Type':raw?'application/octet-stream':'application/json'},body:raw?body:JSON.stringify(body)});const d=await r.json();if(!r.ok)throw Error(d.error||'Operation failed');notice(d.message);await refresh()}catch(e){notice(e.message,true);try{await refresh()}catch(_){}}finally{disable(false)}}
function render(){
  renderStudy();
  const account=state.account||{status:'disconnected'};
  $('account-badge').textContent=account.status==='connected'?'Verified / read only':account.status;
  $('account-balance').textContent=money(account.current_balance);
  $('account-power').textContent=money(account.buying_power);
  $('account-positions').textContent=account.positions_count===null||account.positions_count===undefined?'—':String(account.positions_count)+(account.positions_complete?'':' +');
  $('account-status').textContent=account.error||(account.status==='connected'?'Verified '+new Date(account.checked_at*1000).toLocaleString()+'. '+(account.positions_notice||(!account.positions_complete?'Position coverage is partial.':'')):account.status==='unverified'?'Saved link. Refresh to verify this session.':'Link your local saved credentials to view an account snapshot.');
  $('account-connect').hidden=!!account.linked;
  $('account-refresh').hidden=!account.linked;
  $('account-disconnect').hidden=!account.linked;
  if(state.readiness){const r=state.readiness;$('readiness-summary').textContent=(r.cloud_configured?(state.recent_historical?.cloud.validated_calls>0?'Historical cloud inference validated; prospective data gates still apply.':'Cloud settings complete; inference still needs validation.'):'Cloud setup incomplete.')+'\nReal evidence: '+r.real_evidence_records+' records. Historical station-days: '+(Object.entries(r.history_station_days).map(([k,v])=>k+': '+v).join(', ')||'0')+'\n'+r.blockers.map(x=>'• '+x).join('\n')+(state.model_access?'\nModel access: '+(state.model_access.reason||Object.values(state.model_access.models||{}).map(m=>m.model+': '+(m.listed?'listed':'not listed')).join('; ')):'');}
  if(state.historical){const h=state.historical;const a=h.arms.statistical_baseline;$('historical-summary').textContent=`${h.cases} days · ${h.seconds.toFixed(3)} seconds · ${(h.python_peak_bytes/1024).toFixed(0)} KB traced Python peak · Baseline Brier ${a.mean_brier.toFixed(4)} · ${a.yes_outcomes} YES / ${a.no_outcomes} NO outcomes. Actual LLM calls: 0.`;}
  if(state.recent_historical){const h=state.recent_historical;$('recent-historical-summary').textContent=`Recent archive: ${h.period} / ${h.test_station_days} test station-days / ${h.calibration_station_days} earlier calibration days. Baseline Brier: ${Object.entries(h.baseline).map(([k,v])=>k+' '+v.mean_brier.toFixed(4)).join(', ')}. Cloud: ${h.cloud.validated_calls} validated calls; ${h.cloud.provider_code||h.cloud.status}. Assumed archive availability; weather accuracy only, no historical trades.`;}
  if(state.recent_historical?.market_inputs){const m=state.recent_historical.market_inputs;$('historical-market-inputs').textContent=`US market archive: ${m.markets} contracts / ${m.price_points} historical display prices / ${m.settlements} verified settlements. Historical depth and reference-wallet signals unavailable; no simulated fills.`;}
  renderHistoricalComparison();
  renderProfitability();
  const session=state.session;
  $('session-badge').textContent=session?(session.alive?'Running':'Stopped')+' · '+(session.mode==='demo'?'SAMPLE':'PUBLIC DATA'):'Stopped';
  $('session-badge').className=session?.alive?'active':'';
  $('session-status').textContent=session?`${session.phase} · ${session.frames_published} frames · ${Object.values(session.workers).filter(Boolean).length}/4 workers active · ${session.mode==='demo'?'Accelerated synthetic fixtures; no cloud inference.':('Prospective capture; missing setup/evidence means no trade.'+(state.cloud_enabled?'':' Cloud inference disabled.'))} Ends ${new Date(session.ends_at*1000).toLocaleTimeString()}`:'Awaiting session start.';
  $('session-coverage').textContent=session?.error||session?.notices?.map(n=>n.reason).slice(0,2).join(' · ')||'';
  $('strategies').replaceChildren();
  strategies.forEach(([id,name,description],i)=>{const loaded=state.bots[id],r=currentResults()[id],tr=el('tr'),td=el('td'),wrap=el('div',undefined,'strategy');wrap.append(el('span',String(i+1).padStart(2,'0'),'num'));const text=el('div');text.append(el('b',name),el('small',description));wrap.append(text);td.append(wrap);tr.append(td);let status=r?(r.status==='failed'?'Run failed':r.synthetic?'Sample complete':r.inference==='cloud'?'Cloud replay':'Test-model replay'):(loaded?'Ready':'Not loaded');if(state.session?.alive){status=state.session.workers[id]?(r?.frames_processed?'Running · '+r.frames_processed+' frames':'Waiting for data'):'Starting'}const statusCell=el('td',status);if(r?.heartbeat_at){statusCell.append(el('small','Updated '+Math.max(0,Math.floor(Date.now()/1000-r.heartbeat_at))+'s ago','risk-run'));const last=r.journal?.slice(-1)[0];if(last)statusCell.append(el('small',last.kind+': '+last.reason,'worker-reason'))}tr.append(statusCell);const risk=el('td');if(id==='wallet_control'){risk.append(el('span','Fixed control','hint'))}else{const group=el('div',undefined,'risk-picker');group.setAttribute('role','group');group.setAttribute('aria-label',name+' risk profile');const selected=state.settings.risk_profiles?.[id]||loaded?.manifest.config.risk_profile||'balanced';for(const profile of ['reliable','balanced','risky']){const button=el('button',profile[0].toUpperCase()+profile.slice(1));button.type='button';button.setAttribute('aria-pressed',String(selected===profile));button.onclick=()=>post('/api/risk',{strategy:id,profile});group.append(button)}risk.append(group);if(r)risk.append(el('small',(r.status==='running'?'This session: ':'Last run: ')+(r.config.risk_profile||'balanced'),'risk-run'))}tr.append(risk);['cash','open_value','realized_pnl','model_cost'].forEach(k=>tr.append(el('td',money(r?.[k]))));Array.from(tr.children).forEach((cell,index)=>cell.dataset.label=['Strategy','Status','Risk profile','Cash','Open value','Realized P&L','Model cost'][index]);$('strategies').append(tr)});
  if(!$('settings-form').contains(document.activeElement)){$('wallet').value=state.settings.wallet;$('control-mode').value=state.settings.control_mode;}
  $('cloud-status').textContent=state.cloud_enabled?'Cloud enabled locally. Calls still require a key, valid prices and available budget.':'Cloud calls are disabled until configured.';
  $('data-status').textContent=(state.dataset?`${state.dataset.frames} recorded frames${state.dataset.synthetic?' · synthetic':''}`:'No recorded dataset')+` · ${state.evidence_count} evidence records indexed`+(state.strategy_library?` / ${state.strategy_library.total_revisions} strategy-library revisions (not proof of profit)`:"");
  $('coverage-detail').textContent=state.dataset?JSON.stringify({coverage:state.dataset.coverage,errors:state.dataset.errors},null,2):'No capture loaded.';
  const results=Object.values(currentResults());$('results-label').hidden=!results.length;
  if(results.length)$('results-label').textContent=results.every(r=>r.synthetic)?'SYNTHETIC DEMO · Test-model outputs · These numbers are not evidence of trading performance.':`${state.session?.mode==='public'?'Public paper session':'Recorded data replay'} · ${results.reduce((n,r)=>n+(r.cloud_connection_validated?r.validated_model_calls:0),0)} validated cloud calls · Review coverage and skipped decisions.`;
  $('research-results').hidden=!results.length;
  const table=el('table'),head=el('tr');['Strategy','Net after all costs','Brier score','Station-days','Unmarked positions'].forEach(t=>head.append(el('th',t)));const thead=el('thead');thead.append(head);table.append(thead);const tbody=el('tbody');strategies.forEach(([id,name])=>{const r=currentResults()[id];if(!r)return;const tr=el('tr');[name,money(r.net_after_costs),r.mean_brier===null?'—':r.mean_brier.toFixed(4),r.independent_station_days,r.unmarked_positions].forEach(t=>tr.append(el('td',String(t))));tbody.append(tr)});table.append(tbody);$('scores').replaceChildren(table);renderJournal();
}
function renderJournal(){const expanded=new Set(Array.from($('journal').querySelectorAll('details[open]')).map(n=>n.dataset.key));const filter=$('journal-filter').value;const entries=[];for(const [id,name] of strategies){if(filter!=='all'&&filter!==id)continue;const r=currentResults()[id];if(!r)continue;for(const j of r.journal||[])entries.push({...j,name});if(r.error)entries.push({kind:'failure',reason:r.error,name,at:r.created_at})}entries.sort((a,b)=>b.at-a.at);$('journal').replaceChildren();if(!entries.length){$('journal').append(el('p','Upload a package, then run a replay to inspect decisions.','empty'));return}for(const j of entries.slice(0,50)){const box=el('div',undefined,'journal-item');box.append(el('strong',`${j.name} · ${j.kind}`),el('time',new Date(j.at*1000).toISOString().replace('T',' ').slice(0,19)+' UTC'),el('p',j.reason));if(j.audit){const d=el('details'),s=el('summary','Model, route & evidence audit');d.dataset.key=j.name+'/'+j.at;d.open=expanded.has(d.dataset.key);d.append(s,el('pre',JSON.stringify(j.audit,null,2)));box.append(d)}$('journal').append(box)}}
for(const [id,name] of strategies){const o=el('option',name);o.value=id;$('journal-filter').append(o)}
$('journal-filter').addEventListener('change',renderJournal);
$('upload').onclick=()=>$('zip-file').click();
$('zip-file').onchange=async e=>{for(const file of e.target.files){await post('/api/upload',file,true)}e.target.value=''};
$('settings-form').onsubmit=e=>{e.preventDefault();post('/api/settings',{wallet:$('wallet').value,control_mode:$('control-mode').value})};
$('source').onchange=()=>{$('run').textContent={sample:'Replay sample',recorded:'Replay test model',cloud:'Replay cloud'}[$('source').value]};
$('run').onclick=()=>{notice('Running isolated paper accounts on the same dataset…');post('/api/run',{source:$('source').value})};
$('capture').onclick=()=>{notice('Collecting a bounded public-data sample. Coverage notices will be retained.');post('/api/capture',{})};
for(const [button,input,path] of [['data-upload','dataset-file','/api/dataset'],['rag-upload','evidence-file','/api/evidence']]){$(button).onclick=()=>$(input).click();$(input).onchange=async e=>{if(e.target.files[0])await post(path,e.target.files[0],true);e.target.value=''}}
refresh().catch(e=>notice(e.message,true));
$('start-demo').onclick=()=>post('/api/session/start',{mode:'demo',duration:Number($('session-duration').value)});
$('start-public').onclick=()=>post('/api/session/start',{mode:'public',duration:Number($('session-duration').value)});
$('stop-session').onclick=()=>post('/api/session/stop',{});
setInterval(()=>{if(!busy)refresh().catch(e=>notice(e.message,true))},2000);

$('account-connect').onclick=()=>post('/api/account/connect',{});
$('account-refresh').onclick=()=>post('/api/account/refresh',{});
$('account-disconnect').onclick=()=>post('/api/account/disconnect',{});

$('readiness-refresh').onclick=()=>post('/api/readiness',{});
$('model-check').onclick=()=>post('/api/models/check',{});
$('collect-evidence').onclick=()=>{notice('Collecting public rules and future-day forecasts. This may take a minute.');post('/api/research/collect',{})};

$('historical-run').onclick=()=>post('/api/historical/baseline',{});

function renderStudy(){
  const s=state.disagreement;
  if(!s){$('study-status').textContent='Restart the dashboard server to load the tracker update.';return}
  if(!$('shortcuts-folder-form').contains(document.activeElement))$('shortcuts-folder').value=s.shortcuts?.folder||'';
  const r=s.latest, fmt=v=>v===null||v===undefined?'—':Number(v).toFixed(1)+'°F';
  $('study-status').textContent=(s.running?'Collecting':'Stopped')+' · '+s.snapshots+' snapshots this session · '+(s.shortcuts?.configured?'Synced folder connected':'iCloud folder not connected — see Shortcuts setup')+(s.error?' · '+s.error:'');
  $('study-markets').replaceChildren();$('apple-attribution').replaceChildren();
  if(!r){$('study-weather').textContent='Waiting for an automatic Apple Weather export from your iPhone. Follow Shortcuts setup once; temperatures are then retrieved and saved automatically.';return}
  const a=r.apple,n=r.nws_forecast,o=r.nws_observation;
  const fresh=a&&r.apple_fresh&&Date.now()/1000<a.expires_at;
  $('study-weather').textContent=`${r.station} / ${r.date} · Captured ${new Date(r.finished_at*1000).toLocaleString()} · Apple daily high: ${fmt(a?.high_f)}${a&&!fresh?' (expired)':''} · NWS forecast high: ${fmt(n?.high_f)} · Latest NWS observation: ${fmt(o?.temperature_f)}${o?' at '+new Date(o.observed_at*1000).toLocaleString():''} · Final CLI daily high: pending review. `+(a?.notice||'Apple data missing.');
  if(a?.logo_url&&a?.attribution_url){try{const logo=new URL(a.logo_url),legal=new URL(a.attribution_url);if(logo.origin==='https://weatherkit.apple.com'&&legal.protocol==='https:'){const link=el('a');link.href=legal.href;link.target='_blank';link.rel='noreferrer';const img=el('img');img.src=logo.href;img.alt='Apple Weather';img.width=130;link.append(img,el('span',' Data sources'));$('apple-attribution').append(link)}}catch(_){}}
  for(const m of r.markets){const tr=el('tr'),match=x=>x===null?'—':x?'Yes':'No';
    const bin=m.lower_f===null?'≤ '+m.upper_f:m.upper_f===null?'≥ '+m.lower_f:m.lower_f===m.upper_f?String(m.lower_f):m.lower_f+'–'+m.upper_f;
    const stale=Date.now()/1000-m.compared_at>10;
    const shares=v=>v===null||v===undefined?'—':Number(v).toLocaleString('en-US',{maximumFractionDigits:2});
    [bin,match(fresh?m.apple_match:null),match(m.nws_match),money(m.best_bid)+' / '+money(m.best_ask),shares(m.ask_shares),shares(m.ask_shares_within_2c),m.break_even_probability===undefined?'—':(m.break_even_probability*100).toFixed(1)+'%',(stale?'Archived snapshot. ':'')+m.status].forEach(v=>tr.append(el('td',String(v))));$('study-markets').append(tr);
  }
  $('study-audit').textContent=JSON.stringify({snapshot:r.snapshot_path,errors:r.errors,inventory_complete:r.inventory_complete,matching_contracts:r.matching_contracts,contracts_truncated:r.contracts_truncated,complete_partition:r.complete_partition,comparison_aligned:r.comparison_aligned,apple_minus_nws_forecast_f:r.apple_minus_nws_forecast_f,trade_enabled:false,individual_order_count:'Unavailable; quantities are shares, not orders',sampling:'Every 5 minutes; bounded snapshots, no continuous-fill claim'},null,2);
}
const today=new Date();$('study-date').value=today.getFullYear()+'-'+String(today.getMonth()+1).padStart(2,'0')+'-'+String(today.getDate()).padStart(2,'0');
$('weather-study-form').onsubmit=e=>{e.preventDefault();post('/api/disagreement/start',{station:$('study-station').value,date:$('study-date').value,apple_mode:'shortcuts',duration:Number($('study-duration').value),interval:300})};
$('study-stop').onclick=()=>post('/api/disagreement/stop',{});

$('shortcuts-folder-form').onsubmit=e=>{e.preventDefault();post('/api/shortcuts/configure',{folder:$('shortcuts-folder').value})};

function renderHistoricalComparison(){
  const h=state.recent_historical?.comparison,box=$('historical-comparison');box.hidden=!h;if(!h)return;
  $('historical-chart-caption').textContent=`${h.period} / ${h.paired_station_days} shared station-days across ${h.paired_calendar_days} dates. Mean Brier error: lower is better. Whiskers: descriptive 95% day-block bootstrap. ${h.validated_calls} validated calls. ${h.status==='complete'?'All stations processed.':'Partial run; results may change.'}`;
  const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');
  function shape(tag,attrs,text){const n=document.createElementNS(ns,tag);for(const [k,v] of Object.entries(attrs))n.setAttribute(k,String(v));if(text!==undefined)n.textContent=text;svg.append(n);return n}
  svg.setAttribute('viewBox','0 0 900 315');svg.setAttribute('role','img');svg.setAttribute('aria-label','Mean Brier forecast error on identical historical cases, lower is better');
  const left=230,width=500,valid=h.arms.filter(a=>a.paired_brier!==null),max=Math.max(.1,...valid.map(a=>a.paired_interval?.[1]||a.paired_brier))*1.18;
  for(let i=0;i<=4;i++){const x=left+i*width/4;shape('line',{x1:x,y1:24,x2:x,y2:247,stroke:'#504b52'});shape('text',{x,y:275,fill:'#eee','text-anchor':'middle'},(i*max/4).toFixed(2))}
  h.arms.forEach((a,i)=>{const y=38+i*52;shape('text',{x:214,y:y+20,fill:'#eee','text-anchor':'end'},a.name);if(a.paired_brier===null){shape('text',{x:left+8,y:y+20,fill:'#ddd'},'No shared scored cases');return}const x=left+width*a.paired_brier/max;shape('rect',{x:left,y,width:x-left,height:30,fill:i===0?'#a9a4ac':'#dfacd2'});if(a.paired_interval){const lo=left+width*a.paired_interval[0]/max,hi=left+width*a.paired_interval[1]/max;shape('line',{x1:lo,y1:y+15,x2:hi,y2:y+15,stroke:'#fff','stroke-width':2});for(const xx of [lo,hi])shape('line',{x1:xx,y1:y+9,x2:xx,y2:y+21,stroke:'#fff','stroke-width':2})}shape('text',{x:755,y:y+20,fill:'#fff'},a.paired_brier.toFixed(4))});
  shape('text',{x:left+width/2,y:304,fill:'#eee','text-anchor':'middle'},'Mean Brier error (0 = perfect)');$('historical-chart').replaceChildren(svg);
  const table=el('table'),tr=el('tr');['Model','Scored / 50','Shared-case accuracy','All scored Brier'].forEach(x=>tr.append(el('th',x)));const head=el('thead');head.append(tr);table.append(head);const body=el('tbody');for(const a of h.arms){const row=el('tr');[a.name,`${a.scored} / ${a.expected}`,a.paired_accuracy===null?'—':(100*a.paired_accuracy).toFixed(1)+'%',a.mean_brier_all===null?'—':a.mean_brier_all.toFixed(4)].forEach(x=>row.append(el('td',x)));body.append(row)}table.append(body);$('historical-coverage').replaceChildren(table,el('p','Unequal all-case coverage is not a fair ranking. Shared-case filtering also excludes abstentions and can bias the comparison. Ten dates are exploratory.','hint'));
}

function renderProfitability(){
  const dollars=v=>new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',minimumFractionDigits:2,maximumFractionDigits:2}).format(v);
  const r=state.recent_historical?.profitability;
  $('profitability').hidden=!r;
  if(!r)return;
  const slip=Number($('profitability-slippage').value);
  $('profitability-caption').textContent=`${r.preparation.eligible} exact contracts / September 6-15, 2026 / ${r.validated_calls} validated cloud responses. Each arm starts with $50 and keeps $40 in reserve. Additional entry cost: ${(100*slip).toFixed(0)} cents/share. Overhead: ${dollars(r.overhead_per_arm)} per arm over ${r.overhead_days.toFixed(2)} days. Exploratory reused dates; assumed archive availability.`;
  const rows=r.arms.map(a=>({a,s:a.scenarios.find(s=>s.slippage_per_share===slip)}));
  const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 900 310');svg.setAttribute('role','img');svg.setAttribute('aria-label','Hypothetical return after fees and model costs, excluding subscription overhead');
  const add=(tag,attrs,text)=>{const n=document.createElementNS(svg.namespaceURI,tag);for(const [k,v] of Object.entries(attrs))n.setAttribute(k,String(v));if(text!==undefined)n.textContent=text;svg.append(n);return n};
  const vals=rows.map(x=>x.s.pnl_after_models),lo=Math.min(0,...vals)-1,hi=Math.max(0,...vals)+1,px=v=>220+(v-lo)/(hi-lo)*570;
  for(let i=0;i<=4;i++){const v=lo+(hi-lo)*i/4;add('line',{x1:px(v),x2:px(v),y1:20,y2:264,stroke:'#514a52'});add('text',{x:px(v),y:286,fill:'#eee','text-anchor':'middle'},'$'+v.toFixed(1));}
  add('line',{x1:px(0),x2:px(0),y1:20,y2:264,stroke:'#fff'});
  rows.forEach(({a,s},i)=>{const y=40+i*46;add('text',{x:205,y:y+5,fill:'#fff','text-anchor':'end'},a.name);add('rect',{x:Math.min(px(0),px(s.pnl_after_models)),y:y-12,width:Math.max(1,Math.abs(px(s.pnl_after_models)-px(0))),height:24,fill:s.pnl_after_models<0?'#d997aa':'#abd1ad'});add('text',{x:880,y:y+5,fill:'#fff','text-anchor':'end'},dollars(s.pnl_after_models));});
  add('text',{x:500,y:308,fill:'#fff','text-anchor':'middle'},'P&L after fees and model costs / excludes overhead');$('profitability-chart').replaceChildren(svg);
  const table=el('table'),head=el('tr');['Method','Forecasts / 50','Trades','Win rate','Trading P&L','Model cost*','Net incl. overhead'].forEach(t=>head.append(el('th',t)));const thead=el('thead');thead.append(head);table.append(thead);const body=el('tbody');
  rows.forEach(({a,s})=>{const tr=el('tr');[a.name,a.scored+' / 50',s.trades,s.win_rate===null?'No trades':(100*s.win_rate).toFixed(1)+'%',dollars(s.trading_pnl),dollars(a.model_cost_or_reserved_usd),dollars(s.net_after_all_costs)].forEach(v=>tr.append(el('td',String(v))));body.append(tr)});table.append(body);$('profitability-table').replaceChildren(table,el('p','*Includes known failed-call usage and unresolved reservations; estimates, not invoices. Trading P&L includes fees and the selected entry-price assumption.','hint'));
}
$('profitability-slippage').addEventListener('change',renderProfitability);
