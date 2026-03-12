import { useState } from 'react';
import { motion } from 'framer-motion';
import { Search, UserPlus } from 'lucide-react';

const samplePatients = [
  { name: 'John Smith', mrn: 'MRN-001234', dob: '1974-03-15', lastVisit: 'Mar 12, 2026', notes: 8, status: 'Active', initials: 'JS' },
  { name: 'Emily Davis', mrn: 'MRN-002187', dob: '1989-07-22', lastVisit: 'Mar 12, 2026', notes: 5, status: 'Active', initials: 'ED' },
  { name: 'Robert Chen', mrn: 'MRN-003045', dob: '1965-11-04', lastVisit: 'Mar 11, 2026', notes: 12, status: 'Active', initials: 'RC' },
  { name: 'Maria Lopez', mrn: 'MRN-004321', dob: '1992-01-30', lastVisit: 'Mar 11, 2026', notes: 3, status: 'Active', initials: 'ML' },
  { name: 'David Park', mrn: 'MRN-005678', dob: '1958-09-18', lastVisit: 'Mar 10, 2026', notes: 6, status: 'Active', initials: 'DP' },
  { name: 'Sarah White', mrn: 'MRN-006543', dob: '1981-05-25', lastVisit: 'Mar 10, 2026', notes: 4, status: 'Inactive', initials: 'SW' },
  { name: 'James Wilson', mrn: 'MRN-007890', dob: '1970-12-08', lastVisit: 'Mar 9, 2026', notes: 9, status: 'Active', initials: 'JW' },
  { name: 'Linda Brown', mrn: 'MRN-008765', dob: '1995-06-14', lastVisit: 'Mar 9, 2026', notes: 2, status: 'Active', initials: 'LB' },
];

export default function PatientList() {
  const [search, setSearch] = useState('');

  const filtered = samplePatients.filter(p =>
    p.name.toLowerCase().includes(search.toLowerCase()) ||
    p.mrn.toLowerCase().includes(search.toLowerCase())
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
          <h1 className="text-2xl font-bold text-gray-900">Patients</h1>
          <p className="text-sm text-gray-500 mt-1">Manage and search your patient directory.</p>
        </div>
        <button
          className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold text-white transition-all hover:-translate-y-0.5"
          style={{ background: 'linear-gradient(135deg, #1a5d3a 0%, #2d8a5e 100%)', boxShadow: '0 4px 12px rgba(26,93,58,0.25)' }}
        >
          <UserPlus size={15} />
          Add Patient
        </button>
      </div>

      {/* Search */}
      <div className="relative mb-6">
        <Search size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400" />
        <input
          type="text"
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search by name or MRN…"
          className="w-full pl-11 pr-4 py-3 bg-white border border-gray-200 rounded-xl text-sm focus:outline-none focus:border-[#1a5d3a] transition-colors"
        />
      </div>

      {/* Table */}
      <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
        <div className="grid grid-cols-12 gap-4 px-6 py-3 border-b border-gray-50 text-xs font-semibold text-gray-400 uppercase tracking-wider">
          <div className="col-span-3">Patient</div>
          <div className="col-span-2">MRN</div>
          <div className="col-span-2">Date of Birth</div>
          <div className="col-span-2">Last Visit</div>
          <div className="col-span-1 text-center">Notes</div>
          <div className="col-span-2">Status</div>
        </div>

        {filtered.length === 0 ? (
          <div className="px-6 py-12 text-center text-sm text-gray-400">No patients found.</div>
        ) : (
          filtered.map((patient, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.04 }}
              className={`grid grid-cols-12 gap-4 px-6 py-4 items-center hover:bg-gray-50 transition-colors cursor-pointer ${i !== filtered.length - 1 ? 'border-b border-gray-50' : ''}`}
            >
              <div className="col-span-3 flex items-center gap-3">
                <div
                  className="w-8 h-8 rounded-full flex items-center justify-center text-white text-xs font-semibold shrink-0"
                  style={{ background: 'linear-gradient(135deg, #1a5d3a 0%, #2d8a5e 100%)' }}
                >
                  {patient.initials}
                </div>
                <span className="text-sm font-medium text-gray-800 truncate">{patient.name}</span>
              </div>
              <div className="col-span-2 text-sm text-gray-500 font-mono">{patient.mrn}</div>
              <div className="col-span-2 text-sm text-gray-500">{patient.dob}</div>
              <div className="col-span-2 text-sm text-gray-500">{patient.lastVisit}</div>
              <div className="col-span-1 text-center text-sm font-medium text-gray-700">{patient.notes}</div>
              <div className="col-span-2">
                <span
                  className="text-[11px] font-medium px-2.5 py-1 rounded-full"
                  style={patient.status === 'Active'
                    ? { background: '#f0fdf4', color: '#16a34a' }
                    : { background: '#f9fafb', color: '#9ca3af' }
                  }
                >
                  {patient.status}
                </span>
              </div>
            </motion.div>
          ))
        )}
      </div>
    </motion.div>
  );
}
