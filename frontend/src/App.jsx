import React from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import Layout from "./components/Layout.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import UploadDataset from "./pages/UploadDataset.jsx";
import DatasetExplorer from "./pages/DatasetExplorer.jsx";
import AIAnalyst from "./pages/AIAnalyst.jsx";
import ChartsPage from "./pages/ChartsPage.jsx";
import InsightsPage from "./pages/InsightsPage.jsx";
import HistoryPage from "./pages/HistoryPage.jsx";
import SettingsPage from "./pages/SettingsPage.jsx";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/upload" element={<UploadDataset />} />
        <Route path="/explorer" element={<DatasetExplorer />} />
        <Route path="/analyst" element={<AIAnalyst />} />
        <Route path="/charts" element={<ChartsPage />} />
        <Route path="/insights" element={<InsightsPage />} />
        <Route path="/history" element={<HistoryPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
