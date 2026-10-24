import assert from 'node:assert/strict';
import { afterEach, mock, test } from 'node:test';
import { apiFetch } from '../src/api.js';

afterEach(() => mock.restoreAll());

test('uploads through the current origin without overriding multipart boundaries', async () => {
  const body = new FormData();
  body.append('file', new Blob(['audio']), 'sample.wav');
  const response = Response.json({ words: [] });
  const fetchMock = mock.method(globalThis, 'fetch', async () => response);

  assert.equal(await apiFetch('/transcribe', { method: 'POST', body }), response);
  const [url, options] = fetchMock.mock.calls[0].arguments;
  assert.equal(url, '/api/transcribe');
  assert.equal(options.method, 'POST');
  assert.equal(options.body, body);
  assert.equal(options.headers, undefined);
});

test('replaces a rejected fetch with actionable connection guidance', async () => {
  mock.method(globalThis, 'fetch', async () => { throw new TypeError('Failed to fetch'); });

  await assert.rejects(apiFetch('/transcribe'), /Could not reach the API.*127\.0\.0\.1:8000/);
});

test('preserves transcription failure details returned by the backend', async () => {
  mock.method(globalThis, 'fetch', async () => Response.json(
    { detail: 'Pipeline step failed: WhisperX could not load the audio.' }, { status: 500 },
  ));

  await assert.rejects(apiFetch('/transcribe'), {
    message: 'Pipeline step failed: WhisperX could not load the audio.',
  });
});

test('handles an empty proxy error when the backend is unavailable', async () => {
  mock.method(globalThis, 'fetch', async () => new Response('', { status: 500 }));

  await assert.rejects(apiFetch('/transcribe'), /HTTP 500.*backend is running/);
});

test('rejects a failed feedback write rather than treating it as saved', async () => {
  mock.method(globalThis, 'fetch', async () => Response.json(
    { detail: 'Could not append feedback.' }, { status: 500 },
  ));

  await assert.rejects(apiFetch('/feedback', { method: 'POST' }), {
    message: 'Could not append feedback.',
  });
});
