import React from "react";
import { motion } from "framer-motion";

export function ConfidenceRing({ value }) {
  const pct = Math.round(value * 100);
  const r = 26;
  const circ = 2 * Math.PI * r;
  const offset = circ - (pct / 100) * circ;
  const color =
    pct >= 90
      ? "var(--tw-ring-color, #10b981)"
      : pct >= 70
        ? "#f59e0b"
        : "#f43f5e";

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.4 }}
      className="flex items-center gap-4 rounded-2xl border border-slate-200 p-4 dark:border-slate-800"
    >
      <div className="relative h-16 w-16">
        <svg width="64" height="64" viewBox="0 0 64 64" className="absolute inset-0">
          <circle cx="32" cy="32" r={r} fill="none" stroke="currentColor" strokeWidth="6" className="text-slate-200 dark:text-slate-700" />
          <circle
            cx="32"
            cy="32"
            r={r}
            fill="none"
            stroke={color}
            strokeWidth="6"
            strokeLinecap="round"
            strokeDasharray={circ}
            strokeDashoffset={offset}
            transform="rotate(-90 32 32)"
            style={{ transition: "stroke-dashoffset 0.8s ease" }}
          />
        </svg>
        <span className="absolute inset-0 flex items-center justify-center text-sm font-extrabold" style={{ color }}>
          {pct}%
        </span>
      </div>
      <div className="hidden sm:block">
        <div className="text-sm font-bold text-slate-700 dark:text-slate-300">Confidence</div>
        <div className="mt-0.5 text-xs text-slate-400 dark:text-slate-500">
          how sure the agent is of this answer
        </div>
      </div>
    </motion.div>
  );
}
