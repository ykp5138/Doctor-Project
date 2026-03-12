import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Mic, FileText, Clock, Calendar, ChevronRight, Plus } from 'lucide-react';

const stats = [
  { label: 'Notes Today', value: '3', icon: FileText, color: '#1a5d3a' },
  { label: 'Avg Time Saved', value: '~18 min', icon: Clock, color: '#2d8a5e' },
  { label: 'This Week', value: '12', icon: Calendar, color: '#1a5d3a' },
];

const recentNotes = [
  { patient: 'John Smith', type: 'SOAP Note', time: '10:32 AM', status: 'Complete', initials: 'JS' },
  { patient: 'Emily Davis', type: 'Progress Note', time: '9:15 AM', status: 'Complete', initials: 'ED' },
  { patient: 'Robert Chen', type: 'Consultation', time: 'Yesterday', status: 'Complete', initials: 'RC' },
  { patient: 'Maria Lopez', type: 'SOAP Note', time: 'Yesterday', status: 'Complete', initials: 'ML' },
];

const container = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { staggerChildren: 0.07 } },
};
const item = {
  hidden: { opacity: 0, y: 16 },
  show: { opacity: 1, y: 0, transition: { duration: 0.35 } },
};

export default function Dashboard() {
  const navigate = useNavigate();
  const hour = new Date().getHours();
  const greeting = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening';

  return (
    <motion.div
      className="max-w-5xl mx-auto px-6 py-10"
      variants={container}
      initial="hidden"
      animate="show"
    >
      {/* Header */}
      <motion.div variants={item} className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">
          {greeting}, Dr. Johnson
        </h1>
        <p className="text-gray-500 mt-1 text-sm">
          Here's an overview of your clinical documentation activity.
        </p>
      </motion.div>

      {/* Stats */}
      <motion.div variants={item} className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8">
        {stats.map((stat) => {
          const Icon = stat.icon;
          return (
            <div
              key={stat.label}
              className="bg-white rounded-2xl border border-gray-100 px-6 py-5 flex items-center gap-4 shadow-sm"
            >
              <div
                className="w-11 h-11 rounded-xl flex items-center justify-center text-white shrink-0"
                style={{ background: `${stat.color}18` }}
              >
                <Icon size={20} style={{ color: stat.color }} />
              </div>
              <div>
                <p className="text-2xl font-bold text-gray-900">{stat.value}</p>
                <p className="text-xs text-gray-500 mt-0.5">{stat.label}</p>
              </div>
            </div>
          );
        })}
      </motion.div>

      {/* Quick actions */}
      <motion.div variants={item} className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-8">
        <button
          onClick={() => navigate('/new-note')}
          className="flex items-center gap-4 bg-white rounded-2xl border border-gray-100 px-6 py-5 shadow-sm hover:shadow-md hover:border-[#1a5d3a]/20 transition-all text-left group"
        >
          <div
            className="w-12 h-12 rounded-xl flex items-center justify-center text-white shrink-0 transition-transform group-hover:scale-105"
            style={{ background: 'linear-gradient(135deg, #1a5d3a 0%, #2d8a5e 100%)' }}
          >
            <Mic size={22} />
          </div>
          <div className="flex-1">
            <p className="font-semibold text-gray-900">New Recording</p>
            <p className="text-xs text-gray-500 mt-0.5">Upload or record a patient visit</p>
          </div>
          <ChevronRight size={18} className="text-gray-400 group-hover:text-[#1a5d3a] transition-colors" />
        </button>

        <button
          onClick={() => navigate('/new-note')}
          className="flex items-center gap-4 bg-white rounded-2xl border border-gray-100 px-6 py-5 shadow-sm hover:shadow-md hover:border-[#1a5d3a]/20 transition-all text-left group"
        >
          <div
            className="w-12 h-12 rounded-xl flex items-center justify-center shrink-0 transition-transform group-hover:scale-105"
            style={{ background: '#1a5d3a18' }}
          >
            <Plus size={22} style={{ color: '#1a5d3a' }} />
          </div>
          <div className="flex-1">
            <p className="font-semibold text-gray-900">Manual Entry</p>
            <p className="text-xs text-gray-500 mt-0.5">Type or paste transcript text</p>
          </div>
          <ChevronRight size={18} className="text-gray-400 group-hover:text-[#1a5d3a] transition-colors" />
        </button>
      </motion.div>

      {/* Recent notes */}
      <motion.div variants={item}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-base font-semibold text-gray-900">Recent Notes</h2>
          <button
            onClick={() => navigate('/history')}
            className="text-xs font-medium text-[#1a5d3a] hover:underline"
          >
            View all
          </button>
        </div>

        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
          {recentNotes.map((note, i) => (
            <div
              key={i}
              className={`flex items-center gap-4 px-6 py-4 hover:bg-gray-50 transition-colors cursor-pointer ${i !== recentNotes.length - 1 ? 'border-b border-gray-50' : ''}`}
            >
              <div
                className="w-9 h-9 rounded-full flex items-center justify-center text-white text-xs font-semibold shrink-0"
                style={{ background: 'linear-gradient(135deg, #1a5d3a 0%, #2d8a5e 100%)' }}
              >
                {note.initials}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-900 truncate">{note.patient}</p>
                <p className="text-xs text-gray-500">{note.type}</p>
              </div>
              <div className="text-right shrink-0">
                <p className="text-xs text-gray-400">{note.time}</p>
                <span className="inline-block mt-1 text-[11px] font-medium px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700">
                  {note.status}
                </span>
              </div>
            </div>
          ))}
        </div>
      </motion.div>
    </motion.div>
  );
}
