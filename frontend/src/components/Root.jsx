import { Outlet, Link, useLocation } from "react-router";
import { motion } from "motion/react";

export function Root() {
  const location = useLocation();

  const navItems = [
    { path: "/", label: "Overview" },
    { path: "/new-note", label: "New Note" },
    { path: "/patients", label: "Patients" },
    { path: "/history", label: "History" },
  ];

  return (
    <div className="flex h-screen bg-white">
      {/* Minimal Top Bar */}
      <div className="fixed top-0 left-0 right-0 h-16 bg-white border-b border-slate-200 z-50">
        <div className="h-full max-w-[1600px] mx-auto px-12 flex items-center justify-between">
          {/* Logo + Nav */}
          <div className="flex items-center gap-12">
            <Link to="/" className="flex items-center gap-3">
              <div className="w-7 h-7 bg-slate-900" />
              <span className="text-sm font-medium tracking-wide uppercase text-slate-900">MedScribe</span>
            </Link>

            <nav className="flex items-center gap-1">
              {navItems.map((item) => {
                const isActive = location.pathname === item.path;
                return (
                  <Link key={item.path} to={item.path} className="relative px-4 py-2">
                    <span className={`text-sm transition-colors ${isActive ? 'text-slate-900' : 'text-slate-500 hover:text-slate-900'}`}>
                      {item.label}
                    </span>
                    {isActive && (
                      <motion.div
                        layoutId="activeIndicator"
                        className="absolute bottom-0 left-0 right-0 h-px bg-slate-900"
                        transition={{ type: "spring", stiffness: 380, damping: 30 }}
                      />
                    )}
                  </Link>
                );
              })}
            </nav>
          </div>

          {/* User */}
          <div className="flex items-center gap-4">
            <div className="text-right">
              <p className="text-sm font-medium text-slate-900">Dr. Sarah Johnson</p>
              <p className="text-xs text-slate-500">Internal Medicine</p>
            </div>
            <div className="w-9 h-9 bg-slate-900 text-white flex items-center justify-center">
              <span className="text-xs font-medium">SJ</span>
            </div>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <main className="flex-1 mt-16 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
