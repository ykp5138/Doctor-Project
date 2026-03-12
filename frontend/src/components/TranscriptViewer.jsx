import { useState, useMemo, useRef, useEffect, useCallback } from 'react';

export default function TranscriptViewer({ words: initialWords, audioFile }) {
  const [words, setWords] = useState(initialWords);
  const [popup, setPopup] = useState(null);
  const audioCtxRef = useRef(null);
  const audioBufferRef = useRef(null);
  const sourceRef = useRef(null);
  const popupRef = useRef(null);

  useEffect(() => { setWords(initialWords); }, [initialWords]);

  // Close popup on outside click
  useEffect(() => {
    if (!popup) return;
    const handler = (e) => {
      if (popupRef.current && !popupRef.current.contains(e.target)) {
        setPopup(null);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [popup]);

  // Lazy-load audio buffer
  const ensureAudio = useCallback(async () => {
    if (!audioFile) return false;
    if (audioBufferRef.current) return true;
    try {
      audioCtxRef.current = new AudioContext();
      const arrayBuffer = await audioFile.arrayBuffer();
      audioBufferRef.current = await audioCtxRef.current.decodeAudioData(arrayBuffer);
      return true;
    } catch { return false; }
  }, [audioFile]);

  const playSlice = useCallback(async (start, end, trackKey) => {
    const ready = await ensureAudio();
    if (!ready) return;
    if (sourceRef.current) { try { sourceRef.current.stop(); } catch {} sourceRef.current = null; }
    const ctx = audioCtxRef.current;
    const buf = audioBufferRef.current;
    const from = Math.max(0, start - 1.5);
    const duration = Math.min(buf.duration - from, (end - start) + 3);
    const src = ctx.createBufferSource();
    src.buffer = buf;
    src.connect(ctx.destination);
    src.start(0, from, duration);
    src.onended = () => { sourceRef.current = null; setPopup(p => p ? { ...p, playingTrack: null } : p); };
    sourceRef.current = src;
    setPopup(p => p ? { ...p, playingTrack: trackKey } : p);
  }, [ensureAudio]);

  const stopPlay = useCallback(() => {
    if (sourceRef.current) { try { sourceRef.current.stop(); } catch {} sourceRef.current = null; }
    setPopup(p => p ? { ...p, playingTrack: null } : p);
  }, []);

  const fetchSuggestions = useCallback(async (word, index) => {
    const ctx = words.slice(Math.max(0, index - 5), index + 6).map(w => w.text).join(' ');
    try {
      const res = await fetch('http://localhost:8000/suggest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ word: word.text, context: ctx }),
      });
      const data = await res.json();
      setPopup(p => p ? { ...p, suggestions: data.suggestions || [], loading: false } : p);
    } catch {
      setPopup(p => p ? { ...p, suggestions: [], loading: false } : p);
    }
  }, [words]);

  const handleWordClick = useCallback((word, index, e) => {
    if (!word.flagged) return;
    // Count other flagged instances of the same word text
    const sameWordIndices = words
      .map((w, i) => ({ w, i }))
      .filter(({ w, i }) => w.flagged && i !== index && w.text.toLowerCase() === word.text.toLowerCase())
      .map(({ i }) => i);

    // Use viewport-fixed position so scroll containers don't break it
    const rect = e.currentTarget.getBoundingClientRect();
    const left = Math.min(rect.left, window.innerWidth - 340);
    const top = rect.bottom + 6;

    if (sourceRef.current) { try { sourceRef.current.stop(); } catch {} sourceRef.current = null; }

    setPopup({
      wordIndex: index,
      wordText: word.text,          // original text for "fix all" matching
      start: word.start || 0,
      end: word.end || 0,
      a_start: word.a_start ?? null,
      a_end: word.a_end ?? null,
      position: { top, left },
      suggestions: [],
      loading: true,
      otherValue: '',
      playingTrack: null,
      sameWordIndices,              // other indices with the same flagged text
    });
    fetchSuggestions(word, index);
  }, [fetchSuggestions, words]);

  // applyAll=false → fix just this word; applyAll=true → fix this + all same-text instances
  const applyWord = useCallback((newText, applyAll = false) => {
    if (!newText.trim()) return;
    const { wordIndex, sameWordIndices } = popup;
    setWords(ws => ws.map((w, i) => {
      if (i === wordIndex) return { ...w, text: newText.trim(), flagged: false, fixed: true };
      if (applyAll && sameWordIndices.includes(i)) return { ...w, text: newText.trim(), flagged: false, fixed: true };
      return w;
    }));
    setPopup(null);
    if (sourceRef.current) { try { sourceRef.current.stop(); } catch {} sourceRef.current = null; }
  }, [popup]);

  const keepWord = useCallback((keepAll = false) => {
    const { wordIndex, sameWordIndices } = popup;
    setWords(ws => ws.map((w, i) => {
      if (i === wordIndex) return { ...w, flagged: false, fixed: true };
      if (keepAll && sameWordIndices.includes(i)) return { ...w, flagged: false, fixed: true };
      return w;
    }));
    setPopup(null);
    if (sourceRef.current) { try { sourceRef.current.stop(); } catch {} sourceRef.current = null; }
  }, [popup]);

  const speakerBlocks = useMemo(() => {
    const blocks = [];
    let current = null;
    words.forEach((word, i) => {
      const speaker = word.speaker || 'Unknown';
      if (!current || current.speaker !== speaker) {
        current = { speaker, words: [] };
        blocks.push(current);
      }
      current.words.push({ ...word, globalIndex: i });
    });
    return blocks;
  }, [words]);

  const flaggedCount = useMemo(() => words.filter(w => w.flagged).length, [words]);

  const fmt = (s) => {
    const m = Math.floor(s / 60);
    return `${m}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
  };

  const hasMany = popup && popup.sameWordIndices.length > 0;
  const totalCount = popup ? popup.sameWordIndices.length + 1 : 0;

  return (
    <div className="transcript-container">
      <div className="transcript-toolbar">
        <span className="word-count">{words.length} words · {flaggedCount} flagged</span>
        {flaggedCount > 0 && <span className="flagged-hint">Click highlighted words to review</span>}
      </div>

      <div className="transcript-body">
        {speakerBlocks.map((block, bi) => (
          <div key={bi} className="speaker-block">
            <div className="speaker-label">{block.speaker}</div>
            <div className="speaker-text">
              {block.words.map((word) => (
                <span
                  key={word.globalIndex}
                  className={`word ${word.flagged ? 'word-flagged' : word.fixed ? 'word-fixed' : ''}`}
                  title={word.flagged ? `Low confidence · ${fmt(word.start || 0)} — click to review` : fmt(word.start || 0)}
                  onClick={word.flagged ? (e) => handleWordClick(word, word.globalIndex, e) : undefined}
                >
                  {word.text}{' '}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* Word correction popup — position: fixed so scroll containers don't break it */}
      {popup && (
        <div
          ref={popupRef}
          className="word-popup"
          style={{ position: 'fixed', top: popup.position.top, left: popup.position.left }}
        >
          {/* Header: word + audio play */}
          <div className="popup-header">
            <span className="popup-flagged-word">"{popup.wordText}"</span>
            {audioFile && (
              <div className="popup-play-btns">
                <button
                  className={`popup-play-btn ${popup.playingTrack === 'whisper' ? 'playing' : ''}`}
                  onClick={() => popup.playingTrack === 'whisper' ? stopPlay() : playSlice(popup.start, popup.end, 'whisper')}
                >
                  {popup.playingTrack === 'whisper'
                    ? <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>
                    : <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                  }
                  W
                </button>
                {popup.a_start !== null && (
                  <button
                    className={`popup-play-btn ${popup.playingTrack === 'assembly' ? 'playing' : ''}`}
                    onClick={() => popup.playingTrack === 'assembly' ? stopPlay() : playSlice(popup.a_start, popup.a_end, 'assembly')}
                  >
                    {popup.playingTrack === 'assembly'
                      ? <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>
                      : <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                    }
                    A
                  </button>
                )}
              </div>
            )}
          </div>

          {/* Multiple instances notice */}
          {hasMany && (
            <div className="popup-multi-notice">
              {totalCount} instances of this word are flagged
            </div>
          )}

          {/* Suggestions */}
          <div className="popup-section-label">Suggestions</div>
          {popup.loading ? (
            <div className="popup-loading">Thinking…</div>
          ) : popup.suggestions.length === 0 ? (
            <div className="popup-no-suggestions">No alternatives found</div>
          ) : (
            <div className="popup-suggestions">
              {popup.suggestions.map((s, i) => (
                <div key={i} className="suggestion-row">
                  <button className="suggestion-chip" onClick={() => applyWord(s, false)}>
                    {s}
                  </button>
                  {hasMany && (
                    <button className="suggestion-chip suggestion-chip-all" onClick={() => applyWord(s, true)}>
                      Fix all {totalCount}
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Other / custom */}
          <div className="popup-section-label">Other</div>
          <div className="popup-other">
            <input
              className="popup-input"
              placeholder="Type your own…"
              value={popup.otherValue}
              onChange={e => setPopup(p => ({ ...p, otherValue: e.target.value }))}
              onKeyDown={e => e.key === 'Enter' && applyWord(popup.otherValue, false)}
            />
            <button
              className="popup-apply-btn"
              disabled={!popup.otherValue.trim()}
              onClick={() => applyWord(popup.otherValue, false)}
            >
              Fix
            </button>
            {hasMany && (
              <button
                className="popup-apply-btn"
                disabled={!popup.otherValue.trim()}
                onClick={() => applyWord(popup.otherValue, true)}
              >
                Fix all
              </button>
            )}
          </div>

          {/* Footer */}
          <div className="popup-footer">
            <button className="popup-keep-btn" onClick={() => keepWord(false)}>
              ✓ Keep
            </button>
            {hasMany && (
              <button className="popup-keep-btn" onClick={() => keepWord(true)}>
                Keep all {totalCount}
              </button>
            )}
            <button className="popup-cancel-btn" onClick={() => setPopup(null)}>
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
