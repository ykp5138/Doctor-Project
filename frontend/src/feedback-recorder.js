// A feedback click sets a value; it never toggles a previous value off.
const clientNoteIds = new WeakMap();

export function feedbackRecordingId(result, makeId = () => crypto.randomUUID()) {
  const base = result?.meta?.base;
  if (typeof base === 'string' && base.trim()) return base;
  if (!result || typeof result !== 'object') return null;
  if (!clientNoteIds.has(result)) clientNoteIds.set(result, `note-${makeId()}`);
  return clientNoteIds.get(result);
}

export function feedbackKey(recordingId, code) {
  return JSON.stringify([recordingId, code.trim().toUpperCase()]);
}

export function createFeedbackRecorder({ save, onChoice, onNotice }) {
  const queues = new Map();
  const latestByCode = new Map();
  const confirmed = new Map();
  let sequence = 0;
  let latestNotice = 0;
  let active = true;

  return {
    setActive(value) { active = value; },

    submit(payload) {
      if (!payload.transcript_base || typeof payload.is_correct !== 'boolean') {
        throw new TypeError('Feedback needs a recording and a true/false choice.');
      }
      const key = feedbackKey(payload.transcript_base, payload.code);
      const action = ++sequence;
      const choice = payload.is_correct;
      latestByCode.set(key, action);
      latestNotice = action;
      if (active) {
        onChoice({ key, value: choice, pending: true });
        onNotice({ recordingId: payload.transcript_base, message: 'Saving...', pending: true });
      }

      // Finish earlier saves for this code before submitting the next click.
      // A failed save must not block a later choice, and different codes may save together.
      const request = (queues.get(key) ?? Promise.resolve())
        .catch(() => undefined)
        .then(async () => {
          const response = await save(payload);
          if (response?.ok !== true) throw new Error('Feedback was not acknowledged');
          return response;
        });
      queues.set(key, request);

      const completion = request.then(() => {
        confirmed.set(key, choice);
        if (active && latestByCode.get(key) === action) {
          onChoice({ key, value: choice, pending: false });
        }
        if (active && latestNotice === action) {
          onNotice({
            recordingId: payload.transcript_base,
            message: choice ? '✓ recorded' : 'X recorded',
            pending: false,
          });
        }
        return { saved: true, choice };
      }, () => {
        if (active && latestByCode.get(key) === action) {
          onChoice({ key, value: confirmed.get(key), pending: false });
        }
        if (active && latestNotice === action) {
          onNotice({ recordingId: payload.transcript_base, message: 'Feedback not saved', pending: false });
        }
        return { saved: false, choice };
      });
      completion.then(() => {
        if (queues.get(key) === request) queues.delete(key);
      });
      return completion;
    },
  };
}
