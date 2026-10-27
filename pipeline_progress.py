"""Small, process-local progress registry; never stores recording or patient data."""
import threading
import time


class DuplicateJobError(ValueError):
    pass


class ProgressCapacityError(RuntimeError):
    pass


class PipelineProgressStore:
    """Bounded single-worker tracking with short-lived completed records."""

    STAGES = ("whisperx", "assemblyai", "kevin")
    TERMINAL = ("completed", "failed")

    def __init__(self, max_jobs=128, terminal_ttl_seconds=3600, clock=None):
        self.max_jobs = max_jobs
        self.terminal_ttl_seconds = terminal_ttl_seconds
        self._clock = clock or time.perf_counter
        self._jobs = {}
        self._lock = threading.Lock()

    def _prune(self, now):
        expired = [job_id for job_id, job in self._jobs.items()
                   if job["finished_at"] is not None
                   and now - job["finished_at"] >= self.terminal_ttl_seconds]
        for job_id in expired:
            del self._jobs[job_id]

    def create(self, job_id):
        with self._lock:
            now = self._clock()
            self._prune(now)
            if job_id in self._jobs:
                raise DuplicateJobError("This job ID is already registered")
            if len(self._jobs) >= self.max_jobs:
                terminal = [key for key, value in self._jobs.items()
                            if value["finished_at"] is not None]
                if not terminal:
                    raise ProgressCapacityError("Progress tracker is busy; try again shortly")
                oldest = min(terminal, key=lambda key: self._jobs[key]["finished_at"])
                del self._jobs[oldest]
            self._jobs[job_id] = {
                "status": "pending",
                "finished_at": None,
                "stages": {stage: {"status": "pending", "started_at": None,
                                   "elapsed_seconds": None} for stage in self.STAGES},
            }

    def start_stage(self, job_id, stage):
        with self._lock:
            job = self._jobs[job_id]
            if job["status"] in self.TERMINAL:
                return
            job["status"] = "running"
            job["stages"][stage].update(status="running", started_at=self._clock())

    def finish_stage(self, job_id, stage, failed=False):
        with self._lock:
            job = self._jobs[job_id]
            if job["status"] in self.TERMINAL:
                return
            entry = job["stages"][stage]
            entry["status"] = "failed" if failed else "completed"
            if entry["started_at"] is not None:
                entry["elapsed_seconds"] = round(self._clock() - entry["started_at"], 3)

    def finish_job(self, job_id, failed=False):
        with self._lock:
            job = self._jobs[job_id]
            now = self._clock()
            if failed:
                for stage in job["stages"].values():
                    if stage["status"] == "pending":
                        stage["status"] = "skipped"
                    elif stage["status"] == "running":
                        stage["status"] = "failed"
                        stage["elapsed_seconds"] = round(now - stage["started_at"], 3)
            job["status"] = "failed" if failed else "completed"
            job["finished_at"] = now

    def snapshot(self, job_id):
        with self._lock:
            now = self._clock()
            self._prune(now)
            job = self._jobs.get(job_id)
            if job is None:
                return None
            stages = {}
            for name, stage in job["stages"].items():
                elapsed = stage["elapsed_seconds"]
                if stage["status"] == "running":
                    elapsed = round(now - stage["started_at"], 3)
                stages[name] = {"status": stage["status"], "elapsed_seconds": elapsed}
            return {"job_id": job_id, "status": job["status"], "stages": stages}
