import React from "react";
import { motion } from "framer-motion";

export function StatCard({ label, value, hint, tone }) {
  const toneColor =
    tone === "success"
      ? "text-emerald-500 dark:text-emerald-400"
      : tone === "warning"
        ? "text-amber-500 dark:text-amber-400"
        : tone === "danger"
          ? "text-rose-500 dark:text-rose-400"
          : "text-slate-900 dark:text-white";

  return (
    <motion.div
      whileHover={{ y: -2 }}
      className="glass card-pad"
    >
      <div className="text-[11px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
        {label}
      </div>
      <div className={`mt-1 text-xl font-extrabold tracking-tight ${toneColor}`}>{value}</div>
      {hint && (
        <div className="mt-1 truncate text-xs text-slate-400 dark:text-slate-500">{hint}</div>
      )}
    </motion.div>
  );
}
