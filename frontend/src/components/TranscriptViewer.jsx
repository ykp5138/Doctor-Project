import { useState, useMemo } from 'react';

export default function TranscriptViewer({ words }) {
  const [showFlaggedOnly, setShowFlaggedOnly] = useState(false);

  const speakerBlocks = useMemo(() => {
    const blocks = [];
    let current = null;
    words.forEach(word => {
      const speaker = word.speaker || 'Unknown';
      if (!current || current.speaker !== speaker) {
        current = { speaker, words: [] };
        blocks.push(current);
      }
      current.words.push(word);
    });
    return blocks;
  }, [words]);

  const flaggedCount = useMemo(() => words.filter(w => w.flagged).length, [words]);

  const fmt = (s) => {
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return `${m}:${String(sec).padStart(2, '0')}`;
  };

  const displayBlocks = showFlaggedOnly
    ? speakerBlocks.map(b => ({ ...b, words: b.words.filter(w => w.flagged) })).filter(b => b.words.length > 0)
    : speakerBlocks;

  return (
    <div className="transcript-container">
      <div className="transcript-toolbar">
        <span className="word-count">{words.length} words · {flaggedCount} flagged</span>
        {flaggedCount > 0 && (
          <button
            className={`btn-flag-filter ${showFlaggedOnly ? 'active' : ''}`}
            onClick={() => setShowFlaggedOnly(v => !v)}
          >
            {showFlaggedOnly ? 'Show All' : 'Show Flagged Only'}
          </button>
        )}
      </div>

      <div className="transcript-body">
        {displayBlocks.map((block, bi) => (
          <div key={bi} className="speaker-block">
            <div className="speaker-label">{block.speaker}</div>
            <div className="speaker-text">
              {block.words.map((word, wi) => (
                <span
                  key={wi}
                  className={`word ${word.flagged ? 'word-flagged' : ''}`}
                  title={word.flagged ? `Low confidence · ${fmt(word.start || 0)}` : fmt(word.start || 0)}
                >
                  {word.text}{' '}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
