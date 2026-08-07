import React from "react";
import { NavLink, Outlet } from "react-router-dom";
import { motion } from "framer-motion";

import { useApp } from "../context/AppContext.jsx";

const NAV = [
  { to: "/", label: "Dashboard", icon: "▦" },
  { to: "/upload", label: "Upload Dataset", icon: "⇪" },
  { to: "/explorer", label: "Dataset Explorer", icon: "☷" },
  { to: "/analyst", label: "AI Analyst", icon: "◇" },
  { to: "/charts", label: "Charts", icon: "📈" },
  { to: "/insights", label: "Insights", icon: "💡" },
  { to: "/history", label: "History", icon: "↺" },
  { to: "/settings", label: "Settings", icon: "⚙" },
];

export default function Layout() {
  const { health, activeDatasetId, theme, toggleTheme } = useApp();

  return (
    <>
      <div className="bg-scene" />
      <div className="flex min-h-screen">
        <aside className="fixed inset-y-0 left-0 z-20 flex w-60 flex-col border-r border-slate-200 bg-white/80 px-4 py-5 backdrop-blur-xl dark:border-slate-800 dark:bg-slate-950/80">
          <div className="mb-8 flex items-center gap-3 px-1">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-600 text-xl shadow-glow">
              🧠
            </div>
            <div>
              <div className="text-sm font-extrabold tracking-tight text-slate-900 dark:text-white">
                InsightPilot AI
              </div>
              <div className="text-[11px] font-medium text-brand-500 dark:text-brand-400">
                Autonomous BI Agent
              </div>
            </div>
          </div>

          <nav className="flex flex-1 flex-col gap-1">
            {NAV.map((n) => (
              <NavLink key={n.to} to={n.to} end={n.to === "/"}>
                {({ isActive }) => (
                  <motion.div
                    whileHover={{ x: 3 }}
                    className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold transition-colors ${
                      isActive
                        ? "bg-brand-600 text-white shadow-glow"
                        : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800/60"
                    }`}
                  >
                    <span className="text-base leading-none">{n.icon}</span>
                    {n.label}
                  </motion.div>
                )}
              </NavLink>
            ))}
          </nav>

          <div className="mt-6 space-y-2">
            <button
              onClick={toggleTheme}
              className="btn btn-ghost w-full justify-between"
            >
              <span>{theme === "dark" ? "🌙 Dark mode" : "☀️ Light mode"}</span>
              <span className="text-xs opacity-60">{theme === "dark" ? "on" : "on"}</span>
            </button>
            <div className="flex items-center justify-center gap-2 rounded-xl border border-slate-200 px-3 py-2 dark:border-slate-800">
              <span
                className="h-2 w-2 rounded-full"
                style={{ background: health?.status === "ok" ? "#10b981" : "#f43f5e" }}
              />
              <span className="text-xs font-semibold text-slate-500 dark:text-slate-400">
                Backend {health?.status === "ok" ? "online" : "offline"}
              </span>
              <span className="text-xs text-slate-400 dark:text-slate-500">
                · {health?.llm_mode || "deterministic"}
              </span>
            </div>
            <div className="px-1 text-[11px] text-slate-400 dark:text-slate-500">
              {activeDatasetId ? `Active: ${activeDatasetId.slice(0, 18)}` : "No dataset loaded"}
            </div>
            <div className="px-1 text-[11px] font-medium text-brand-500/70 dark:text-brand-400/60">
              Think · Plan · Act · Verify · Explain
            </div>
          </div>
        </aside>

        <main className="ml-60 flex-1 px-6 py-6">
          <Outlet />
        </main>
      </div>
    </>
  );
}
