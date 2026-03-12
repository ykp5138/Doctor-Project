import { useState, useRef } from 'react';
import { motion } from 'framer-motion';
import { Upload, Mic, Play, FileAudio, CheckCircle, Loader2, AlertCircle, FileText, ClipboardList } from 'lucide-react';
import { AudioUploader } from './AudioUploader';
import { AudioRecorder } from './AudioRecorder';
import TranscriptViewer from './TranscriptViewer';
import SummaryViewer from './SummaryViewer';

const STEPS = [
  { id: 1, label: 'WhisperX', desc: 'Transcribing + diarizing audio' },
  { id: 2, label: 'AssemblyAI', desc: 'Cloud transcription' },
  { id: 3, label: 'Kevin', desc: 'Merging + generating summary' },
];

const NOTE_TYPES = ['SOAP Note', 'Progress Note', 'Consultation', 'Procedure'];

export default function NewNote() {
  const [file, setFile] = useState(null);
  const [inputTab, setInputTab] = useState('upload');
  const [resultTab, setResultTab] = useState('transcript');
  const [noteType, setNoteType] = useState('SOAP Note');
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
    <motion.div
      className="max-w-6xl mx-auto px-6 py-10"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
    >
      {/* Page header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">New Note</h1>
        <p className="text-sm text-gray-500 mt-1">Upload or record a patient visit to generate a structured clinical note.</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* ── Left panel: Input ── */}
        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-6 flex flex-col gap-5">
          {/* Note type selector */}
          <div>
            <label className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2 block">Note Type</label>
            <div className="flex flex-wrap gap-2">
              {NOTE_TYPES.map(t => (
                <button
                  key={t}
                  onClick={() => setNoteType(t)}
                  className="px-3 py-1.5 rounded-lg text-sm font-medium border transition-all"
                  style={noteType === t
                    ? { background: '#1a5d3a', color: 'white', borderColor: '#1a5d3a' }
                    : { background: 'transparent', color: '#6b7280', borderColor: '#e5e7eb' }
                  }
                >
                  {t}
                </button>
              ))}
            </div>
          </div>

          {/* Input mode tabs */}
          <div>
            <label className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2 block">Audio Source</label>
            <div className="flex gap-2 p-1 bg-gray-100 rounded-xl">
              <button
                onClick={() => setInputTab('upload')}
                className="flex-1 flex items-center justify-center gap-2 py-2 px-3 rounded-lg text-sm font-medium transition-all"
                style={inputTab === 'upload'
                  ? { background: 'white', color: '#1a5d3a', boxShadow: '0 1px 4px rgba(0,0,0,0.08)' }
                  : { color: '#6b7280' }
                }
              >
                <Upload size={15} />
                Upload File
              </button>
              <button
                onClick={() => setInputTab('record')}
                className="flex-1 flex items-center justify-center gap-2 py-2 px-3 rounded-lg text-sm font-medium transition-all"
                style={inputTab === 'record'
                  ? { background: 'white', color: '#1a5d3a', boxShadow: '0 1px 4px rgba(0,0,0,0.08)' }
                  : { color: '#6b7280' }
                }
              >
                <Mic size={15} />
                Record Audio
              </button>
            </div>
          </div>

          {/* Upload / Record component */}
          <div>
            {inputTab === 'upload'
              ? <AudioUploader onFileSelect={handleFileSelect} selectedFile={file} onClear={handleClear} />
              : <AudioRecorder onRecordingComplete={handleRecordingComplete} />
            }
          </div>

          {/* Transcribe button */}
          {file && !loading && (
            <button
              onClick={handleTranscribe}
              className="w-full flex items-center justify-center gap-2 py-3 rounded-xl text-sm font-semibold text-white transition-all hover:-translate-y-0.5 active:translate-y-0"
              style={{ background: 'linear-gradient(135deg, #1a5d3a 0%, #2d8a5e 100%)', boxShadow: '0 4px 14px rgba(26,93,58,0.3)' }}
            >
              <Play size={16} />
              Transcribe Audio
            </button>
          )}

          {/* Pipeline progress */}
          {loading && (
            <div className="border-t border-gray-100 pt-4">
              <p className="text-xs text-gray-400 text-center mb-4">This may take several minutes on CPU.</p>
              <div className="flex flex-col gap-2">
                {STEPS.map(s => (
                  <div
                    key={s.id}
                    className="flex items-center gap-3 px-3 py-2.5 rounded-xl transition-all"
                    style={step === s.id
                      ? { background: 'rgba(26,93,58,0.06)' }
                      : step > s.id
                      ? { opacity: 0.6 }
                      : { opacity: 0.35 }
                    }
                  >
                    <div
                      className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold shrink-0"
                      style={step > s.id
                        ? { background: 'rgba(26,93,58,0.15)', color: '#1a5d3a' }
                        : step === s.id
                        ? { background: '#1a5d3a', color: 'white' }
                        : { background: '#f3f4f6', color: '#9ca3af' }
                      }
                    >
                      {step > s.id
                        ? <CheckCircle size={14} />
                        : step === s.id
                        ? <span className="spinner-sm" />
                        : s.id
                      }
                    </div>
                    <div className="flex flex-col">
                      <span className="text-sm font-semibold text-gray-800">{s.label}</span>
                      <span className="text-xs text-gray-500">{s.desc}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="flex items-start gap-3 p-4 bg-red-50 border border-red-100 rounded-xl text-red-600 text-sm">
              <AlertCircle size={18} className="shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}
        </div>

        {/* ── Right panel: Results ── */}
        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-6 flex flex-col min-h-[420px]">
          {!result && !loading && (
            <div className="flex-1 flex flex-col items-center justify-center text-center gap-3 py-12">
              <div
                className="w-16 h-16 rounded-2xl flex items-center justify-center mb-2"
                style={{ background: '#1a5d3a0f' }}
              >
                <FileAudio size={28} style={{ color: '#1a5d3a' }} />
              </div>
              <p className="font-semibold text-gray-700">No results yet</p>
              <p className="text-sm text-gray-400 max-w-[220px]">
                Upload or record audio on the left, then click <strong>Transcribe Audio</strong> to begin.
              </p>
            </div>
          )}

          {loading && !result && (
            <div className="flex-1 flex flex-col items-center justify-center gap-3 py-12">
              <Loader2 size={36} className="animate-spin" style={{ color: '#1a5d3a' }} />
              <p className="text-sm text-gray-500">Processing audio pipeline…</p>
            </div>
          )}

          {result && (
            <>
              {/* Result tabs */}
              <div className="flex gap-1 p-1 bg-gray-100 rounded-xl mb-5">
                <button
                  onClick={() => setResultTab('transcript')}
                  className="flex-1 flex items-center justify-center gap-2 py-2 px-3 rounded-lg text-sm font-medium transition-all"
                  style={resultTab === 'transcript'
                    ? { background: 'white', color: '#1a5d3a', boxShadow: '0 1px 4px rgba(0,0,0,0.08)' }
                    : { color: '#6b7280' }
                  }
                >
                  <FileText size={15} />
                  Transcript
                </button>
                <button
                  onClick={() => setResultTab('summary')}
                  className="flex-1 flex items-center justify-center gap-2 py-2 px-3 rounded-lg text-sm font-medium transition-all"
                  style={resultTab === 'summary'
                    ? { background: 'white', color: '#1a5d3a', boxShadow: '0 1px 4px rgba(0,0,0,0.08)' }
                    : { color: '#6b7280' }
                  }
                >
                  <ClipboardList size={15} />
                  Clinical Note
                </button>
              </div>

              <div className="flex-1 overflow-auto">
                {resultTab === 'transcript'
                  ? <TranscriptViewer words={result.words} audioFile={file} />
                  : <SummaryViewer summary={result.summary} />
                }
              </div>
            </>
          )}
        </div>
      </div>
    </motion.div>
  );
}
