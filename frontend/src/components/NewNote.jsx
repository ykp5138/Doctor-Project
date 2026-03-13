import { useState, useRef, useCallback } from "react";
import { Label } from "./ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select";
import { Input } from "./ui/input";
import { Mic, MicOff, Circle, Upload, X } from "lucide-react";
import { motion, AnimatePresence } from "motion/react";
import TranscriptViewer from "./TranscriptViewer";
import SummaryViewer from "./SummaryViewer";
import { useNote } from "../NoteContext";

const STEPS = [
  { id: 1, label: "WhisperX", desc: "Transcribing + diarizing audio" },
  { id: 2, label: "AssemblyAI", desc: "Cloud transcription" },
  { id: 3, label: "Kevin", desc: "Merging + generating summary" },
];

export default function NewNote() {
  // Persistent state (survives navigation)
  const { result, setResult, words, setWords, file, setFile, patientName, setPatientName, noteType, setNoteType, resultTab, setResultTab, keywords, setKeywords } = useNote();

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

  // ── Upload handlers ──
  const handleDragOver = (e) => { e.preventDefault(); setIsDragging(true); };
  const handleDragLeave = (e) => { e.preventDefault(); setIsDragging(false); };
  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    const f = e.dataTransfer.files?.[0];
    if (f && f.type.startsWith("audio/")) { setFile(f); setResult(null); setWords([]); setError(null); }
  };
  const handleFileChange = (e) => {
    const f = e.target.files?.[0];
    if (f) { setFile(f); setResult(null); setWords([]); setError(null); }
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

  // ── Transcribe ──
  const handleTranscribe = async () => {
    if (!file) return;
    setLoading(true);
    setStep(1);
    setError(null);
    setResult(null);
    setWords([]);

    stepTimer.current = setTimeout(() => setStep(2), 25000);
    const t2 = setTimeout(() => setStep(3), 55000);

    const formData = new FormData();
    formData.append("file", file);

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
                  onChange={(e) => setPatientName(e.target.value)}
                  placeholder="Enter name"
                  className="border-0 border-b border-slate-200 rounded-none px-0 focus:border-slate-900 focus:ring-0 text-lg bg-transparent"
                />
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
                  <input ref={fileInputRef} type="file" accept="audio/*" onChange={handleFileChange} className="hidden" />
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
                      <span className="text-xs text-slate-400">MP3, WAV, M4A, WebM</span>
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
                    {resultTab === "transcript"
                      ? <TranscriptViewer words={words} setWords={setWords} audioFile={file} />
                      : <SummaryViewer summary={result.summary} audioFile={file} />
                    }
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </motion.div>

        </div>
      </div>
    </div>
  );
}
