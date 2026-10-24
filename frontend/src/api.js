const CONNECTION_HELP = 'Check that the backend is running on 127.0.0.1:8000, then try again.';

// Vite forwards /api to FastAPI, so requests work on whichever port serves the UI.
export async function apiFetch(path, options) {
  let response;
  try {
    response = await fetch(`/api${path}`, options);
  } catch (error) {
    if (error.name === 'AbortError') throw error;
    throw new Error(`Could not reach the API. ${CONNECTION_HELP}`, { cause: error });
  }

  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const detail = payload?.detail;
    // Keep pipeline errors from FastAPI visible instead of hiding their cause.
    if (detail) {
      throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
    }
    throw new Error(`API request failed (HTTP ${response.status}). ${CONNECTION_HELP}`);
  }

  return response;
}
