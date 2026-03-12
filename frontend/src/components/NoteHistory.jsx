import { useState } from "react";
import { Input } from "./ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "./ui/dialog";
import { Search } from "lucide-react";
import { motion, AnimatePresence } from "motion/react";

export function NoteHistory() {
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedNote, setSelectedNote] = useState(null);

  const notes = [
    { patient: "John Smith", type: "SOAP", date: "Mar 12, 2026", time: "9:30 AM", status: "Signed",
      content: "Chief Complaint: Persistent dry cough for one week\n\nHistory of Present Illness:\nThe patient presents with a one-week history of persistent dry cough..." },
    { patient: "Emily Davis", type: "Progress", date: "Mar 12, 2026", time: "8:15 AM", status: "Signed",
      content: "Interval History: Patient returns for routine follow-up of asthma..." },
    { patient: "Michael Brown", type: "Consultation", date: "Mar 11, 2026", time: "4:45 PM", status: "Signed",
      content: "Reason for Consultation: Evaluation of atypical chest pain..." },
    { patient: "Sarah Wilson", type: "SOAP", date: "Mar 10, 2026", time: "2:30 PM", status: "Signed",
      content: "Chief Complaint: Annual physical examination..." },
    { patient: "David Martinez", type: "Progress", date: "Mar 9, 2026", time: "11:00 AM", status: "Review",
      content: "Interval History: Patient returns for management of hypertension and coronary artery disease..." },
    { patient: "Jennifer Lee", type: "SOAP", date: "Mar 8, 2026", time: "3:15 PM", status: "Signed",
      content: "Chief Complaint: Severe migraine headache..." },
    { patient: "Robert Taylor", type: "Progress", date: "Mar 7, 2026", time: "10:45 AM", status: "Signed",
      content: "Interval History: Follow-up for diabetes management..." },
    { patient: "Lisa Anderson", type: "SOAP", date: "Mar 6, 2026", time: "1:20 PM", status: "Signed",
      content: "Chief Complaint: Lower back pain..." },
  ];

  const filteredNotes = notes.filter(
    (note) =>
      note.patient.toLowerCase().includes(searchQuery.toLowerCase()) ||
      note.type.toLowerCase().includes(searchQuery.toLowerCase())
  );

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
          <p className="text-xs uppercase tracking-widest text-slate-500 mb-4">Archive</p>
          <h1 className="text-5xl font-light text-slate-900 tracking-tight">Note History</h1>
        </div>
      </motion.section>

      <div className="max-w-[1600px] mx-auto px-12 py-16">
        {/* Search */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.2, ease: [0.19, 1.0, 0.22, 1.0] }}
          className="mb-12"
        >
          <div className="relative">
            <Search className="absolute left-0 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <Input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search notes"
              className="pl-8 border-0 border-b border-slate-200 rounded-none focus:border-slate-900 focus:ring-0 text-lg bg-transparent"
            />
          </div>
        </motion.div>

        {/* Table Header */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.3, ease: [0.19, 1.0, 0.22, 1.0] }}
          className="grid grid-cols-12 gap-4 px-8 py-4 border-b border-slate-200"
        >
          <div className="col-span-3"><span className="text-xs uppercase tracking-widest text-slate-500">Patient</span></div>
          <div className="col-span-2"><span className="text-xs uppercase tracking-widest text-slate-500">Type</span></div>
          <div className="col-span-3"><span className="text-xs uppercase tracking-widest text-slate-500">Date</span></div>
          <div className="col-span-2"><span className="text-xs uppercase tracking-widest text-slate-500">Time</span></div>
          <div className="col-span-2"><span className="text-xs uppercase tracking-widest text-slate-500">Status</span></div>
        </motion.div>

        {/* Note Rows */}
        <div>
          {filteredNotes.map((note, index) => (
            <motion.div
              key={index}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, delay: 0.4 + index * 0.03, ease: [0.19, 1.0, 0.22, 1.0] }}
              onClick={() => setSelectedNote(note)}
              className="grid grid-cols-12 gap-4 px-8 py-6 border-b border-slate-100 hover:bg-slate-50 transition-colors cursor-pointer"
            >
              <div className="col-span-3"><span className="text-sm font-medium text-slate-900">{note.patient}</span></div>
              <div className="col-span-2"><span className="text-sm text-slate-600">{note.type}</span></div>
              <div className="col-span-3"><span className="text-sm text-slate-600">{note.date}</span></div>
              <div className="col-span-2"><span className="text-sm font-mono text-slate-500">{note.time}</span></div>
              <div className="col-span-2"><span className="text-xs uppercase tracking-wider text-slate-400">{note.status}</span></div>
            </motion.div>
          ))}
        </div>

        {filteredNotes.length === 0 && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="text-center py-24">
            <p className="text-sm text-slate-400">No notes found</p>
          </motion.div>
        )}
      </div>

      {/* Note Detail Dialog */}
      <AnimatePresence>
        {selectedNote && (
          <Dialog open={!!selectedNote} onOpenChange={() => setSelectedNote(null)}>
            <DialogContent className="max-w-3xl border-0 shadow-2xl p-0">
              <DialogHeader className="p-12 border-b border-slate-200">
                <div className="flex items-start justify-between">
                  <div>
                    <DialogTitle className="text-2xl font-light text-slate-900 mb-2">
                      {selectedNote.patient}
                    </DialogTitle>
                    <div className="flex items-center gap-4 text-sm text-slate-600">
                      <span>{selectedNote.type}</span>
                      <span>•</span>
                      <span>{selectedNote.date}</span>
                      <span>•</span>
                      <span className="font-mono">{selectedNote.time}</span>
                    </div>
                  </div>
                </div>
              </DialogHeader>
              <div className="p-12">
                <pre className="text-sm text-slate-700 leading-relaxed whitespace-pre-wrap font-sans">
                  {selectedNote.content}
                </pre>
              </div>
            </DialogContent>
          </Dialog>
        )}
      </AnimatePresence>
    </div>
  );
}
