import assert from 'node:assert/strict';
import { setImmediate as flush } from 'node:timers/promises';
import { test } from 'node:test';
import { createPipelineJobId, startPipelineProgress } from '../src/pipeline-progress.js';

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

function snapshot(jobId, status, whisperx, assemblyai, kevin) {
  return {
    job_id: jobId,
    status,
    stages: {
      whisperx: { status: whisperx, elapsed_seconds: 1.2 },
      assemblyai: { status: assemblyai, elapsed_seconds: 0.8 },
      kevin: { status: kevin, elapsed_seconds: kevin === 'pending' ? null : 0.4 },
    },
  };
}

function fixture(fetchProgress, jobId = 'job-a') {
  const updates = [];
  const unavailable = [];
  const calls = [];
  const timers = new Map();
  let sequence = 0;
  const stop = startPipelineProgress({
    jobId,
    fetchProgress: (...args) => { calls.push(args); return fetchProgress(...args); },
    onProgress: (progress) => updates.push(progress),
    onUnavailable: (value) => unavailable.push(value),
    schedule: (callback, delay) => {
      assert.equal(delay, 800);
      timers.set(++sequence, callback);
      return sequence;
    },
    cancel: (timer) => timers.delete(timer),
  });
  return {
    stop, updates, unavailable, calls, timers,
    async tick() {
      assert.equal(timers.size, 1);
      const [id, callback] = timers.entries().next().value;
      timers.delete(id);
      await callback();
    },
  };
}

test('each recording gets a fresh UUID hex ID accepted by the API', () => {
  const ids = Array.from({ length: 20 }, () => createPipelineJobId());
  assert.equal(new Set(ids).size, ids.length);
  assert.ok(ids.every((id) => /^[0-9a-f]{12}4[0-9a-f]{3}[89ab][0-9a-f]{15}$/.test(id)));
});

test('reflects overlapping transcribers and only backend-reported merge progress', async () => {
  const frames = [
    snapshot('job-a', 'running', 'running', 'running', 'pending'),
    snapshot('job-a', 'running', 'completed', 'running', 'pending'),
    snapshot('job-a', 'running', 'completed', 'completed', 'running'),
    snapshot('job-a', 'completed', 'completed', 'completed', 'completed'),
  ];
  let index = 0;
  const state = fixture(async () => frames[index++]);
  await flush();
  assert.equal(state.updates[0].stages.whisperx.status, 'running');
  assert.equal(state.updates[0].stages.assemblyai.status, 'running');
  assert.equal(state.updates[0].stages.kevin.status, 'pending');
  await state.tick();
  await state.tick();
  await state.tick();
  assert.deepEqual(state.updates, frames, 'statuses and elapsed times must come from the server');
  assert.equal(state.timers.size, 0, 'terminal progress must stop polling');
});

test('retries an initial 404 without showing a failed transcription', async () => {
  let attempt = 0;
  const progress = snapshot('job-a', 'running', 'running', 'running', 'pending');
  const state = fixture(async () => {
    if (++attempt === 1) throw Object.assign(new Error('Not registered yet'), { status: 404 });
    return progress;
  });
  await flush();
  assert.deepEqual(state.unavailable, []);
  assert.deepEqual(state.updates, []);
  await state.tick();
  assert.deepEqual(state.updates, [progress]);
  assert.deepEqual(state.unavailable, [false]);
  state.stop();
});

test('polling failures stay isolated and recover without overwriting stage states', async () => {
  const initial = snapshot('job-a', 'running', 'running', 'running', 'pending');
  const recovered = snapshot('job-a', 'running', 'completed', 'completed', 'running');
  let attempt = 0;
  const state = fixture(async () => {
    if (++attempt === 1) return initial;
    if (attempt === 2) throw new TypeError('Network unavailable');
    return recovered;
  });
  await flush();
  await state.tick();
  assert.deepEqual(state.updates, [initial]);
  assert.deepEqual(state.unavailable, [false, true]);
  await state.tick();
  assert.deepEqual(state.updates, [initial, recovered]);
  assert.deepEqual(state.unavailable, [false, true, false]);
  state.stop();
});

test('slow GET requests never overlap and stopping aborts pending work', async () => {
  const waiting = deferred();
  const state = fixture(() => waiting.promise);
  assert.equal(state.calls.length, 1);
  assert.equal(state.timers.size, 0, 'no next request is scheduled while a GET is pending');
  const signal = state.calls[0][1].signal;
  assert.equal(signal.aborted, false);
  state.stop();
  state.stop();
  assert.equal(signal.aborted, true);
  waiting.resolve(snapshot('job-a', 'completed', 'completed', 'completed', 'completed'));
  await flush();
  assert.deepEqual(state.updates, [], 'a late response after cleanup must be ignored');
  assert.equal(state.timers.size, 0);
});

test('stopping clears a scheduled GET and prevents further updates', async () => {
  const state = fixture(async () => snapshot('job-a', 'running', 'running', 'running', 'pending'));
  await flush();
  assert.equal(state.timers.size, 1);
  state.stop();
  assert.equal(state.timers.size, 0);
  assert.equal(state.calls.length, 1);
});

test('a stale job response or cleanup cannot affect a newer recording', async () => {
  const previous = deferred();
  const oldState = fixture(() => previous.promise);
  oldState.stop();
  const current = deferred();
  const newState = fixture(() => current.promise, 'job-b');
  previous.resolve(snapshot('job-a', 'completed', 'completed', 'completed', 'completed'));
  await flush();
  oldState.stop();
  assert.deepEqual(oldState.updates, []);
  assert.equal(newState.calls[0][1].signal.aborted, false);
  const progress = snapshot('job-b', 'running', 'running', 'running', 'pending');
  current.resolve(progress);
  await flush();
  assert.deepEqual(newState.updates, [progress]);
  newState.stop();
});

test('a mismatched job snapshot is ignored rather than displayed', async () => {
  const state = fixture(async () => snapshot('other-job', 'completed', 'completed', 'completed', 'completed'));
  await flush();
  assert.deepEqual(state.updates, []);
  assert.deepEqual(state.unavailable, [true]);
  state.stop();
});

test('failed and skipped stages remain distinct and stop further polling', async () => {
  const progress = snapshot('job-a', 'failed', 'failed', 'completed', 'skipped');
  const state = fixture(async () => progress);
  await flush();
  assert.deepEqual(state.updates, [progress]);
  assert.equal(state.timers.size, 0);
});
