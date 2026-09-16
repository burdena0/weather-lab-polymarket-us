"""Bounded previous-weeks NOAA archive jobs. Never impersonates Apple history."""
import copy
import json
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from .historical_window import STATIONS, build_window


def window(station, weeks, now):
    if station not in STATIONS or type(weeks) is not int or not 1 <= weeks <= 4:
        raise ValueError('Select a supported station and 1-4 weeks')
    local=datetime.fromtimestamp(now,timezone.utc)-timedelta(hours=STATIONS[station][0])
    end=local.date()-timedelta(days=1)
    start=end-timedelta(days=7*weeks-1)
    return start.isoformat(),end.isoformat()


class ArchiveHistory:
    def __init__(self, root):
        self.root=Path(root);self.lock=threading.Lock();self.thread=None
        path=self.root/'latest.json'
        self.latest=json.loads(path.read_text(encoding='utf-8')) if path.exists() else None
        if self.latest and self.latest['status']=='running':
            self.latest=dict(self.latest,status='interrupted',error='Server stopped before archive job completed')

    def state(self):
        with self.lock:
            return {'running':bool(self.thread and self.thread.is_alive()),'latest':copy.deepcopy(self.latest),
                    'apple_history_available':False,'source':'IEM NOAA GFS MOS and NWS CLI archives'}

    def start(self, station, weeks):
        start,end=window(station,weeks,time.time())
        with self.lock:
            if self.thread and self.thread.is_alive():
                raise ValueError('A historical download is already running')
            self.root.mkdir(parents=True,exist_ok=True)
            folder=self.root/str(uuid.uuid4())
            self.latest={'status':'running','station':station,'start':start,'end':end,'weeks':weeks,
                         'expected_days':7*weeks,'created_at':time.time(), 'archive':str(folder),
                         'source':'NOAA GFS MOS forecast archive + NWS CLI outcomes via IEM; not Apple Weather',
                         'availability_verified':False,'profitability_evaluated':False,'apple_records':0}
            self.save()
            def work():
                try:
                    result=build_window(folder,station,start,end,training_days=0)
                    with self.lock:
                        self.latest.update(status='complete' if result['test_days']==7*weeks else 'partial',
                            days=result['test_days'],errors=result['errors'],finished_at=time.time())
                        self.save()
                except Exception as exc:
                    with self.lock:
                        self.latest.update(status='failed',error=type(exc).__name__+': '+str(exc)[:200],finished_at=time.time())
                        self.save()
            self.thread=threading.Thread(target=work,name='previous-weeks-archive',daemon=True)
            self.thread.start()
        return {'message':f'Downloading {weeks} previous week(s) for {station}. NOAA/NWS archive only; no Apple history or model calls.'}

    def save(self):
        # Caller holds the lock. Each dataset gets its own folder; latest is a pointer.
        target=self.root/'latest.json';temp=target.with_suffix('.tmp')
        temp.write_text(json.dumps(self.latest,indent=2),encoding='utf-8');temp.replace(target)
