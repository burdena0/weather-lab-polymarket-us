'use strict';
// Local ES256 signing using Node's built-in crypto; no network or npm modules.
const crypto = require('node:crypto');
let input = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', chunk => { input += chunk; if (input.length > 16384) process.exit(1); });
process.stdin.on('end', () => {
  try {
    const {privateKey, team, keyId, service, now} = JSON.parse(input);
    if (!/^[A-Z0-9]{10}$/.test(team) || !/^[A-Z0-9]{10}$/.test(keyId) ||
        !/^[A-Za-z0-9.-]{3,200}$/.test(service) || !Number.isInteger(now)) throw Error();
    const key = crypto.createPrivateKey(privateKey);
    if (key.asymmetricKeyType !== 'ec' || key.asymmetricKeyDetails.namedCurve !== 'prime256v1') throw Error();
    const enc = obj => Buffer.from(JSON.stringify(obj)).toString('base64url');
    const unsigned = enc({alg:'ES256',kid:keyId,id:team+'.'+service})+'.'+
      enc({iss:team,iat:now,exp:now+1200,sub:service});
    const signature = crypto.sign('sha256',Buffer.from(unsigned),{key,dsaEncoding:'ieee-p1363'});
    process.stdout.write(unsigned+'.'+signature.toString('base64url'));
  } catch (_) { process.stderr.write('WeatherKit signing failed'); process.exitCode=1; }
});
