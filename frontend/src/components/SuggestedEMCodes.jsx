export default function SuggestedEMCodes({ emData, loading }) {
  if (loading) {
    return <div className="em-loading">Assessing encounter complexity…</div>;
  }

  if (!emData) return null;

  const { duration_minutes, time_based, mdm_based } = emData;
  const hasDuration = duration_minutes > 0;
  const hasTimeSuggestions = hasDuration && (time_based?.new_patient || time_based?.established_patient);
  const hasMdm = mdm_based?.code_established_patient || mdm_based?.code_new_patient;

  if (!hasTimeSuggestions && !hasMdm) return null;

  return (
    <div className="em-panel">
      <div className="em-panel-header">
        <span className="em-panel-label">Suggested E/M Code</span>
        {hasDuration && (
          <span className="em-duration-badge">{duration_minutes} min recorded</span>
        )}
      </div>

      {/* Time-based section */}
      {hasTimeSuggestions && (
        <div className="em-section">
          <div className="em-section-title">Time-based billing</div>
          <div className="em-code-rows">
            {time_based.established_patient && (
              <div className="em-code-row">
                <span className="em-code">{time_based.established_patient.code}</span>
                <span className="em-code-meta">
                  Established patient · {time_based.established_patient.label}
                </span>
              </div>
            )}
            {time_based.new_patient && (
              <div className="em-code-row">
                <span className="em-code em-code-secondary">{time_based.new_patient.code}</span>
                <span className="em-code-meta">
                  New patient · {time_based.new_patient.label}
                </span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* MDM-based section */}
      {hasMdm && (
        <div className="em-section">
          <div className="em-section-title">
            Medical Decision Making
            {mdm_based.complexity && (
              <span className={`em-complexity-badge em-complexity-${mdm_based.complexity}`}>
                {mdm_based.complexity}
              </span>
            )}
          </div>
          <div className="em-code-rows">
            {mdm_based.code_established_patient && (
              <div className="em-code-row">
                <span className="em-code">{mdm_based.code_established_patient}</span>
                <span className="em-code-meta">Established patient</span>
              </div>
            )}
            {mdm_based.code_new_patient && (
              <div className="em-code-row">
                <span className="em-code em-code-secondary">{mdm_based.code_new_patient}</span>
                <span className="em-code-meta">New patient</span>
              </div>
            )}
          </div>
          {mdm_based.reasoning && (
            <div className="em-reasoning">{mdm_based.reasoning}</div>
          )}
        </div>
      )}

      <div className="em-disclaimer">
        Suggestions only — verify new vs. established patient status and confirm with your billing team.
      </div>
    </div>
  );
}