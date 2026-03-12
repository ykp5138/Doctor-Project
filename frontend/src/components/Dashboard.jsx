import { Link } from "react-router";
import { ArrowRight, Circle } from "lucide-react";
import { motion } from "motion/react";

export function Dashboard() {
  const stats = [
    { label: "Notes Today", value: "12", change: "+3" },
    { label: "Time Saved", value: "18m", change: "avg" },
    { label: "This Week", value: "47", change: "total" },
  ];

  const recentNotes = [
    { patient: "John Smith", type: "SOAP", time: "9:30 AM", date: "Mar 12" },
    { patient: "Emily Davis", type: "Progress", time: "8:15 AM", date: "Mar 12" },
    { patient: "Michael Brown", type: "Consultation", time: "4:45 PM", date: "Mar 11" },
    { patient: "Sarah Wilson", type: "SOAP", time: "2:30 PM", date: "Mar 10" },
    { patient: "David Martinez", type: "Progress", time: "11:00 AM", date: "Mar 9" },
  ];

  return (
    <div className="min-h-screen">
      {/* Hero Section */}
      <motion.section
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.8, ease: [0.19, 1.0, 0.22, 1.0] }}
        className="border-b border-slate-200"
      >
        <div className="max-w-[1600px] mx-auto px-12 py-24">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.1, ease: [0.19, 1.0, 0.22, 1.0] }}
          >
            <p className="text-xs uppercase tracking-widest text-slate-500 mb-4">Thursday, March 12, 2026</p>
            <h1 className="text-6xl font-light text-slate-900 mb-6 tracking-tight leading-none">
              Good morning,<br />Dr. Johnson
            </h1>
            <p className="text-lg text-slate-600 max-w-xl leading-relaxed">
              Your clinical documentation workspace is ready.
            </p>
          </motion.div>
        </div>
      </motion.section>

      <div className="max-w-[1600px] mx-auto px-12 py-16">
        {/* Stats */}
        <motion.section
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.3, ease: [0.19, 1.0, 0.22, 1.0] }}
          className="grid grid-cols-3 gap-16 mb-24"
        >
          {stats.map((stat, index) => (
            <motion.div
              key={stat.label}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.8, delay: 0.4 + index * 0.1, ease: [0.19, 1.0, 0.22, 1.0] }}
              className="border-l border-slate-200 pl-6"
            >
              <p className="text-xs uppercase tracking-widest text-slate-500 mb-3">{stat.label}</p>
              <div className="flex items-baseline gap-3">
                <span className="text-5xl font-light text-slate-900 tracking-tight">{stat.value}</span>
                <span className="text-sm text-slate-400">{stat.change}</span>
              </div>
            </motion.div>
          ))}
        </motion.section>

        {/* Actions */}
        <motion.section
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.6, ease: [0.19, 1.0, 0.22, 1.0] }}
          className="mb-24"
        >
          <h2 className="text-xs uppercase tracking-widest text-slate-500 mb-8">Quick Actions</h2>
          <div className="grid grid-cols-2 gap-px bg-slate-200">
            <Link to="/new-note" className="group bg-white hover:bg-slate-50 transition-colors">
              <div className="p-12">
                <div className="flex items-start justify-between mb-8">
                  <div>
                    <h3 className="text-2xl font-light text-slate-900 mb-2">Start Recording</h3>
                    <p className="text-sm text-slate-600">Voice-powered documentation</p>
                  </div>
                  <Circle className="w-3 h-3 text-slate-900 fill-slate-900" />
                </div>
                <div className="flex items-center text-sm text-slate-900 opacity-0 group-hover:opacity-100 transition-opacity">
                  Begin <ArrowRight className="ml-2 w-4 h-4" />
                </div>
              </div>
            </Link>
            <Link to="/new-note" className="group bg-white hover:bg-slate-50 transition-colors">
              <div className="p-12">
                <div className="flex items-start justify-between mb-8">
                  <div>
                    <h3 className="text-2xl font-light text-slate-900 mb-2">Manual Entry</h3>
                    <p className="text-sm text-slate-600">Type your documentation</p>
                  </div>
                  <Circle className="w-3 h-3 text-slate-400" />
                </div>
                <div className="flex items-center text-sm text-slate-900 opacity-0 group-hover:opacity-100 transition-opacity">
                  Create <ArrowRight className="ml-2 w-4 h-4" />
                </div>
              </div>
            </Link>
          </div>
        </motion.section>

        {/* Recent Notes */}
        <motion.section
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.8, ease: [0.19, 1.0, 0.22, 1.0] }}
        >
          <div className="flex items-center justify-between mb-8">
            <h2 className="text-xs uppercase tracking-widest text-slate-500">Recent Notes</h2>
            <Link to="/history" className="text-xs uppercase tracking-widest text-slate-900 hover:text-slate-600 transition-colors">
              View All
            </Link>
          </div>

          <div className="space-y-px bg-slate-200">
            {recentNotes.map((note, index) => (
              <motion.div
                key={index}
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.6, delay: 0.9 + index * 0.05, ease: [0.19, 1.0, 0.22, 1.0] }}
                className="bg-white hover:bg-slate-50 transition-colors cursor-pointer group"
              >
                <div className="px-8 py-6 flex items-center justify-between">
                  <div className="flex items-center gap-12 flex-1">
                    <span className="text-sm font-medium text-slate-900 w-48">{note.patient}</span>
                    <span className="text-sm text-slate-500 w-32">{note.type}</span>
                    <span className="text-xs text-slate-400 uppercase tracking-wider">{note.date}</span>
                  </div>
                  <div className="flex items-center gap-8">
                    <span className="text-xs font-mono text-slate-500">{note.time}</span>
                    <ArrowRight className="w-4 h-4 text-slate-400 opacity-0 group-hover:opacity-100 transition-opacity" />
                  </div>
                </div>
              </motion.div>
            ))}
          </div>
        </motion.section>
      </div>
    </div>
  );
}
