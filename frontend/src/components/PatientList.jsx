import { useState } from "react";
import { Input } from "./ui/input";
import { Search } from "lucide-react";
import { motion } from "motion/react";

export function PatientList() {
  const [searchQuery, setSearchQuery] = useState("");

  const patients = [
    { name: "John Smith", mrn: "001234", dob: "05/14/1965", lastVisit: "Mar 12, 2026", notes: 8, status: "Active" },
    { name: "Emily Davis", mrn: "001235", dob: "11/22/1978", lastVisit: "Mar 12, 2026", notes: 5, status: "Active" },
    { name: "Michael Brown", mrn: "001236", dob: "08/30/1952", lastVisit: "Mar 11, 2026", notes: 12, status: "Active" },
    { name: "Sarah Wilson", mrn: "001237", dob: "03/17/1990", lastVisit: "Mar 10, 2026", notes: 3, status: "Active" },
    { name: "David Martinez", mrn: "001238", dob: "12/05/1968", lastVisit: "Mar 9, 2026", notes: 15, status: "Monitoring" },
    { name: "Jennifer Lee", mrn: "001239", dob: "07/28/1985", lastVisit: "Mar 8, 2026", notes: 6, status: "Active" },
    { name: "Robert Taylor", mrn: "001240", dob: "06/15/1960", lastVisit: "Mar 7, 2026", notes: 10, status: "Active" },
    { name: "Lisa Anderson", mrn: "001241", dob: "09/03/1975", lastVisit: "Mar 6, 2026", notes: 4, status: "Active" },
  ];

  const filteredPatients = patients.filter(
    (patient) =>
      patient.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      patient.mrn.includes(searchQuery)
  );

  return (
    <div className="min-h-screen">
      <motion.section
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.8, ease: [0.19, 1.0, 0.22, 1.0] }}
        className="border-b border-slate-200"
      >
        <div className="max-w-[1600px] mx-auto px-12 py-16">
          <p className="text-xs uppercase tracking-widest text-slate-500 mb-4">Directory</p>
          <h1 className="text-5xl font-light text-slate-900 tracking-tight">Patients</h1>
        </div>
      </motion.section>

      <div className="max-w-[1600px] mx-auto px-12 py-16">
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
              placeholder="Search by name or MRN"
              className="pl-8 border-0 border-b border-slate-200 rounded-none focus:border-slate-900 focus:ring-0 text-lg bg-transparent"
            />
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.3, ease: [0.19, 1.0, 0.22, 1.0] }}
          className="grid grid-cols-12 gap-4 px-8 py-4 border-b border-slate-200"
        >
          <div className="col-span-3"><span className="text-xs uppercase tracking-widest text-slate-500">Name</span></div>
          <div className="col-span-2"><span className="text-xs uppercase tracking-widest text-slate-500">MRN</span></div>
          <div className="col-span-2"><span className="text-xs uppercase tracking-widest text-slate-500">Date of Birth</span></div>
          <div className="col-span-2"><span className="text-xs uppercase tracking-widest text-slate-500">Last Visit</span></div>
          <div className="col-span-1"><span className="text-xs uppercase tracking-widest text-slate-500">Notes</span></div>
          <div className="col-span-2"><span className="text-xs uppercase tracking-widest text-slate-500">Status</span></div>
        </motion.div>

        <div>
          {filteredPatients.map((patient, index) => (
            <motion.div
              key={patient.mrn}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, delay: 0.4 + index * 0.03, ease: [0.19, 1.0, 0.22, 1.0] }}
              className="grid grid-cols-12 gap-4 px-8 py-6 border-b border-slate-100 hover:bg-slate-50 transition-colors cursor-pointer"
            >
              <div className="col-span-3"><span className="text-sm font-medium text-slate-900">{patient.name}</span></div>
              <div className="col-span-2"><span className="text-sm font-mono text-slate-500">{patient.mrn}</span></div>
              <div className="col-span-2"><span className="text-sm text-slate-600">{patient.dob}</span></div>
              <div className="col-span-2"><span className="text-sm text-slate-600">{patient.lastVisit}</span></div>
              <div className="col-span-1"><span className="text-sm text-slate-600">{patient.notes}</span></div>
              <div className="col-span-2"><span className="text-xs uppercase tracking-wider text-slate-400">{patient.status}</span></div>
            </motion.div>
          ))}
        </div>

        {filteredPatients.length === 0 && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="text-center py-24">
            <p className="text-sm text-slate-400">No patients found</p>
          </motion.div>
        )}
      </div>
    </div>
  );
}
