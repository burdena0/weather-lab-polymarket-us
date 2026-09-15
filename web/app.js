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
  const account=state.account||{status:'disconnected'};
  $('account-badge').textContent=account.status==='connected'?'Verified / read only':account.status;
  $('account-balance').textContent=money(account.current_balance);
  $('account-power').textContent=money(account.buying_power);
  $('account-positions').textContent=account.positions_count===null||account.positions_count===undefined?'—':String(account.positions_count)+(account.positions_complete?'':' +');
  $('account-status').textContent=account.error||(account.status==='connected'?'Verified '+new Date(account.checked_at*1000).toLocaleString()+'. '+(account.positions_notice||(!account.positions_complete?'Position coverage is partial.':'')):account.status==='unverified'?'Saved link. Refresh to verify this session.':'Link your local saved credentials to view an account snapshot.');
  $('account-connect').hidden=!!account.linked;
  $('account-refresh').hidden=!account.linked;
  $('account-disconnect').hidden=!account.linked;
  const session=state.session;
  $('session-badge').textContent=session?(session.alive?'Running':'Stopped')+' · '+(session.mode==='demo'?'SAMPLE':'PUBLIC DATA'):'Stopped';
  $('session-badge').className=session?.alive?'active':'';
  $('session-status').textContent=session?`${session.phase} · ${session.frames_published} frames · ${Object.values(session.workers).filter(Boolean).length}/4 workers active · ${session.mode==='demo'?'Accelerated synthetic fixtures; no cloud inference.':('Prospective capture; missing setup/evidence means no trade.'+(state.cloud_enabled?'':' Cloud inference disabled.'))} Ends ${new Date(session.ends_at*1000).toLocaleTimeString()}`:'Awaiting session start.';
  $('session-coverage').textContent=session?.error||session?.notices?.map(n=>n.reason).slice(0,2).join(' · ')||'';
  $('strategies').replaceChildren();
  strategies.forEach(([id,name,description],i)=>{const loaded=state.bots[id],r=currentResults()[id],tr=el('tr'),td=el('td'),wrap=el('div',undefined,'strategy');wrap.append(el('span',String(i+1).padStart(2,'0'),'num'));const text=el('div');text.append(el('b',name),el('small',description));wrap.append(text);td.append(wrap);tr.append(td);let status=r?(r.status==='failed'?'Run failed':r.synthetic?'Sample complete':r.inference==='cloud'?'Cloud replay':'Test-model replay'):(loaded?'Ready':'Not loaded');if(state.session?.alive){status=state.session.workers[id]?(r?.frames_processed?'Running · '+r.frames_processed+' frames':'Waiting for data'):'Starting'}const statusCell=el('td',status);if(r?.heartbeat_at){statusCell.append(el('small','Updated '+Math.max(0,Math.floor(Date.now()/1000-r.heartbeat_at))+'s ago','risk-run'));const last=r.journal?.slice(-1)[0];if(last)statusCell.append(el('small',last.kind+': '+last.reason,'worker-reason'))}tr.append(statusCell);const risk=el('td');if(id==='wallet_control'){risk.append(el('span','Fixed control','hint'))}else{const group=el('div',undefined,'risk-picker');group.setAttribute('role','group');group.setAttribute('aria-label',name+' risk profile');const selected=state.settings.risk_profiles?.[id]||loaded?.manifest.config.risk_profile||'balanced';for(const profile of ['reliable','balanced','risky']){const button=el('button',profile[0].toUpperCase()+profile.slice(1));button.type='button';button.setAttribute('aria-pressed',String(selected===profile));button.onclick=()=>post('/api/risk',{strategy:id,profile});group.append(button)}risk.append(group);if(r)risk.append(el('small',(r.status==='running'?'This session: ':'Last run: ')+(r.config.risk_profile||'balanced'),'risk-run'))}tr.append(risk);['cash','open_value','realized_pnl','model_cost'].forEach(k=>tr.append(el('td',money(r?.[k]))));Array.from(tr.children).forEach((cell,index)=>cell.dataset.label=['Strategy','Status','Risk profile','Cash','Open value','Realized P&L','Model cost'][index]);$('strategies').append(tr)});
  if(!$('settings-form').contains(document.activeElement)){$('wallet').value=state.settings.wallet;$('control-mode').value=state.settings.control_mode;}
  $('cloud-status').textContent=state.cloud_enabled?'Cloud enabled locally. Calls still require a key, valid prices and available budget.':'Cloud calls are disabled until configured.';
  $('data-status').textContent=(state.dataset?`${state.dataset.frames} recorded frames${state.dataset.synthetic?' · synthetic':''}`:'No recorded dataset')+` · ${state.evidence_count} evidence records indexed`;
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
