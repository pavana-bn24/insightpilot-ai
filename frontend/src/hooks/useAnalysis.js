import { useState } from "react";

import { api } from "../services/api.js";

/**
 * Runs a question through the InsightPilot agent pipeline.
 * Handles both "answer" responses and "clarification" responses (when the
 * planner needs the user to resolve column ambiguity).
 */
export function useAnalysis() {
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [clarification, setClarification] = useState(null);

  const analyze = async (dataset_id, question, hints) => {
    setLoading(true);
    setError(null);
    setClarification(null);
    try {
      const data = await api.analyze(dataset_id, question, hints);
      if (data.kind === "clarification") {
        setClarification(data.clarification);
        return null;
      }
      setResult(data.result);
      return data.result;
    } catch (e) {
      setError(e.message);
      return null;
    } finally {
      setLoading(false);
    }
  };

  const clear = () => {
    setResult(null);
    setError(null);
    setClarification(null);
  };

  return { result, loading, error, clarification, analyze, clear };
}
