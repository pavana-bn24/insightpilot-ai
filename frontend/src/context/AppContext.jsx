import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { api } from "../services/api.js";

const AppContext = createContext(null);

export function AppProvider({ children }) {
  const [datasets, setDatasets] = useState([]);
  const [activeDatasetId, setActiveDatasetId] = useState(() => {
    return localStorage.getItem("insightpilot.active_dataset") || "";
  });
  const [activeProfile, setActiveProfile] = useState(null);
  const [history, setHistory] = useState([]);
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [theme, setTheme] = useState(() => {
    return localStorage.getItem("insightpilot.theme") || "light";
  });
  const [suggestions, setSuggestions] = useState([]);

  const toggleTheme = useCallback(() => {
    setTheme((t) => {
      const next = t === "dark" ? "light" : "dark";
      localStorage.setItem("insightpilot.theme", next);
      document.documentElement.classList.toggle("dark", next === "dark");
      return next;
    });
  }, []);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
  }, [theme]);

  const loadSuggestions = useCallback(
    async (id) => {
      if (!id) {
        setSuggestions([]);
        return;
      }
      try {
        const data = await api.suggestions(id);
        setSuggestions(data.questions || []);
      } catch (e) {
        console.error("Failed to load suggestions", e);
      }
    },
    []
  );

  const refreshDatasets = useCallback(async () => {
    try {
      const list = await api.listDatasets();
      setDatasets(list);
    } catch (e) {
      console.error("Failed to list datasets", e);
    }
  }, []);

  const refreshHistory = useCallback(async () => {
    try {
      const h = await api.history();
      setHistory(h);
    } catch (e) {
      console.error("Failed to load history", e);
    }
  }, []);

  const loadActiveProfile = useCallback(async (id) => {
    if (!id) {
      setActiveProfile(null);
      return;
    }
    try {
      const data = await api.getDataset(id);
      setActiveProfile(data.profile);
      localStorage.setItem("insightpilot.active_dataset", id);
    } catch (e) {
      console.error("Failed to load profile", e);
      setError(e.message);
    }
  }, []);

  // On mount: load health, datasets, history, active profile.
  useEffect(() => {
    (async () => {
      try {
        const h = await api.health();
        setHealth(h);
      } catch (e) {
        setError("Cannot reach the InsightPilot backend. Start it with: uvicorn backend.main:app --reload");
      }
      await refreshDatasets();
      await refreshHistory();
    })();
  }, [refreshDatasets, refreshHistory]);

  useEffect(() => {
    loadActiveProfile(activeDatasetId);
    loadSuggestions(activeDatasetId);
  }, [activeDatasetId, loadActiveProfile, loadSuggestions]);

  const selectDataset = useCallback(
    (id) => {
      setActiveDatasetId(id);
      loadActiveProfile(id);
      loadSuggestions(id);
    },
    [loadActiveProfile, loadSuggestions]
  );

  const value = useMemo(
    () => ({
      datasets,
      activeDatasetId,
      activeProfile,
      history,
      health,
      loading,
      error,
      theme,
      toggleTheme,
      suggestions,
      setError,
      setLoading,
      refreshDatasets,
      refreshHistory,
      selectDataset,
      setActiveDatasetId,
    }),
    [
      datasets,
      activeDatasetId,
      activeProfile,
      history,
      health,
      loading,
      error,
      theme,
      toggleTheme,
      suggestions,
      refreshDatasets,
      refreshHistory,
      selectDataset,
    ]
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp must be used within AppProvider");
  return ctx;
}
