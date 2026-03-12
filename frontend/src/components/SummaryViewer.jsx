export default function SummaryViewer({ summary }) {
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

  const renderChapters = (body) => {
    const lines = body.split('\n').filter(l => l.trim());
    return (
      <div className="chapters-list">
        {lines.map((line, i) => {
          const m = line.match(/^\[(\d{2}:\d{2}:\d{2})\s*-\s*(\d{2}:\d{2}:\d{2})\]\s*(.+?):\s*(.+)$/);
          if (m) {
            return (
              <div key={i} className="chapter-item">
                <span className="chapter-ts">{m[1]} – {m[2]}</span>
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
