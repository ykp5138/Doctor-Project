export default function SuggestedCodes({
  suggestions,
  loading,
  activeCodeIdx,
  activeEvidenceIdx,
  onSelectEvidence,
  onFeedback,
  feedbackStates = {},
}) {
  if (loading) {
    return (
      <div className="icd-loading">
        Analyzing transcript for ICD-10 codes…
      </div>
    );
  }

  if (!suggestions?.length) return null;

  return (
    <div className="icd-panel">
      <div className="icd-panel-header">
        <span className="icd-panel-label">Suggested ICD-10 Codes</span>
        {activeCodeIdx !== null && suggestions[activeCodeIdx]?.evidence.length > 1 && (
          <span className="icd-nav-hint">← → to navigate evidence</span>
        )}
      </div>

      <div className="icd-codes-list">
        {suggestions.map((sug, ci) => {
          const isOpen = activeCodeIdx === ci;
          return (
            <div key={ci} className={`icd-code-item${isOpen ? ' open' : ''}`}>
              <button
                className="icd-code-btn"
                onClick={() => onSelectEvidence(isOpen ? null : ci, 0)}
              >
                <span className="icd-code">{sug.code}</span>
                <span className="icd-code-desc">{sug.description}</span>
                <span className="icd-chevron">{isOpen ? '▲' : '▼'}</span>
              </button>

              {isOpen && (
                <div className="icd-evidence-list">
                  {sug.evidence.map((ev, ei) => {
                    const isActive = activeEvidenceIdx === ei;
                    const hasMatch = ev.word_indices?.length > 0;
                    return (
                      <div
                        key={ei}
                        className={`icd-evidence-item${isActive ? ' active' : ''}`}
                      >
                        <button
                          className="icd-evidence-btn"
                          onClick={() => onSelectEvidence(ci, ei)}
                        >
                          <span className="icd-evidence-dot">●</span>
                          <span className="icd-evidence-phrase">"{ev.phrase}"</span>
                          {!hasMatch && (
                            <span className="icd-no-match">(not found in transcript)</span>
                          )}
                        </button>
                        <div
                          className="icd-feedback-btns"
                          role="group"
                          aria-label={`Feedback for ${sug.code}`}
                          aria-busy={feedbackStates[sug.code]?.pending || undefined}
                        >
                          <button
                            type="button"
                            className="icd-feedback-correct"
                            title="Correct — this code applies"
                            aria-pressed={feedbackStates[sug.code]?.value === true}
                            onClick={() => onFeedback(sug.code, ev.phrase, ev.word_indices ?? [], true)}
                          >
                            ✓
                          </button>
                          <button
                            type="button"
                            className="icd-feedback-incorrect"
                            title="Incorrect — this code does not apply"
                            aria-pressed={feedbackStates[sug.code]?.value === false}
                            onClick={() => onFeedback(sug.code, ev.phrase, ev.word_indices ?? [], false)}
                          >
                            ✗
                          </button>
                        </div>
                      </div>
                    );
                  })}

                  {sug.evidence.length > 1 && (
                    <div className="icd-nav-counter">
                      {activeEvidenceIdx + 1} of {sug.evidence.length} — use ← → to navigate
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
