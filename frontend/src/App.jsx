import { useState, useRef } from 'react';
import { AudioUploader } from './components/AudioUploader';
import { AudioRecorder } from './components/AudioRecorder';
import TranscriptViewer from './components/TranscriptViewer';
import SummaryViewer from './components/SummaryViewer';
import './App.css';

const STEPS = [
  { id: 1, label: 'WhisperX', desc: 'Transcribing + diarizing audio' },
  { id: 2, label: 'AssemblyAI', desc: 'Cloud transcription' },
  { id: 3, label: 'Kevin', desc: 'Merging + generating summary' },
];

function App() {
  const [file, setFile] = useState(null);
  const [inputTab, setInputTab] = useState('upload');
  const [resultTab, setResultTab] = useState('transcript');
  const [loading, setLoading] = useState(false);
  const [step, setStep] = useState(0);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const stepTimer = useRef(null);

  const handleFileSelect = (f) => { setFile(f); setResult(null); setError(null); };
  const handleRecordingComplete = (blob) => {
    setFile(new File([blob], 'recording.webm', { type: 'audio/webm' }));
    setResult(null); setError(null); setInputTab('upload');
  };
  const handleClear = () => { setFile(null); setResult(null); setError(null); };

  const handleTranscribe = async () => {
    if (!file) return;
    setLoading(true);
    setStep(1);
    setError(null);
    setResult(null);

    // Simulate step progression (rough timing)
    stepTimer.current = setTimeout(() => setStep(2), 25000);
    const t2 = setTimeout(() => setStep(3), 55000);

    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await fetch('http://localhost:8000/transcribe', {
        method: 'POST',
        body: formData,
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        throw new Error(detail.detail || 'Transcription failed');
      }
      const data = await res.json();
      setResult(data);
      setResultTab('transcript');
    } catch (err) {
      setError(err.message || 'An error occurred');
    } finally {
      clearTimeout(stepTimer.current);
      clearTimeout(t2);
      setLoading(false);
      setStep(0);
    }
  };

  return (
    <div className="app">
      <div className="bg-decoration">
        <div className="bg-circle bg-circle-1" />
        <div className="bg-circle bg-circle-2" />
      </div>

      <div className="container">
        <header className="header">
          <div className="logo">
            <div className="logo-icon">
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" />
                <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
                <line x1="12" x2="12" y1="19" y2="22" />
              </svg>
            </div>
            <div className="logo-text">
              <h1>Clinic Transcriber</h1>
              <p>Medical Dictation & Documentation</p>
            </div>
          </div>
        </header>

        <main className="main-content">
          {/* Upload card */}
          <div className="card glass-card">
            <div className="tabs">
              <button onClick={() => setInputTab('upload')} className={`tab ${inputTab === 'upload' ? 'active' : ''}`}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                  <polyline points="17 8 12 3 7 8" />
                  <line x1="12" y1="3" x2="12" y2="15" />
                </svg>
                Upload File
              </button>
              <button onClick={() => setInputTab('record')} className={`tab ${inputTab === 'record' ? 'active' : ''}`}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" />
                  <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
                  <line x1="12" x2="12" y1="19" y2="22" />
                </svg>
                Record Audio
              </button>
            </div>

            <div className="tab-content">
              {inputTab === 'upload'
                ? <AudioUploader onFileSelect={handleFileSelect} selectedFile={file} onClear={handleClear} />
                : <AudioRecorder onRecordingComplete={handleRecordingComplete} />
              }
            </div>

            {file && !loading && (
              <div className="action-section">
                <button onClick={handleTranscribe} className="btn btn-primary btn-xl">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <polygon points="5 3 19 12 5 21 5 3" />
                  </svg>
                  Transcribe Audio
                </button>
              </div>
            )}

            {loading && (
              <div className="pipeline-progress">
                <p className="pipeline-note">This may take several minutes on CPU.</p>
                <div className="steps">
                  {STEPS.map(s => (
                    <div key={s.id} className={`step ${step === s.id ? 'step-active' : step > s.id ? 'step-done' : 'step-pending'}`}>
                      <div className="step-icon">
                        {step > s.id
                          ? <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><polyline points="20 6 9 17 4 12" /></svg>
                          : step === s.id
                          ? <span className="spinner-sm" />
                          : <span>{s.id}</span>
                        }
                      </div>
                      <div className="step-text">
                        <span className="step-label">{s.label}</span>
                        <span className="step-desc">{s.desc}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {error && (
              <div className="error-message">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="10" /><line x1="12" x2="12" y1="8" y2="12" /><line x1="12" x2="12.01" y1="16" y2="16" />
                </svg>
                {error}
              </div>
            )}
          </div>

          {/* Results */}
          {result && (
            <div className="card glass-card result-card">
              <div className="tabs">
                <button onClick={() => setResultTab('transcript')} className={`tab ${resultTab === 'transcript' ? 'active' : ''}`}>
                  Transcript
                </button>
                <button onClick={() => setResultTab('summary')} className={`tab ${resultTab === 'summary' ? 'active' : ''}`}>
                  Clinical Note
                </button>
              </div>
              <div className="tab-content result-content">
                {resultTab === 'transcript'
                  ? <TranscriptViewer words={result.words} />
                  : <SummaryViewer summary={result.summary} />
                }
              </div>
            </div>
          )}
        </main>

        <footer className="footer">
          <p>Built For Healthcare • Hear Your Clients Out</p>
        </footer>
      </div>
    </div>
  );
}

export default App;
