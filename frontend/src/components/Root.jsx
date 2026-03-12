import { Outlet, NavLink } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Stethoscope } from 'lucide-react';

const navLinks = [
  { to: '/', label: 'Overview', end: true },
  { to: '/new-note', label: 'New Note' },
  { to: '/patients', label: 'Patients' },
  { to: '/history', label: 'History' },
];

export default function Root() {
  return (
    <div className="min-h-screen bg-[#f8faf9]">
      {/* Fixed Header */}
      <header className="fixed top-0 left-0 right-0 h-16 bg-white border-b border-gray-100 z-50 flex items-center px-6">
        {/* Logo */}
        <div className="flex items-center gap-3 mr-10 shrink-0">
          <div
            className="w-9 h-9 rounded-xl flex items-center justify-center text-white shadow-md"
            style={{ background: 'linear-gradient(135deg, #1a5d3a 0%, #2d8a5e 100%)' }}
          >
            <Stethoscope size={18} />
          </div>
          <span className="text-[17px] font-bold tracking-tight text-gray-900">MedScribe</span>
        </div>

        {/* Navigation */}
        <nav className="flex items-stretch flex-1 h-full">
          {navLinks.map(link => (
            <NavLink
              key={link.to}
              to={link.to}
              end={link.end ?? false}
              className="relative flex items-center px-4 h-full"
            >
              {({ isActive }) => (
                <>
                  <span
                    className="text-sm font-medium transition-colors duration-150"
                    style={{ color: isActive ? '#1a5d3a' : '#6b7280' }}
                  >
                    {link.label}
                  </span>
                  {isActive && (
                    <motion.div
                      layoutId="nav-underline"
                      className="absolute bottom-0 left-3 right-3 h-[2px] rounded-full"
                      style={{ background: '#1a5d3a' }}
                      transition={{ type: 'spring', stiffness: 380, damping: 30 }}
                    />
                  )}
                </>
              )}
            </NavLink>
          ))}
        </nav>

        {/* User */}
        <div className="flex items-center gap-3 shrink-0">
          <div
            className="w-9 h-9 rounded-full flex items-center justify-center text-white text-sm font-semibold"
            style={{ background: 'linear-gradient(135deg, #1a5d3a 0%, #2d8a5e 100%)' }}
          >
            SJ
          </div>
          <span className="text-sm text-gray-500 hidden md:block">Dr. Sarah Johnson</span>
        </div>
      </header>

      {/* Page content */}
      <main className="pt-16 min-h-screen">
        <AnimatePresence mode="wait">
          <Outlet />
        </AnimatePresence>
      </main>
    </div>
  );
}
