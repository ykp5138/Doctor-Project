import { useState, useMemo, useRef, useEffect, useCallback } from 'react';

export default function TranscriptViewer({ words: initialWords, audioFile }) {
  const [words, setWords] = useState(initialWords);
  const [popup, setPopup] = useState(null); // { wordIndex, word, start, end, position, suggestions, loading, otherValue, playing }
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
    } catch {
      return false;
    }
  }, [audioFile]);

  const playSlice = useCallback(async (start, end) => {
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
    src.onended = () => { sourceRef.current = null; setPopup(p => p ? { ...p, playing: false } : p); };
    sourceRef.current = src;
    setPopup(p => p ? { ...p, playing: true } : p);
  }, [ensureAudio]);

  const stopPlay = useCallback(() => {
    if (sourceRef.current) { try { sourceRef.current.stop(); } catch {} sourceRef.current = null; }
    setPopup(p => p ? { ...p, playing: false } : p);
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
    const rect = e.currentTarget.getBoundingClientRect();
    const left = Math.min(rect.left, window.innerWidth - 330);
    setPopup({
      wordIndex: index,
      word: word.text,
      start: word.start || 0,
      end: word.end || 0,
      position: { top: rect.bottom + window.scrollY + 6, left: left + window.scrollX },
      suggestions: [],
      loading: true,
      otherValue: '',
      playing: false,
    });
    fetchSuggestions(word, index);
  }, [fetchSuggestions]);

  const applyWord = useCallback((index, newText) => {
    if (!newText.trim()) return;
    setWords(ws => ws.map((w, i) => i === index ? { ...w, text: newText.trim(), flagged: false } : w));
    setPopup(null);
    if (sourceRef.current) { try { sourceRef.current.stop(); } catch {} sourceRef.current = null; }
  }, []);

  const keepWord = useCallback((index) => {
    setWords(ws => ws.map((w, i) => i === index ? { ...w, flagged: false } : w));
    setPopup(null);
    if (sourceRef.current) { try { sourceRef.current.stop(); } catch {} sourceRef.current = null; }
  }, []);

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
                  className={`word ${word.flagged ? 'word-flagged' : ''}`}
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

      {/* Word correction popup */}
      {popup && (
        <div
          ref={popupRef}
          className="word-popup"
          style={{ top: popup.position.top, left: popup.position.left }}
        >
          <div className="popup-header">
            <span className="popup-flagged-word">"{popup.word}"</span>
            {audioFile && (
              <button
                className={`popup-play-btn ${popup.playing ? 'playing' : ''}`}
                onClick={() => popup.playing ? stopPlay() : playSlice(popup.start, popup.end)}
                title="Play surrounding audio"
              >
                {popup.playing
                  ? <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>
                  : <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                }
                {popup.playing ? 'Stop' : 'Play clip'}
              </button>
            )}
          </div>

          <div className="popup-section-label">Suggestions</div>
          {popup.loading
            ? <div className="popup-loading">Thinking…</div>
            : popup.suggestions.length === 0
            ? <div className="popup-no-suggestions">No alternatives found</div>
            : (
              <div className="popup-suggestions">
                {popup.suggestions.map((s, i) => (
                  <button key={i} className="suggestion-chip" onClick={() => applyWord(popup.wordIndex, s)}>
                    {s}
                  </button>
                ))}
              </div>
            )
          }

          <div className="popup-section-label">Other</div>
          <div className="popup-other">
            <input
              className="popup-input"
              placeholder="Type your own word…"
              value={popup.otherValue}
              onChange={e => setPopup(p => ({ ...p, otherValue: e.target.value }))}
              onKeyDown={e => e.key === 'Enter' && applyWord(popup.wordIndex, popup.otherValue)}
            />
            <button
              className="popup-apply-btn"
              disabled={!popup.otherValue.trim()}
              onClick={() => applyWord(popup.wordIndex, popup.otherValue)}
            >
              Apply
            </button>
          </div>

          <div className="popup-footer">
            <button className="popup-keep-btn" onClick={() => keepWord(popup.wordIndex)}>
              ✓ Keep "{popup.word}"
            </button>
            <button className="popup-cancel-btn" onClick={() => setPopup(null)}>
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
