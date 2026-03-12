import { useState } from 'react';
import { motion } from 'framer-motion';
import { Search, FileText, Eye } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

const sampleNotes = [
  { patient: 'John Smith', type: 'SOAP Note', date: 'Mar 12, 2026', time: '10:32 AM', status: 'Complete', initials: 'JS' },
  { patient: 'Emily Davis', type: 'Progress Note', date: 'Mar 12, 2026', time: '9:15 AM', status: 'Complete', initials: 'ED' },
  { patient: 'Robert Chen', type: 'Consultation', date: 'Mar 11, 2026', time: '3:45 PM', status: 'Complete', initials: 'RC' },
  { patient: 'Maria Lopez', type: 'SOAP Note', date: 'Mar 11, 2026', time: '11:00 AM', status: 'Complete', initials: 'ML' },
  { patient: 'David Park', type: 'Procedure Note', date: 'Mar 10, 2026', time: '2:20 PM', status: 'Complete', initials: 'DP' },
  { patient: 'Sarah White', type: 'Progress Note', date: 'Mar 10, 2026', time: '9:00 AM', status: 'Complete', initials: 'SW' },
  { patient: 'James Wilson', type: 'SOAP Note', date: 'Mar 9, 2026', time: '4:30 PM', status: 'Complete', initials: 'JW' },
  { patient: 'Linda Brown', type: 'Consultation', date: 'Mar 9, 2026', time: '10:15 AM', status: 'Complete', initials: 'LB' },
];

export default function NoteHistory() {
  const [search, setSearch] = useState('');
  const navigate = useNavigate();

  const filtered = sampleNotes.filter(n =>
    n.patient.toLowerCase().includes(search.toLowerCase()) ||
    n.type.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <motion.div
      className="max-w-5xl mx-auto px-6 py-10"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
    >
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Note History</h1>
          <p className="text-sm text-gray-500 mt-1">Browse and review previously generated clinical notes.</p>
        </div>
        <button
          onClick={() => navigate('/new-note')}
          className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold text-white transition-all hover:-translate-y-0.5"
          style={{ background: 'linear-gradient(135deg, #1a5d3a 0%, #2d8a5e 100%)', boxShadow: '0 4px 12px rgba(26,93,58,0.25)' }}
        >
          <FileText size={15} />
          New Note
        </button>
      </div>

      {/* Search */}
      <div className="relative mb-6">
        <Search size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400" />
        <input
          type="text"
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search by patient or note type…"
          className="w-full pl-11 pr-4 py-3 bg-white border border-gray-200 rounded-xl text-sm focus:outline-none focus:border-[#1a5d3a] transition-colors"
        />
      </div>

      {/* Table */}
      <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
        <div className="grid grid-cols-12 gap-4 px-6 py-3 border-b border-gray-50 text-xs font-semibold text-gray-400 uppercase tracking-wider">
          <div className="col-span-4">Patient</div>
          <div className="col-span-3">Type</div>
          <div className="col-span-2">Date</div>
          <div className="col-span-2">Time</div>
          <div className="col-span-1">Action</div>
        </div>

        {filtered.length === 0 ? (
          <div className="px-6 py-12 text-center text-sm text-gray-400">No notes found.</div>
        ) : (
          filtered.map((note, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.04 }}
              className={`grid grid-cols-12 gap-4 px-6 py-4 items-center hover:bg-gray-50 transition-colors ${i !== filtered.length - 1 ? 'border-b border-gray-50' : ''}`}
            >
              <div className="col-span-4 flex items-center gap-3">
                <div
                  className="w-8 h-8 rounded-full flex items-center justify-center text-white text-xs font-semibold shrink-0"
                  style={{ background: 'linear-gradient(135deg, #1a5d3a 0%, #2d8a5e 100%)' }}
                >
                  {note.initials}
                </div>
                <span className="text-sm font-medium text-gray-800 truncate">{note.patient}</span>
              </div>
              <div className="col-span-3 text-sm text-gray-500">{note.type}</div>
              <div className="col-span-2 text-sm text-gray-500">{note.date}</div>
              <div className="col-span-2 text-sm text-gray-500">{note.time}</div>
              <div className="col-span-1">
                <button
                  className="p-1.5 rounded-lg hover:bg-gray-100 transition-colors text-gray-400 hover:text-[#1a5d3a]"
                  title="View note"
                >
                  <Eye size={15} />
                </button>
              </div>
            </motion.div>
          ))
        )}
      </div>
    </motion.div>
  );
}
