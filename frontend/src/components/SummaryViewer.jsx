import { useRef, useCallback, useState } from 'react';

const PlayIcon = () => (
  <svg width="9" height="9" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>
);
const PauseIcon = () => (
  <svg width="9" height="9" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>
);

export default function SummaryViewer({ summary, audioFile }) {
  const audioCtxRef = useRef(null);
  const audioBufferRef = useRef(null);
  const sourceRef = useRef(null);
  const [playingChapter, setPlayingChapter] = useState(null);

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

  const stopPlay = useCallback(() => {
    if (sourceRef.current) { try { sourceRef.current.stop(); } catch {} sourceRef.current = null; }
    setPlayingChapter(null);
  }, []);

  const playChapter = useCallback(async (start, end, idx) => {
    // If this chapter is already playing, stop it
    if (playingChapter === idx) {
      stopPlay();
      return;
    }
    const ready = await ensureAudio();
    if (!ready) return;
    // Stop any currently playing chapter
    if (sourceRef.current) { try { sourceRef.current.stop(); } catch {} sourceRef.current = null; }
    const ctx = audioCtxRef.current;
    const buf = audioBufferRef.current;
    const from = Math.max(0, start - 1.5);
    const duration = Math.min(buf.duration - from, (end - start) + 3);
    const src = ctx.createBufferSource();
    src.buffer = buf;
    src.connect(ctx.destination);
    src.start(0, from, duration);
    src.onended = () => { sourceRef.current = null; setPlayingChapter(null); };
    sourceRef.current = src;
    setPlayingChapter(idx);
  }, [ensureAudio, stopPlay, playingChapter]);

  if (!summary) return null;

  // Parse sections from the summary text
  const sections = [];
  const sectionRegex = /===\s*(.+?)\s*===([\s\S]*?)(?====|$)/g;
  let match;
  while ((match = sectionRegex.exec(summary)) !== null) {
    sections.push({ title: match[1].trim(), body: match[2].trim() });
  }

  if (sections.length === 0) {
    return <div className="summary-raw">{summary}</div>;
  }

  // Convert [HH:MM:SS] timestamp string to seconds
  const tsToSecs = (ts) => {
    const parts = ts.split(':').map(Number);
    return parts[0] * 3600 + parts[1] * 60 + parts[2];
  };

  const renderChapters = (body) => {
    const lines = body.split('\n').filter(l => l.trim());
    return (
      <div className="chapters-list">
        {lines.map((line, i) => {
          const m = line.match(/^\[(\d{1,2}:\d{2}:\d{2})\s*[-–]\s*(\d{1,2}:\d{2}:\d{2})\]\s*(.+?):\s*(.+)$/);
          if (m) {
            const start = tsToSecs(m[1]);
            const end = tsToSecs(m[2]);
            const isPlaying = playingChapter === i;
            return (
              <div key={i} className="chapter-item">
                <div className="chapter-ts-row">
                  <span className="chapter-ts">{m[1]} – {m[2]}</span>
                  {audioFile && (
                    <button
                      className={`chapter-play-btn ${isPlaying ? 'playing' : ''}`}
                      onClick={() => playChapter(start, end, i)}
                      title={isPlaying ? 'Stop' : 'Play this section'}
                    >
                      {isPlaying ? <PauseIcon /> : <PlayIcon />}
                    </button>
                  )}
                </div>
                <div className="chapter-content">
                  <span className="chapter-title">{m[3]}</span>
                  <span className="chapter-desc">{m[4]}</span>
                </div>
              </div>
            );
          }
          return <div key={i} className="chapter-raw">{line}</div>;
        })}
      </div>
    );
  };

  const renderClinicalNote = (body) => {
    const lines = body.split('\n').filter(l => l.trim());
    const groups = [];
    let current = [];

    lines.forEach(line => {
      if (line.trim() === '') {
        if (current.length) { groups.push(current); current = []; }
      } else {
        current.push(line);
      }
    });
    if (current.length) groups.push(current);

    return (
      <div className="clinical-note">
        {groups.map((group, gi) => (
          <div key={gi} className="note-group">
            {group.map((line, li) => {
              const colonIdx = line.indexOf(':');
              if (colonIdx > 0) {
                const label = line.slice(0, colonIdx).trim();
                const value = line.slice(colonIdx + 1).trim();
                return (
                  <div key={li} className="note-field">
                    <span className="note-label">{label}</span>
                    <span className="note-value">{value}</span>
                  </div>
                );
              }
              return <div key={li} className="note-text">{line}</div>;
            })}
          </div>
        ))}
      </div>
    );
  };

  return (
    <div className="summary-viewer">
      {sections.map((sec, i) => (
        <div key={i} className={`summary-section section-${sec.title.toLowerCase().replace(/\s+/g, '-')}`}>
          <h3 className="section-heading">{sec.title}</h3>
          {sec.title === 'CHAPTERS'
            ? renderChapters(sec.body)
            : sec.title === 'CLINICAL NOTE'
            ? renderClinicalNote(sec.body)
            : <p className="section-body">{sec.body}</p>
          }
        </div>
      ))}
    </div>
  );
}
