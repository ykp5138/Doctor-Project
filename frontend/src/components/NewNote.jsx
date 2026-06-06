import { useState, useRef, useCallback, useEffect, useMemo } from "react";
import { Label } from "./ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select";
import { Input } from "./ui/input";
import { Mic, MicOff, Circle, Upload, X } from "lucide-react";
import { motion, AnimatePresence } from "motion/react";
import TranscriptViewer from "./TranscriptViewer";
import SummaryViewer from "./SummaryViewer";
import SuggestedCodes from "./SuggestedCodes";
import { useNote } from "../NoteContext";

const STEPS = [
  { id: 1, label: "WhisperX", desc: "Transcribing + diarizing audio" },
  { id: 2, label: "AssemblyAI", desc: "Cloud transcription" },
  { id: 3, label: "Kevin", desc: "Merging + generating summary" },
];

export default function NewNote() {
  // Persistent state (survives navigation)
  const {
    result, setResult, words, setWords, file, setFile,
    patientName, setPatientName, noteType, setNoteType,
    resultTab, setResultTab, keywords, setKeywords,
    codeRange, setCodeRange, icdSuggestions, setIcdSuggestions,
  } = useNote();

  // Audio source
  const [inputTab, setInputTab] = useState("upload");

  // Upload state
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef(null);

  // Recording state
  const [isRecording, setIsRecording] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [recordingTime, setRecordingTime] = useState(0);
  const mediaRecorderRef = useRef(null);
  const chunksRef = useRef([]);
  const intervalRef = useRef(null);

  // Pipeline state
  const [loading, setLoading] = useState(false);
  const [step, setStep] = useState(0);
  const [error, setError] = useState(null);
  const stepTimer = useRef(null);

  // ICD suggestion state
  const [icdLoading, setIcdLoading] = useState(false);
  const [icdActiveCodeIdx, setIcdActiveCodeIdx] = useState(null);
  const [icdActiveEvidenceIdx, setIcdActiveEvidenceIdx] = useState(0);

  // Transient confirmation after a feedback ✓/✗ click
  const [feedbackToast, setFeedbackToast] = useState(null);
  const feedbackToastTimer = useRef(null);

  // Patient name warning
  const [nameWarning, setNameWarning] = useState(false);
  const nameWarningShown = useRef(false);

  // ── Upload handlers ──
  const handleDragOver = (e) => { e.preventDefault(); setIsDragging(true); };
  const handleDragLeave = (e) => { e.preventDefault(); setIsDragging(false); };
  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    const f = e.dataTransfer.files?.[0];
    if (f && (f.type.startsWith("audio/") || f.type === "video/quicktime" || f.name.toLowerCase().endsWith(".mov"))) { setFile(f); setResult(null); setWords([]); setError(null); setIcdSuggestions([]); setIcdActiveCodeIdx(null); }
  };
  const handleFileChange = (e) => {
    const f = e.target.files?.[0];
    if (f) { setFile(f); setResult(null); setWords([]); setError(null); setIcdSuggestions([]); setIcdActiveCodeIdx(null); }
  };
  const formatFileSize = (bytes) => {
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  // ── Recording handlers ──
  const startRecording = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;
      chunksRef.current = [];
      mediaRecorder.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data); };
      mediaRecorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        setFile(new File([blob], "recording.webm", { type: "audio/webm" }));
        stream.getTracks().forEach((t) => t.stop());
        setIsRecording(false);
        setIsPaused(false);
        setInputTab("upload");
      };
      mediaRecorder.start();
      setIsRecording(true);
      setRecordingTime(0);
      intervalRef.current = setInterval(() => setRecordingTime((d) => d + 1), 1000);
    } catch (err) {
      console.error("Microphone error:", err);
    }
  }, []);

  const stopRecording = useCallback(() => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      clearInterval(intervalRef.current);
    }
  }, [isRecording]);

  const togglePause = useCallback(() => {
    if (!mediaRecorderRef.current) return;
    if (isPaused) {
      mediaRecorderRef.current.resume();
      intervalRef.current = setInterval(() => setRecordingTime((d) => d + 1), 1000);
    } else {
      mediaRecorderRef.current.pause();
      clearInterval(intervalRef.current);
    }
    setIsPaused(!isPaused);
  }, [isPaused]);

  const formatTime = (seconds) => {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${s.toString().padStart(2, "0")}`;
  };

  // ── ICD helpers ──
  const handleSelectEvidence = useCallback((codeIdx, evIdx) => {
    setIcdActiveCodeIdx(codeIdx);
    setIcdActiveEvidenceIdx(evIdx ?? 0);
  }, []);

  const handleFeedback = useCallback((code, phrase, wordIndices, isCorrect) => {
    const showToast = (msg) => {
      setFeedbackToast(msg);
      if (feedbackToastTimer.current) clearTimeout(feedbackToastTimer.current);
      feedbackToastTimer.current = setTimeout(() => setFeedbackToast(null), 1600);
    };
    // Optimistic confirmation — shown immediately, never blocks the doctor's flow.
    showToast(`${isCorrect ? '✓ Correct' : '✗ Incorrect'} — ${code} recorded`);

    const sug = icdSuggestions.find((s) => s.code === code);
    fetch('http://localhost:8000/feedback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        code,
        description: sug?.description ?? '',
        evidence_phrase: phrase,
        word_indices: wordIndices ?? [],
        is_correct: isCorrect,
        transcript_base: result?.meta?.base ?? null,
        concepts: result?.concepts ?? null,
      }),
    })
      // Surface a real write failure (non-2xx or network error) instead of the
      // false "recorded" toast — e.g. a OneDrive file lock blocking the append.
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
      })
      .catch(() => showToast(`⚠ Failed to record ${code} — not saved`));
  }, [icdSuggestions, result]);

  // Derive which word indices to highlight and which single word to focus/scroll to
  const icdHighlightedIndices = useMemo(() => {
    if (icdActiveCodeIdx === null || !icdSuggestions[icdActiveCodeIdx]) return new Set();
    const ev = icdSuggestions[icdActiveCodeIdx].evidence[icdActiveEvidenceIdx];
    return new Set(ev?.word_indices ?? []);
  }, [icdSuggestions, icdActiveCodeIdx, icdActiveEvidenceIdx]);

  const icdFocusedIndex = useMemo(() => {
    if (icdActiveCodeIdx === null || !icdSuggestions[icdActiveCodeIdx]) return null;
    const ev = icdSuggestions[icdActiveCodeIdx].evidence[icdActiveEvidenceIdx];
    return ev?.word_indices?.[0] ?? null;
  }, [icdSuggestions, icdActiveCodeIdx, icdActiveEvidenceIdx]);

  // Arrow-key navigation between evidence phrases (like Ctrl+F instances)
  useEffect(() => {
    if (icdActiveCodeIdx === null) return;
    const sug = icdSuggestions[icdActiveCodeIdx];
    if (!sug) return;
    const handler = (e) => {
      if (e.key === 'ArrowRight') {
        e.preventDefault();
        setIcdActiveEvidenceIdx(i => Math.min(i + 1, sug.evidence.length - 1));
      } else if (e.key === 'ArrowLeft') {
        e.preventDefault();
        setIcdActiveEvidenceIdx(i => Math.max(i - 1, 0));
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [icdActiveCodeIdx, icdSuggestions]);

  // ── Transcribe ──
  const handleTranscribe = async () => {
    if (!file) return;

    // Name validation: flash warning on first attempt, proceed on second
    if (!patientName.trim() && !nameWarningShown.current) {
      nameWarningShown.current = true;
      setNameWarning(true);
      setTimeout(() => setNameWarning(false), 2000);
      return;
    }

    setLoading(true);
    setStep(1);
    setError(null);
    setResult(null);
    setWords([]);
    setIcdSuggestions([]);
    setIcdActiveCodeIdx(null);
    setIcdActiveEvidenceIdx(0);

    stepTimer.current = setTimeout(() => setStep(2), 25000);
    const t2 = setTimeout(() => setStep(3), 55000);

    const formData = new FormData();
    formData.append("file", file);
    if (keywords.trim()) formData.append("keywords", keywords.trim());
    if (patientName.trim()) formData.append("patient_name", patientName.trim());

    try {
      const res = await fetch("http://localhost:8000/transcribe", {
        method: "POST",
        body: formData,
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        throw new Error(detail.detail || "Transcription failed");
      }
      const data = await res.json();
      setResult(data);
      setWords(data.words || []);
      setResultTab("transcript");

      // Fire ICD suggestion asynchronously — doesn't block transcript display
      if (codeRange.trim() || true) {
        setIcdLoading(true);
        fetch('http://localhost:8000/suggest-codes', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ words: data.words, summary: data.summary || '', code_range: codeRange.trim(), concepts: data.concepts }),
        })
          .then(r => r.json())
          .then(d => setIcdSuggestions(d.suggestions || []))
          .catch(() => setIcdSuggestions([]))
          .finally(() => setIcdLoading(false));
      }
    } catch (err) {
      setError(err.message || "An error occurred");
    } finally {
      clearTimeout(stepTimer.current);
      clearTimeout(t2);
      setLoading(false);
      setStep(0);
    }
  };

  const canTranscribe = file && !loading;

  return (
    <div className="min-h-screen">
      {/* Header */}
      <motion.section
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.8, ease: [0.19, 1.0, 0.22, 1.0] }}
        className="border-b border-slate-200"
      >
        <div className="max-w-[1600px] mx-auto px-12 py-16">
          <p className="text-xs uppercase tracking-widest text-slate-500 mb-4">New Documentation</p>
          <h1 className="text-5xl font-light text-slate-900 tracking-tight">Clinical Note</h1>
        </div>
      </motion.section>

      <div className="max-w-[1600px] mx-auto px-12 py-16">
        <div className="grid grid-cols-2 gap-px bg-slate-200">

          {/* ── Left Panel: Input ── */}
          <motion.div
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.8, delay: 0.2, ease: [0.19, 1.0, 0.22, 1.0] }}
            className="bg-white p-12"
          >
            {/* Patient info */}
            <div className="mb-16 space-y-8">
              <div>
                <Label className="text-xs uppercase tracking-widest text-slate-500 mb-3 block">Patient Name</Label>
                <Input
                  value={patientName}
                  onChange={(e) => { setPatientName(e.target.value); nameWarningShown.current = false; setNameWarning(false); }}
                  placeholder="Enter name"
                  className={`border-0 border-b rounded-none px-0 focus:ring-0 text-lg bg-transparent transition-colors ${nameWarning ? 'border-red-400 focus:border-red-400' : 'border-slate-200 focus:border-slate-900'}`}
                />
                <AnimatePresence>
                  {nameWarning && (
                    <motion.p
                      initial={{ opacity: 0, y: -4 }}
                      animate={{ opacity: [0, 1, 0.4, 1, 0.4, 1] }}
                      exit={{ opacity: 0 }}
                      transition={{ duration: 0.8 }}
                      className="text-xs text-red-500 mt-2"
                    >
                      Please enter a patient name. Press Transcribe again to skip.
                    </motion.p>
                  )}
                </AnimatePresence>
              </div>
              <div>
                <Label className="text-xs uppercase tracking-widest text-slate-500 mb-3 block">Note Type</Label>
                <Select value={noteType} onValueChange={setNoteType}>
                  <SelectTrigger className="border-0 border-b border-slate-200 rounded-none px-0 focus:border-slate-900 focus:ring-0 text-lg bg-transparent h-auto py-2">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="soap">SOAP Note</SelectItem>
                    <SelectItem value="progress">Progress Note</SelectItem>
                    <SelectItem value="consultation">Consultation</SelectItem>
                    <SelectItem value="procedure">Procedure Note</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-xs uppercase tracking-widest text-slate-500 mb-3 block">Code Range <span className="normal-case text-slate-400">(optional — e.g. E11-E14, J45.50, L00-L99)</span></Label>
                <Input
                  value={codeRange}
                  onChange={(e) => setCodeRange(e.target.value)}
                  placeholder="e.g. I00-I99, E11.9, L00-L99"
                  className="border-0 border-b border-slate-200 rounded-none px-0 focus:border-slate-900 focus:ring-0 text-base bg-transparent"
                />
              </div>
              <div>
                <Label className="text-xs uppercase tracking-widest text-slate-500 mb-3 block">Keywords <span className="normal-case text-slate-400">(optional — medicines, terms)</span></Label>
                <Input
                  value={keywords}
                  onChange={(e) => setKeywords(e.target.value)}
                  placeholder="e.g. metformin, lisinopril, HbA1c"
                  className="border-0 border-b border-slate-200 rounded-none px-0 focus:border-slate-900 focus:ring-0 text-base bg-transparent"
                />
              </div>
            </div>

            {/* Audio source toggle */}
            <div className="mb-8">
              <div className="flex items-center justify-between mb-4">
                <span className="text-xs uppercase tracking-widest text-slate-500">Audio Source</span>
                <div className="flex gap-px bg-slate-200">
                  <button
                    onClick={() => setInputTab("upload")}
                    className={`px-4 py-1.5 text-xs uppercase tracking-widest transition-colors ${inputTab === "upload" ? "bg-slate-900 text-white" : "bg-white text-slate-500 hover:text-slate-900"}`}
                  >
                    Upload
                  </button>
                  <button
                    onClick={() => setInputTab("record")}
                    className={`px-4 py-1.5 text-xs uppercase tracking-widest transition-colors ${inputTab === "record" ? "bg-slate-900 text-white" : "bg-white text-slate-500 hover:text-slate-900"}`}
                  >
                    Record
                  </button>
                </div>
              </div>

              {/* Upload zone */}
              {inputTab === "upload" && (
                <>
                  <input ref={fileInputRef} type="file" accept="audio/*,video/quicktime,.mov" onChange={handleFileChange} className="hidden" />
                  {!file ? (
                    <div
                      onDragOver={handleDragOver}
                      onDragLeave={handleDragLeave}
                      onDrop={handleDrop}
                      onClick={() => fileInputRef.current?.click()}
                      className={`w-full py-16 border border-dashed cursor-pointer transition-colors flex flex-col items-center gap-4 ${isDragging ? "border-slate-900 bg-slate-50" : "border-slate-200 hover:border-slate-400"}`}
                    >
                      <Upload className={`w-6 h-6 transition-colors ${isDragging ? "text-slate-900" : "text-slate-400"}`} />
                      <span className="text-sm text-slate-500">Drop audio file or click to browse</span>
                      <span className="text-xs text-slate-400">MP3, WAV, M4A, WebM, MOV</span>
                    </div>
                  ) : (
                    <div className="border border-slate-200 px-6 py-4 flex items-center justify-between">
                      <div>
                        <p className="text-sm font-medium text-slate-900">{file.name}</p>
                        <p className="text-xs text-slate-500 mt-0.5">{formatFileSize(file.size)}</p>
                      </div>
                      <button
                        onClick={() => { setFile(null); setResult(null); setWords([]); setError(null); }}
                        className="text-slate-400 hover:text-slate-900 transition-colors"
                      >
                        <X className="w-4 h-4" />
                      </button>
                    </div>
                  )}
                </>
              )}

              {/* Record zone */}
              {inputTab === "record" && (
                <div>
                  <div className="flex items-center justify-between mb-4">
                    <span className="text-xs text-slate-400">Recording</span>
                    <span className="font-mono text-2xl text-slate-900 tracking-tight">{formatTime(recordingTime)}</span>
                  </div>

                  <button
                    onClick={isRecording ? stopRecording : startRecording}
                    className="w-full py-16 border border-slate-200 hover:border-slate-900 transition-colors group"
                  >
                    <div className="flex flex-col items-center gap-6">
                      <AnimatePresence mode="wait">
                        {isRecording ? (
                          <motion.div
                            key="recording"
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            exit={{ opacity: 0 }}
                            className="relative"
                          >
                            <MicOff className="w-8 h-8 text-slate-900" />
                            <motion.div
                              className="absolute -inset-4 border border-slate-900"
                              animate={{ opacity: [1, 0] }}
                              transition={{ duration: 1.5, repeat: Infinity }}
                            />
                          </motion.div>
                        ) : (
                          <motion.div key="idle" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                            <Mic className="w-8 h-8 text-slate-400 group-hover:text-slate-900 transition-colors" />
                          </motion.div>
                        )}
                      </AnimatePresence>
                      <span className="text-sm text-slate-500 group-hover:text-slate-900 transition-colors">
                        {isRecording ? "Stop Recording" : "Start Recording"}
                      </span>
                    </div>
                  </button>

                  {isRecording && (
                    <button
                      onClick={togglePause}
                      className="w-full mt-px py-3 border border-slate-200 text-xs uppercase tracking-widest text-slate-500 hover:text-slate-900 hover:border-slate-900 transition-colors"
                    >
                      {isPaused ? "Resume" : "Pause"}
                    </button>
                  )}
                </div>
              )}
            </div>

            {/* Transcribe button */}
            {canTranscribe && (
              <button
                onClick={handleTranscribe}
                className="w-full h-14 bg-slate-900 hover:bg-slate-700 text-white text-sm uppercase tracking-widest transition-colors mt-4"
              >
                Transcribe Audio
              </button>
            )}

            {/* Pipeline progress */}
            {loading && (
              <div className="mt-8 space-y-2">
                <p className="text-xs text-slate-400 mb-4">This may take several minutes on CPU.</p>
                {STEPS.map((s) => (
                  <div
                    key={s.id}
                    className="flex items-center gap-4 px-4 py-3 transition-all"
                    style={step === s.id ? { background: "#f5f5f5" } : { opacity: step > s.id ? 0.5 : 0.3 }}
                  >
                    <div
                      className="w-6 h-6 flex items-center justify-center text-xs font-medium shrink-0"
                      style={step > s.id
                        ? { background: "#1a1a1a", color: "white" }
                        : step === s.id
                        ? { background: "#1a1a1a", color: "white" }
                        : { background: "#e5e5e5", color: "#737373" }
                      }
                    >
                      {step === s.id ? <span className="spinner-sm" /> : step > s.id ? "✓" : s.id}
                    </div>
                    <div>
                      <p className="text-sm font-medium text-slate-900">{s.label}</p>
                      <p className="text-xs text-slate-500">{s.desc}</p>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Error */}
            {error && (
              <div className="mt-6 px-4 py-3 border border-red-200 bg-red-50 text-red-700 text-sm">
                {error}
              </div>
            )}
          </motion.div>

          {/* ── Right Panel: Output ── */}
          <motion.div
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.8, delay: 0.3, ease: [0.19, 1.0, 0.22, 1.0] }}
            className="bg-slate-50 p-12"
          >
            <div className="mb-8">
              <span className="text-xs uppercase tracking-widest text-slate-500">Generated Output</span>
            </div>

            <AnimatePresence mode="wait">
              {!result && !loading && (
                <motion.div
                  key="empty"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="flex items-center justify-center h-[600px]"
                >
                  <div className="text-center">
                    <Circle className="w-4 h-4 text-slate-300 mx-auto mb-4" />
                    <p className="text-sm text-slate-400">Awaiting generation</p>
                  </div>
                </motion.div>
              )}

              {loading && !result && (
                <motion.div
                  key="loading"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="flex items-center justify-center h-[600px]"
                >
                  <div className="text-center">
                    <div className="w-5 h-5 border-2 border-slate-300 border-t-slate-900 rounded-full animate-spin mx-auto mb-4" />
                    <p className="text-sm text-slate-400">Processing pipeline…</p>
                  </div>
                </motion.div>
              )}

              {result && (
                <motion.div
                  key="result"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="space-y-6"
                >
                  {/* Result tabs */}
                  <div className="flex gap-px bg-slate-200">
                    <button
                      onClick={() => setResultTab("transcript")}
                      className={`flex-1 py-2.5 text-xs uppercase tracking-widest transition-colors ${resultTab === "transcript" ? "bg-slate-900 text-white" : "bg-white text-slate-500 hover:text-slate-900"}`}
                    >
                      Transcript
                    </button>
                    <button
                      onClick={() => setResultTab("summary")}
                      className={`flex-1 py-2.5 text-xs uppercase tracking-widest transition-colors ${resultTab === "summary" ? "bg-slate-900 text-white" : "bg-white text-slate-500 hover:text-slate-900"}`}
                    >
                      Clinical Note
                    </button>
                  </div>

                  <div className="bg-white p-8">
                    {resultTab === "transcript" ? (
                      <>
                        {(icdLoading || icdSuggestions.length > 0) && (
                          <SuggestedCodes
                            suggestions={icdSuggestions}
                            loading={icdLoading}
                            activeCodeIdx={icdActiveCodeIdx}
                            activeEvidenceIdx={icdActiveEvidenceIdx}
                            onSelectEvidence={handleSelectEvidence}
                            onFeedback={handleFeedback}
                          />
                        )}
                        <TranscriptViewer
                          words={words}
                          setWords={setWords}
                          audioFile={file}
                          icdHighlightedIndices={icdHighlightedIndices}
                          icdFocusedIndex={icdFocusedIndex}
                        />
                      </>
                    ) : (
                      <SummaryViewer summary={result.summary} audioFile={file} />
                    )}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </motion.div>

        </div>
      </div>

      {/* Feedback confirmation toast */}
      <AnimatePresence>
        {feedbackToast && (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 12 }}
            transition={{ duration: 0.2 }}
            className="fixed bottom-8 right-8 z-50 bg-slate-900 text-white text-sm px-5 py-3 shadow-lg"
          >
            {feedbackToast}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
