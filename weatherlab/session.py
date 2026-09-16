"""Bounded background paper sessions; independent accounts, no exchange orders."""
import copy
import json
import queue
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from .core import identity
from .engine import replay, validate_config
from .fixtures import sample, WALLET
from .sources import capture


class Session:
    def __init__(self, root, configs, mode, rag, budget_path, wallet='', mappings=None, duration=3600):
        if mode not in ('demo', 'public') or not 10 <= duration <= 14400:
            raise ValueError('Select demo/public session, duration 10 seconds to four hours')
        self.configs = copy.deepcopy(configs)
        for config in self.configs.values():
            validate_config(config)
            if mode == 'demo':
                config.pop('research_protocol', None)
        self.mode, self.rag, self.budget_path = mode, rag, budget_path
        self.wallet, self.mappings, self.duration = wallet, mappings or [], duration
        self.id = 'session-'+str(uuid.uuid4())[:12]
        self.root = Path(root)/self.id
        self.root.mkdir(parents=True, exist_ok=False)
        self.started = time.time()
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.queues = {key:queue.Queue(maxsize=1) for key in configs}
        self.results, self.workers = {}, {}
        self.dropped = {key:0 for key in configs}
        self.phase, self.error, self.frames, self.cycle = 'starting', None, 0, 0
        self.coverage, self.notices = {}, []
        self.last_source_at = None
        self.thread = threading.Thread(target=self._run, name='weatherlab-paper-session', daemon=True)
        (self.root/'session.json').write_text(json.dumps({'id':self.id,'mode':mode,'started':self.started,
            'duration':duration,'configs':self.configs,'execution':'paper_only'},indent=2),encoding='utf-8')

    def start(self):
        self.thread.start()

    def state(self):
        with self.lock:
            return {'id':self.id,'mode':self.mode,'phase':self.phase,'error':self.error,
                    'alive':self.thread.is_alive(),'started_at':self.started,'ends_at':self.started+self.duration,
                    'frames_published':self.frames,'demo_cycle':self.cycle,'last_source_at':self.last_source_at,
                    'coverage':copy.deepcopy(self.coverage),'notices':list(self.notices[-8:]),
                    'dropped_frames':dict(self.dropped),'workers':{k:t.is_alive() for k,t in self.workers.items()},
                    'results':copy.deepcopy(self.results)}

    def _update(self, key, result):
        with self.lock:
            self.results[key] = result
            if result.get('status') == 'failed':
                self.error = 'Worker '+key+' failed: '+str(result.get('error'))[:180]
                self.stop.set()

    def _frames(self, key):
        while not self.stop.is_set():
            try:
                frame = self.queues[key].get(timeout=.5)
            except queue.Empty:
                continue
            if self.mode == 'public':
                # Never backdate decisions queued while another inference was in flight.
                frame['at'] = max(frame['at'], time.time())
            yield frame

    def _worker(self, key):
        try:
            data, _ = sample()
            header = {'schema_version':1,'venue':'polymarket_us','synthetic':self.mode=='demo',
                      'frames':[], 'started_at':data['frames'][0]['at'] if self.mode=='demo' else self.started}
            config = self.configs[key]
            if self.mode == 'demo':
                config['reference_wallet'] = WALLET
            replay(config, header, self.root/key, cloud=self.mode=='public' and key!='wallet_control',
                   rag=self.rag if self.mode=='public' else None, budget_path=self.budget_path,
                   frame_stream=self._frames(key), on_update=lambda r:self._update(key,r), duration=self.duration+60, stop_event=self.stop)
        except Exception as exc:
            with self.lock:
                self.error = 'Worker '+key+' failed: '+type(exc).__name__+': '+str(exc)[:150]
            self.stop.set()

    def _publish(self, frame):
        with self.lock:
            self.frames += 1
            self.last_source_at = time.time()
        for key, inbox in self.queues.items():
            try:
                inbox.put_nowait(copy.deepcopy(frame))
            except queue.Full:
                try:
                    inbox.get_nowait()
                except queue.Empty:
                    pass
                with self.lock:
                    self.dropped[key] += 1
                inbox.put_nowait(copy.deepcopy(frame))

    def _demo_frames(self):
        data, _ = sample()
        for original in data['frames']:
            f = copy.deepcopy(original)
            offset = (self.cycle-1)*90020
            f['at'] += offset
            for m in f['markets']:
                m['id'] += '-'+str(self.cycle)
                m['slug'] += '-'+str(self.cycle)
                m['date'] = datetime.fromtimestamp(data['frames'][0]['at']+86400+offset,timezone.utc).date().isoformat()
                m['metadata_received'] += offset
                m['close_at'] += offset
                m['forecast']['date'] = m['date']
                for key in ('issued_at','received_at'):
                    m['forecast'][key] += offset
                m['book']['slug'] = m['slug']
                for key in ('received','source_at'):
                    m['book'][key] += offset
            for s in f['signals']:
                s['id'] += '-'+str(self.cycle)
                s['slug'] = f['markets'][0]['slug']
                s['us_market_id'] = f['markets'][0]['id']
                s['contract_identity'] = identity(f['markets'][0])
                s['trade_at'] += offset
                s['received_at'] += offset
            for s in f['settlements']:
                s['slug'] += '-'+str(self.cycle)
                s['market_id'] += '-'+str(self.cycle)
                s['received_at'] += offset
                s['yes_payout'] = self.cycle % 2  # Alternating synthetic outcomes; no performance claim.
            yield f

    def _run(self):
        try:
            with self.lock:
                self.phase = 'running'
                for key in self.configs:
                    worker = threading.Thread(target=self._worker,args=(key,),name='paper-'+key,daemon=True)
                    self.workers[key] = worker
                    worker.start()
            empty_windows = 0
            while not self.stop.is_set() and time.time()-self.started < self.duration:
                self.cycle += 1
                if self.mode == 'demo':
                    for frame in self._demo_frames():
                        if self.stop.is_set() or time.time()-self.started >= self.duration:
                            break
                        self._publish(frame)
                        if self.stop.wait(3):
                            break
                else:
                    result = capture(self.root/'captures'/str(self.cycle),seconds=45,max_markets=4,
                                     wallet=self.wallet,mappings=self.mappings,on_frame=self._publish,stop_event=self.stop)
                    with self.lock:
                        self.coverage = result['coverage']
                        self.notices = result['errors'][-8:]
                    empty_windows = empty_windows+1 if not result['frames'] else 0
                    if empty_windows >= 3:
                        raise ValueError('Three empty capture windows; inspect source notices before restarting')
                    if self.stop.wait(5):
                        break
        except Exception as exc:
            with self.lock:
                self.error = type(exc).__name__+': '+str(exc)[:180]
        finally:
            self.stop.set()
            with self.lock:
                self.phase = 'stopping'
            for worker in self.workers.values():
                worker.join(timeout=60)
            with self.lock:
                if any(t.is_alive() for t in self.workers.values()):
                    self.error = 'Worker did not stop within its bounded timeout; do not start another session'
                self.phase = 'failed' if self.error else 'stopped'
            (self.root/'final-state.json').write_text(json.dumps(self.state(),indent=2),encoding='utf-8')
