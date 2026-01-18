import { useState, useRef, useCallback } from "react";

export function AudioRecorder({ onRecordingComplete }) {
    const [isRecording, setIsRecording] = useState(false);
    const [isPaused, setIsPaused] = useState(false);
    const [duration, setDuration] = useState(0);
    const mediaRecorderRef = useRef(null);
    const chunksRef = useRef([]);
    const intervalRef = useRef(null);

    const startRecording = useCallback(async () => {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            const mediaRecorder = new MediaRecorder(stream);
            mediaRecorderRef.current = mediaRecorder;
            chunksRef.current = [];

            mediaRecorder.ondataavailable = (e) => {
                if (e.data.size > 0) {
                    chunksRef.current.push(e.data);
                }
            };

            mediaRecorder.onstop = () => {
                const blob = new Blob(chunksRef.current, { type: "audio/webm" });
                onRecordingComplete(blob);
                stream.getTracks().forEach((track) => track.stop());
            };

            mediaRecorder.start();
            setIsRecording(true);
            setDuration(0);

            intervalRef.current = setInterval(() => {
                setDuration((d) => d + 1);
            }, 1000);
        } catch (err) {
            console.error("Error accessing microphone:", err);
        }
    }, [onRecordingComplete]);

    const stopRecording = useCallback(() => {
        if (mediaRecorderRef.current && isRecording) {
            mediaRecorderRef.current.stop();
            setIsRecording(false);
            setIsPaused(false);
            if (intervalRef.current) {
                clearInterval(intervalRef.current);
            }
        }
    }, [isRecording]);

    const togglePause = useCallback(() => {
        if (mediaRecorderRef.current) {
            if (isPaused) {
                mediaRecorderRef.current.resume();
                intervalRef.current = setInterval(() => {
                    setDuration((d) => d + 1);
                }, 1000);
            } else {
                mediaRecorderRef.current.pause();
                if (intervalRef.current) {
                    clearInterval(intervalRef.current);
                }
            }
            setIsPaused(!isPaused);
        }
    }, [isPaused]);

    const formatTime = (seconds) => {
        const mins = Math.floor(seconds / 60);
        const secs = seconds % 60;
        return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
    };

    return (
        <div className="recorder-container">
            {/* Recording indicator */}
            <div className={`recorder-circle ${isRecording ? (isPaused ? 'paused' : 'recording') : ''}`}>
                {isRecording ? (
                    <div className="recorder-status">
                        <div className={`recorder-time ${isPaused ? 'paused' : ''}`}>
                            {formatTime(duration)}
                        </div>
                        <div className={`recorder-label ${isPaused ? 'paused' : ''}`}>
                            {isPaused ? "Paused" : "Recording"}
                        </div>
                    </div>
                ) : (
                    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="mic-icon">
                        <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" />
                        <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
                        <line x1="12" x2="12" y1="19" y2="22" />
                    </svg>
                )}
            </div>

            {/* Controls */}
            <div className="recorder-controls">
                {!isRecording ? (
                    <button onClick={startRecording} className="btn btn-primary btn-lg">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" />
                            <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
                            <line x1="12" x2="12" y1="19" y2="22" />
                        </svg>
                        Start Recording
                    </button>
                ) : (
                    <>
                        <button onClick={togglePause} className="btn btn-outline btn-lg">
                            {isPaused ? (
                                <>
                                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                        <polygon points="5 3 19 12 5 21 5 3" />
                                    </svg>
                                    Resume
                                </>
                            ) : (
                                <>
                                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                        <rect width="4" height="16" x="6" y="4" />
                                        <rect width="4" height="16" x="14" y="4" />
                                    </svg>
                                    Pause
                                </>
                            )}
                        </button>
                        <button onClick={stopRecording} className="btn btn-danger btn-lg">
                            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                <rect width="14" height="14" x="5" y="5" rx="2" />
                            </svg>
                            Stop
                        </button>
                    </>
                )}
            </div>
        </div>
    );
}
