'use strict';
// Secrets enter through stdin only. No network or third-party modules.
const crypto = require('node:crypto');
let input = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', chunk => {
  input += chunk;
  if (input.length > 8192) process.exit(1);
});
process.stdin.on('end', () => {
  try {
    const {seed, message} = JSON.parse(input);
    const raw = Buffer.from(seed, 'base64');
    if (raw.length !== 32 || typeof message !== 'string' || message.length > 1024) throw Error();
    const key = crypto.createPrivateKey({key: Buffer.concat([
      Buffer.from('302e020100300506032b657004220420', 'hex'), raw
    ]), format: 'der', type: 'pkcs8'});
    process.stdout.write(crypto.sign(null, Buffer.from(message, 'utf8'), key).toString('base64'));
  } catch (_) { process.stderr.write('Signing failed'); process.exitCode = 1; }
});
