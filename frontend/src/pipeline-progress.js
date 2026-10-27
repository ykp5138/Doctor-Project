export function createPipelineJobId() {
  // getRandomValues also works on local-network origins without randomUUID support.
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('');
}

// A fresh poller belongs to one transcription; stopping it never affects another job.
export function startPipelineProgress({
  jobId,
  fetchProgress,
  onProgress,
  onUnavailable = () => {},
  intervalMs = 800,
  schedule = setTimeout,
  cancel = clearTimeout,
}) {
  let stopped = false;
  let timer = null;
  let controller = null;
  let receivedProgress = false;

  const stop = () => {
    stopped = true;
    if (timer !== null) cancel(timer);
    timer = null;
    controller?.abort();
  };

  const poll = async () => {
    if (stopped) return;
    const requestController = new AbortController();
    controller = requestController;
    try {
      const progress = await fetchProgress(jobId, { signal: requestController.signal });
      if (stopped) return;
      if (progress?.job_id !== jobId || !progress.stages) {
        throw new Error('Progress did not match this recording.');
      }
      receivedProgress = true;
      onUnavailable(false);
      onProgress(progress);
      if (progress.status === 'completed' || progress.status === 'failed') stop();
    } catch (error) {
      if (stopped || error.name === 'AbortError') return;
      // The first GET may arrive before the upload has registered its job ID.
      if (error.status !== 404 || receivedProgress) onUnavailable(true);
    } finally {
      if (controller === requestController) controller = null;
      // Schedule after settlement, so even slow requests never overlap.
      if (!stopped) timer = schedule(poll, intervalMs);
    }
  };

  void poll();
  return stop;
}
