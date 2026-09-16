import copy
import hashlib
import json
import os
import base64
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from weatherlab.disagreement import (manual_record, parse_apple, observation, compare_market,
    score_snapshot, DisagreementStudy, collect_snapshot, apple_token, weatherkit_get)
from weatherlab.fixtures import sample


class DisagreementTests(unittest.TestCase):
    def setUp(self):
        data, _ = sample()
        self.now = data['frames'][0]['at']
        self.market = copy.deepcopy(data['frames'][0]['markets'][0])
        self.market.update(lower_f=79, upper_f=81, day_start=1000, close_at=87400)
        self.apple = {'station':self.market['station'],'date':self.market['date'],'high_f':80,
            'received_at':self.now-5, 'expires_at':self.now+300}

    def test_manual_rejects_future_backdating_and_nonfinite(self):
        b={'station':'KLAX','date':'2026-09-17','high_f':80,'location':'LAX airport','viewed_at':995}
        row=manual_record(b,1000)
        self.assertEqual(row['received_at'],1000)
        self.assertFalse(row['location_verified'])
        for field,value in [('viewed_at',1001),('viewed_at',1),('high_f',float('nan'))]:
            with self.assertRaises(ValueError):manual_record(dict(b,**{field:value}),1000)

    def apple_raw(self):
        return {'forecastDaily':{'metadata':{'units':'m','latitude':34,'longitude':-118,'readTime':900,'expireTime':1200},
            'days':[{'forecastStart':1000,'forecastEnd':87400,'temperatureMax':25}]}}

    def test_apple_units_coordinates_intervals_and_expiry(self):
        raw=self.apple_raw()
        self.assertEqual(parse_apple(raw,self.market,34,-118,950)['high_f'],77)
        for section,field,value in [('metadata','units','e'),('metadata','expireTime',940),
            ('metadata','readTime',960),('metadata','latitude',35),('days','forecastStart',4600)]:
            bad=copy.deepcopy(raw); target=bad['forecastDaily'][section]
            (target[0] if isinstance(target,list) else target)[field]=value
            with self.assertRaises(ValueError):parse_apple(bad,self.market,34,-118,950)

    def test_observation_is_quality_checked_current_temperature(self):
        raw={'properties':{'station':'https://api.weather.gov/stations/KLAX','timestamp':900,
            'temperature':{'unitCode':'wmoUnit:degC','value':20,'qualityControl':'V'}}}
        self.assertEqual(observation(raw,'KLAX',1000)['temperature_f'],68)
        for station,at in [('KNYC',1000),('KLAX',800),('KLAX',10000)]:
            with self.assertRaises(ValueError):observation(raw,station,at)
        raw['properties']['temperature']['qualityControl']='X'
        with self.assertRaises(ValueError):observation(raw,'KLAX',1000)

    def valid_book(self):
        m=self.market
        m['close_at']=self.now+86400
        m['metadata_received']=self.now
        m['minimum_qty']=1;m['tick']=.01
        m['book']={'slug':m['slug'],'state':'OPEN','source_at':self.now,'received':self.now,
            'bids':[[.3,12]],'asks':[[.4,10],[.41,20],[.5,50]]}
        return m

    def test_depth_is_shares_not_orders_and_price_is_not_forecast_probability(self):
        m=self.valid_book()
        nws={'high_f':85,'received_at':self.now,'issued_at':self.now-1}
        row=compare_market(m,self.apple,nws,self.now)
        self.assertEqual(row['ask_shares'],80)
        self.assertEqual(row['ask_shares_within_2c'],30)
        self.assertEqual(row['ask_levels'],3)
        self.assertIsNone(row['individual_order_count'])
        self.assertTrue(row['forecast_disagreement'])
        self.assertGreater(row['break_even_probability'],.4)
        self.assertNotIn('expected_profit',row)

    def test_expired_apple_and_future_nws_cannot_generate_matches(self):
        m=self.valid_book()
        a=dict(self.apple,expires_at=self.now)
        nws={'high_f':85,'received_at':self.now+1,'issued_at':self.now}
        row=compare_market(m,a,nws,self.now)
        self.assertIsNone(row['apple_match']);self.assertIsNone(row['nws_match'])
        self.assertIsNone(row['forecast_disagreement'])

    def test_stale_or_insufficient_book_is_not_executable(self):
        m=self.valid_book();m['book']['source_at']=self.now-121
        self.assertFalse(compare_market(m,self.apple,None,self.now)['executable'])
        m=self.valid_book();m['book']['asks']=[[.4,.1]]
        row=compare_market(m,self.apple,None,self.now)
        self.assertFalse(row['executable']);self.assertNotIn('break_even_probability',row)

    def test_missing_sources_retained_without_fake_apple_or_prices(self):
        class Missing:
            def __init__(self,*args,**kwargs):pass
            def inventory(self):return [],1000,True
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'snapshot'
            r=collect_snapshot(root,'KLAX','2026-09-17','manual',source_factory=Missing)
            self.assertIsNone(r['apple']);self.assertEqual(r['markets'],[])
            self.assertFalse(r['trade_enabled']);self.assertTrue(r['errors'])
            self.assertTrue((root/'snapshot.json').exists())
            with self.assertRaises(FileExistsError):collect_snapshot(root,'KLAX','2026-09-17','manual',source_factory=Missing)

    def test_scoring_separate_from_predictions_and_requires_postday_review(self):
        snapshot={'station':'KLAX','date':'2026-09-17','finished_at':100,'day_end':200,
            'apple':{'high_f':80},'apple_fresh':True,'nws_forecast':{'high_f':82}}
        outcome={'station':'KLAX','date':'2026-09-17','reviewed':True,'review_note':'CLI MAXIMUM reviewed',
            'source_url':'https://api.weather.gov/products/test','product_text':'CLI TEST',
            'product_sha256':hashlib.sha256(b'CLI TEST').hexdigest(),
            'published_at':210,'received_at':220,'actual_high_f':81}
        original=copy.deepcopy(snapshot)
        self.assertEqual(score_snapshot(snapshot,outcome,300)['apple_error_f'],-1)
        self.assertEqual(snapshot,original)
        for field,value in [('station','KNYC'),('reviewed',False),('published_at',199),('received_at',301),('actual_high_f',81.5)]:
            with self.assertRaises(ValueError):score_snapshot(snapshot,dict(outcome,**{field:value}),300)
        with self.assertRaises(ValueError):score_snapshot(dict(snapshot,finished_at=230),outcome,300)

    def test_background_sampler_one_snapshot_and_restart_has_no_autorun(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch('weatherlab.disagreement.collect_snapshot',return_value={'test':True}) as collect:
                s=DisagreementStudy(tmp)
                s.start({'station':'KLAX','date':'2026-09-17','duration':1})
                s.thread.join(timeout=3)
                self.assertFalse(s.state()['running']);self.assertEqual(s.state()['snapshots'],1)
                collect.assert_called_once()
                self.assertFalse(DisagreementStudy(tmp).state()['running'])

    def test_private_credentials_do_not_enter_state_and_missing_key_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,{'WEATHERLAB_WEATHERKIT_TOKEN':'private-token'},clear=True):
            state=DisagreementStudy(tmp).state()
            self.assertTrue(state['weatherkit_configured'])
            self.assertNotIn('private-token',json.dumps(state))
        with patch.dict(os.environ,{},clear=True):
            with self.assertRaises(ValueError):apple_token()

    def test_api_errors_do_not_expose_tokens(self):
        with tempfile.TemporaryDirectory() as tmp, patch('urllib.request.build_opener') as opener:
            opener.return_value.open.side_effect=RuntimeError('private-token')
            with self.assertRaises(ValueError) as caught:weatherkit_get('/api/v1/weather/test',tmp,'a.json','private-token')
            self.assertNotIn('private-token',str(caught.exception))
            self.assertEqual(list(Path(tmp).iterdir()),[])

    @unittest.skipUnless(shutil.which('node'), 'Optional Node signer runtime unavailable')
    def test_local_es256_token_signature_and_claims(self):
        # Ephemeral test key stays in process memory / a temporary directory.
        generated=subprocess.run(['node','-e',"const c=require('node:crypto');const k=c.generateKeyPairSync('ec',{namedCurve:'prime256v1'});process.stdout.write(JSON.stringify({privateKey:k.privateKey.export({type:'pkcs8',format:'pem'}),publicKey:k.publicKey.export({type:'spki',format:'pem'})}));"],capture_output=True,text=True,check=True)
        keys=json.loads(generated.stdout)
        with tempfile.TemporaryDirectory() as tmp:
            key=Path(tmp)/'test.p8';key.write_text(keys['privateKey'],encoding='utf-8')
            env={'PATH':os.environ['PATH'],'WEATHERLAB_WEATHERKIT_TOKEN':'',
                'WEATHERLAB_WEATHERKIT_TEAM_ID':'ABCDEFGHIJ','WEATHERLAB_WEATHERKIT_KEY_ID':'0123456789',
                'WEATHERLAB_WEATHERKIT_SERVICE_ID':'test.weather','WEATHERLAB_WEATHERKIT_KEY_PATH':str(key)}
            with patch.dict(os.environ,env):token=apple_token()
            header,payload,sig=token.split('.')
            decode=lambda s:json.loads(base64.urlsafe_b64decode(s+'='*(-len(s)%4)))
            self.assertEqual(decode(header),{'alg':'ES256','kid':'0123456789','id':'ABCDEFGHIJ.test.weather'})
            claims=decode(payload)
            self.assertEqual(claims['exp']-claims['iat'],1200)
            self.assertEqual(claims['sub'],'test.weather')
            script="const c=require('node:crypto');let s='';process.stdin.on('data',x=>s+=x);process.stdin.on('end',()=>{const x=JSON.parse(s),p=x.token.split('.');process.stdout.write(String(c.verify('sha256',Buffer.from(p[0]+'.'+p[1]),{key:x.key,dsaEncoding:'ieee-p1363'},Buffer.from(p[2],'base64url'))));});"
            checked=subprocess.run(['node','-e',script],input=json.dumps({'token':token,'key':keys['publicKey']}),capture_output=True,text=True,check=True)
            self.assertEqual(checked.stdout,'true')


if __name__=='__main__':unittest.main()
