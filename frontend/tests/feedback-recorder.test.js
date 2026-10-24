import assert from 'node:assert/strict';
import { setImmediate as flush } from 'node:timers/promises';
import { test } from 'node:test';
import { createFeedbackRecorder, feedbackKey, feedbackRecordingId } from '../src/feedback-recorder.js';

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

function payload(choice, code = 'L70.0', recording = 'recording-a') {
  return {
    code,
    description: 'Synthetic fixture',
    evidence_phrase: 'example',
    word_indices: [0],
    is_correct: choice,
    transcript_base: recording,
    concepts: { symptoms: ['example'] },
  };
}

function fixture(save) {
  const changes = [];
  const notices = [];
  const states = new Map();
  const recorder = createFeedbackRecorder({
    save,
    onChoice: (state) => { changes.push(state); states.set(state.key, state); },
    onNotice: (notice) => notices.push(notice),
  });
  return { recorder, changes, notices, states };
}

test('rapid check, X, X saves in click order and never cancels the selected value', async () => {
  const pending = [deferred(), deferred(), deferred()];
  const submitted = [];
  const { recorder, changes, notices, states } = fixture((record) => {
    submitted.push(record);
    return pending[submitted.length - 1].promise;
  });
  const clicks = [recorder.submit(payload(true)), recorder.submit(payload(false)), recorder.submit(payload(false))];
  await flush();
  assert.equal(submitted.length, 1, 'later clicks must wait for the earlier request');
  assert.equal(states.get(feedbackKey('recording-a', 'L70.0')).value, false);

  pending[0].resolve({ ok: true });
  await flush();
  assert.equal(submitted.length, 2);
  assert.equal(notices.filter((notice) => notice.message.endsWith('recorded')).length, 0);
  pending[1].resolve({ ok: true });
  await flush();
  assert.equal(submitted.length, 3);
  assert.equal(notices.filter((notice) => notice.message.endsWith('recorded')).length, 0);
  pending[2].resolve({ ok: true });
  await Promise.all(clicks);

  assert.deepEqual(submitted.map((record) => record.is_correct), [true, false, false]);
  assert.ok(changes.every((state) => typeof state.value === 'boolean'), 'a repeated choice must never clear feedback');
  assert.deepEqual(states.get(feedbackKey('recording-a', 'L70.0')), {
    key: feedbackKey('recording-a', 'L70.0'), value: false, pending: false,
  });
  assert.equal(notices.at(-1).message, 'X recorded');
  assert.equal(notices.filter((notice) => notice.message.endsWith('recorded')).length, 1);
  assert.deepEqual(submitted[0], payload(true), 'the evidence and transcript payload must be preserved');
});

test('different codes can save together and an older success cannot replace the latest popup', async () => {
  const first = deferred();
  const second = deferred();
  const started = [];
  const { recorder, notices } = fixture((record) => {
    started.push(record.code);
    return record.code === 'A' ? first.promise : second.promise;
  });
  const a = recorder.submit(payload(true, 'A'));
  const b = recorder.submit(payload(false, 'B'));
  await flush();
  assert.deepEqual(started, ['A', 'B']);
  second.resolve({ ok: true });
  await b;
  assert.equal(notices.at(-1).message, 'X recorded');
  const afterLatest = notices.length;
  first.resolve({ ok: true });
  await a;
  assert.equal(notices.length, afterLatest);
});

test('an older failure cannot replace a newer confirmation', async () => {
  const first = deferred();
  const { recorder, notices } = fixture((record) => record.code === 'A' ? first.promise : Promise.resolve({ ok: true }));
  const a = recorder.submit(payload(true, 'A'));
  await recorder.submit(payload(false, 'B'));
  first.reject(new Error('synthetic failure'));
  assert.equal((await a).saved, false);
  assert.equal(notices.at(-1).message, 'X recorded');
});

test('a failed latest save restores the confirmed choice and shows failure', async () => {
  let attempts = 0;
  const { recorder, notices, states } = fixture(async () => {
    if (++attempts === 2) throw new Error('synthetic failure');
    return { ok: true };
  });
  await recorder.submit(payload(true));
  assert.equal(notices.at(-1).message, '✓ recorded');
  assert.equal((await recorder.submit(payload(false))).saved, false);
  assert.equal(states.get(feedbackKey('recording-a', 'L70.0')).value, true);
  assert.equal(notices.at(-1).message, 'Feedback not saved');
});

test('an unsuccessful earlier request does not block a later choice for the same code', async () => {
  let attempts = 0;
  const { recorder, notices, states } = fixture(async () => {
    if (++attempts === 1) throw new Error('synthetic failure');
    return { ok: true };
  });
  const first = recorder.submit(payload(true));
  const last = recorder.submit(payload(false));
  assert.deepEqual(await Promise.all([first, last]), [
    { saved: false, choice: true }, { saved: true, choice: false },
  ]);
  assert.equal(states.get(feedbackKey('recording-a', 'L70.0')).value, false);
  assert.equal(notices.at(-1).message, 'X recorded');
  assert.ok(notices.every((notice) => notice.message !== 'Feedback not saved'));
});

test('the same code in separate recordings has independent requests and choices', async () => {
  const first = deferred();
  const { recorder, states } = fixture((record) => record.transcript_base === 'one' ? first.promise : Promise.resolve({ ok: true }));
  const a = recorder.submit(payload(true, 'L70.0', 'one'));
  await recorder.submit(payload(false, 'L70.0', 'two'));
  assert.equal(states.get(feedbackKey('two', 'L70.0')).value, false);
  first.resolve({ ok: true });
  await a;
  assert.equal(states.get(feedbackKey('one', 'L70.0')).value, true);
});

test('a 2xx response without a positive save acknowledgment is treated as failure', async () => {
  const { recorder, states, notices } = fixture(async () => ({ ok: false }));
  assert.equal((await recorder.submit(payload(true))).saved, false);
  assert.equal(states.get(feedbackKey('recording-a', 'L70.0')).value, undefined);
  assert.equal(notices.at(-1).message, 'Feedback not saved');
});

test('inactive UI receives no late updates while its queued saves still finish', async () => {
  const waiting = deferred();
  const { recorder, changes, notices } = fixture(() => waiting.promise);
  const click = recorder.submit(payload(true));
  recorder.setActive(false);
  waiting.resolve({ ok: true });
  await click;
  assert.equal(changes.length, 1);
  assert.equal(notices.length, 1);
});

test('real recording bases are preserved and missing bases get stable distinct note IDs', () => {
  let counter = 0;
  const makeId = () => String(++counter);
  const real = { meta: { base: 'real-upload-base' } };
  const first = {};
  const second = {};
  assert.equal(feedbackRecordingId(real, makeId), 'real-upload-base');
  assert.equal(feedbackRecordingId(first, makeId), 'note-1');
  assert.equal(feedbackRecordingId(first, makeId), 'note-1');
  assert.equal(feedbackRecordingId(second, makeId), 'note-2');
  assert.equal(feedbackRecordingId(null, makeId), null);
});
