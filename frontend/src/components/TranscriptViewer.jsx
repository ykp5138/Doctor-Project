import { useState } from "react";

export function TranscriptViewer({ transcript }) {
    const [showFlaggedOnly, setShowFlaggedOnly] = useState(false);

    if (!transcript || !transcript.words) {
        return null;
    }

    const flaggedWords = transcript.words.filter((w) => w.confidence < 0.8);
    const wordsToShow = showFlaggedOnly
        ? transcript.words.filter((w) => w.confidence < 0.8)
        : transcript.words;

    const formatTime = (seconds) => {
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${mins}:${secs.toString().padStart(2, "0")}`;
    };

    return (
        <div className="transcript-container">
            {/* Header */}
            <div className="transcript-header">
                <div className="transcript-title-section">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="transcript-icon">
                        <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z" />
                        <polyline points="14 2 14 8 20 8" />
                        <line x1="16" x2="8" y1="13" y2="13" />
                        <line x1="16" x2="8" y1="17" y2="17" />
                        <line x1="10" x2="8" y1="9" y2="9" />
                    </svg>
                    <h3>Transcription Result</h3>
                </div>
                {flaggedWords.length > 0 && (
                    <button
                        onClick={() => setShowFlaggedOnly(!showFlaggedOnly)}
                        className={`filter-button ${showFlaggedOnly ? 'active' : ''}`}
                    >
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z" />
                            <line x1="4" x2="4" y1="22" y2="15" />
                        </svg>
                        {showFlaggedOnly
                            ? "Show All"
                            : `${flaggedWords.length} Flagged`}
                    </button>
                )}
            </div>

            {/* Main content area */}
            <div className="transcript-body">
                {/* Transcript text */}
                <div className="transcript-text-area">
                    <div className="transcript-text">
                        {wordsToShow.map((word, index) => (
                            <span
                                key={index}
                                className={`transcript-word ${word.confidence < 0.8 ? 'flagged' : ''}`}
                                title={`Confidence: ${Math.round(word.confidence * 100)}%`}
                            >
                                {word.word}{" "}
                            </span>
                        ))}
                    </div>
                </div>

                {/* Flagged words sidebar */}
                {flaggedWords.length > 0 && (
                    <div className="flagged-sidebar">
                        <h4 className="flagged-title">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                <circle cx="12" cy="12" r="10" />
                                <line x1="12" x2="12" y1="8" y2="12" />
                                <line x1="12" x2="12.01" y1="16" y2="16" />
                            </svg>
                            Low Confidence
                        </h4>
                        <div className="flagged-list">
                            {flaggedWords.slice(0, 10).map((word, index) => (
                                <div key={index} className="flagged-item">
                                    <span className="flagged-word">"{word.word}"</span>
                                    <div className="flagged-meta">
                                        <span className="flagged-time">{formatTime(word.start)}</span>
                                        <span className="flagged-confidence">
                                            {Math.round(word.confidence * 100)}%
                                        </span>
                                    </div>
                                </div>
                            ))}
                            {flaggedWords.length > 10 && (
                                <p className="flagged-more">
                                    +{flaggedWords.length - 10} more
                                </p>
                            )}
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
