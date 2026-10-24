import assert from 'node:assert/strict';
import http from 'node:http';
import { test } from 'node:test';
import { createServer } from 'vite';
import { createApiProxy } from '../proxy-config.js';

const sharedSettings = {
  FEEDBACK_API_URL: 'http://192.168.1.23:8001',
  FEEDBACK_API_TOKEN: 'synthetic-token-for-proxy-tests',
};

function routeFor(proxy, path) {
  const key = Object.keys(proxy).find((route) => (
    route.startsWith('^') ? new RegExp(route).test(path) : path.startsWith(route)
  ));
  return proxy[key];
}

test('default configuration keeps feedback and transcription on the local backend', () => {
  const proxy = createApiProxy();
  assert.deepEqual(Object.keys(proxy), ['/api']);
  assert.equal(routeFor(proxy, '/api/feedback').target, 'http://127.0.0.1:8000');
  assert.equal(routeFor(proxy, '/api/transcribe').target, 'http://127.0.0.1:8000');
  assert.equal(routeFor(proxy, '/api/transcribe').proxyTimeout, 0);
});

test('only the exact feedback endpoint goes to the shared receiver', () => {
  const proxy = createApiProxy(sharedSettings);
  for (const path of ['/api/feedback', '/api/feedback?source=test']) {
    const route = routeFor(proxy, path);
    assert.equal(route.target, sharedSettings.FEEDBACK_API_URL);
    assert.equal(route.rewrite(path), path.replace('/api', ''));
  }
  for (const path of ['/api/transcribe', '/api/suggest-codes', '/api/feedback-other', '/api/feedback/anything']) {
    assert.equal(routeFor(proxy, path).target, 'http://127.0.0.1:8000');
  }
});

test('the shared credential is set by the proxy and is absent from local API calls', () => {
  const proxy = createApiProxy(sharedSettings);
  assert.deepEqual(routeFor(proxy, '/api/feedback').headers, {
    Authorization: `Bearer ${sharedSettings.FEEDBACK_API_TOKEN}`,
  });
  assert.equal(routeFor(proxy, '/api/transcribe').headers, undefined);
});

test('the running proxy sends feedback only to the receiver, including when it becomes unavailable', async (t) => {
  const localRequests = [];
  const sharedRequests = [];
  function makeBackend(requests) {
    return http.createServer(async (request, response) => {
      const chunks = [];
      for await (const chunk of request) chunks.push(chunk);
      requests.push({ url: request.url, authorization: request.headers.authorization, body: Buffer.concat(chunks).toString() });
      response.setHeader('Content-Type', 'application/json');
      response.end(JSON.stringify({ ok: true }));
    });
  }
  async function listen(server) {
    await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
    t.after(() => { server.closeAllConnections(); server.close(); });
    return `http://127.0.0.1:${server.address().port}`;
  }
  const local = makeBackend(localRequests);
  const remote = makeBackend(sharedRequests);
  const localUrl = await listen(local);
  const remoteUrl = await listen(remote);
  const proxy = createApiProxy({ ...sharedSettings, FEEDBACK_API_URL: remoteUrl });
  proxy['/api'].target = localUrl;
  const vite = await createServer({
    configFile: false,
    logLevel: 'silent',
    optimizeDeps: { noDiscovery: true, include: [] },
    server: { host: '127.0.0.1', port: 0, proxy },
  });
  t.after(() => vite.close());
  await vite.listen();
  const origin = `http://127.0.0.1:${vite.httpServer.address().port}`;

  const saved = await fetch(`${origin}/api/feedback`, {
    method: 'POST',
    headers: { Authorization: 'Bearer browser-value-must-not-win' },
    body: JSON.stringify({ code: 'TEST', is_correct: true }),
  });
  assert.equal(saved.status, 200);
  assert.deepEqual(await saved.json(), { ok: true });
  assert.equal(sharedRequests.length, 1);
  assert.equal(sharedRequests[0].url, '/feedback');
  assert.equal(sharedRequests[0].authorization, `Bearer ${sharedSettings.FEEDBACK_API_TOKEN}`);
  assert.deepEqual(JSON.parse(sharedRequests[0].body), { code: 'TEST', is_correct: true });
  assert.equal(localRequests.length, 0);

  const transcription = await fetch(`${origin}/api/transcribe`, { method: 'POST', body: 'audio' });
  assert.equal(transcription.status, 200);
  assert.equal(localRequests.length, 1);
  assert.equal(localRequests[0].url, '/transcribe');
  assert.equal(localRequests[0].authorization, undefined);

  remote.closeAllConnections();
  await new Promise((resolve) => remote.close(resolve));
  const failed = await fetch(`${origin}/api/feedback`, { method: 'POST', body: '{}' });
  assert.equal(failed.status, 500);
  assert.equal(localRequests.length, 1, 'failed remote feedback must not write to the local backend');
});

test('a configured destination without a credential fails instead of using local feedback', () => {
  assert.throws(() => createApiProxy({ FEEDBACK_API_URL: sharedSettings.FEEDBACK_API_URL }), /FEEDBACK_API_TOKEN/);
  assert.throws(() => createApiProxy({ ...sharedSettings, FEEDBACK_API_TOKEN: 'two words' }), /FEEDBACK_API_TOKEN/);
});

test('invalid destinations are rejected without including credentials in errors', () => {
  for (const url of ['not-a-url', 'ftp://receiver.example', 'https://receiver.example/path', 'https://receiver.example?x=1', 'https://user:secret@receiver.example']) {
    assert.throws(() => createApiProxy({ ...sharedSettings, FEEDBACK_API_URL: url }), (error) => (
      error.message.includes('FEEDBACK_API_URL') && !error.message.includes('secret')
    ));
  }
});
