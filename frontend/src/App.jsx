import { useState } from "react";
import { AudioUploader } from "./components/AudioUploader";
import { AudioRecorder } from "./components/AudioRecorder";
import { TranscriptViewer } from "./components/TranscriptViewer";
import "./App.css";

function App() {
  const [file, setFile] = useState(null);
  const [transcript, setTranscript] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState("upload");

  const handleFileSelect = (selectedFile) => {
    setFile(selectedFile);
    setTranscript(null);
    setError(null);
  };

  const handleRecordingComplete = (blob) => {
    const recordedFile = new File([blob], "recording.webm", {
      type: "audio/webm",
    });
    setFile(recordedFile);
    setTranscript(null);
    setError(null);
    setActiveTab("upload");
  };

  const handleClear = () => {
    setFile(null);
    setTranscript(null);
    setError(null);
  };

  const handleTranscribe = async () => {
    if (!file) return;

    setLoading(true);
    setError(null);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const response = await fetch("http://localhost:8000/transcribe", {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        throw new Error("Transcription failed");
      }

      const data = await response.json();
      setTranscript(data);
    } catch (err) {
      setError(err.message || "An error occurred during transcription");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="app">
      {/* Background decoration */}
      <div className="bg-decoration">
        <div className="bg-circle bg-circle-1"></div>
        <div className="bg-circle bg-circle-2"></div>
      </div>

      <div className="container">
        {/* Header */}
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
              <p>Your Medical Dictation</p>
            </div>
          </div>
        </header>

        {/* Main content */}
        <main className="main-content">
          <div className="card glass-card">
            {/* Tabs */}
            <div className="tabs">
              <button
                onClick={() => setActiveTab("upload")}
                className={`tab ${activeTab === "upload" ? "active" : ""}`}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                  <polyline points="17 8 12 3 7 8" />
                  <line x1="12" y1="3" x2="12" y2="15" />
                </svg>
                Upload File
              </button>
              <button
                onClick={() => setActiveTab("record")}
                className={`tab ${activeTab === "record" ? "active" : ""}`}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" />
                  <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
                  <line x1="12" x2="12" y1="19" y2="22" />
                </svg>
                Record Audio
              </button>
            </div>

            {/* Tab content */}
            <div className="tab-content">
              {activeTab === "upload" ? (
                <AudioUploader
                  onFileSelect={handleFileSelect}
                  selectedFile={file}
                  onClear={handleClear}
                />
              ) : (
                <AudioRecorder onRecordingComplete={handleRecordingComplete} />
              )}
            </div>

            {/* Transcribe button */}
            {file && (
              <div className="action-section">
                <button
                  onClick={handleTranscribe}
                  disabled={loading}
                  className="btn btn-primary btn-xl"
                >
                  {loading ? (
                    <>
                      <span className="spinner"></span>
                      Processing...
                    </>
                  ) : (
                    <>
                      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <polygon points="5 3 19 12 5 21 5 3" />
                      </svg>
                      Transcribe Audio
                    </>
                  )}
                </button>
              </div>
            )}

            {/* Error display */}
            {error && (
              <div className="error-message">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="10" />
                  <line x1="12" x2="12" y1="8" y2="12" />
                  <line x1="12" x2="12.01" y1="16" y2="16" />
                </svg>
                <span>{error}</span>
              </div>
            )}
          </div>

          {/* Transcript viewer */}
          {transcript && <TranscriptViewer transcript={transcript} />}
        </main>

        {/* Footer */}
        <footer className="footer">
          <p>Built For Healthcare • Hear Your Clients Out</p>
        </footer>
      </div>
    </div>
  );
}

export default App;
