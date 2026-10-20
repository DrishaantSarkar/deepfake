import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  ReactNode,
} from "react";
import { AnalysisStats } from "../types/api";
import { api } from "../services/api";

export type ViewType = "dashboard" | "new" | "history" | "detail" | "system";

interface WorkspaceContextType {
  currentView: ViewType;
  setCurrentView: (view: ViewType) => void;
  selectedAnalysisId: string | null;
  openAnalysis: (analysisId: string) => void;
  stats: AnalysisStats | null;
  statsLoading: boolean;
  refreshStats: () => Promise<void>;
  toastMessage: string | null;
  showToast: (message: string) => void;
}

const WorkspaceContext = createContext<WorkspaceContextType | undefined>(undefined);

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [currentView, setCurrentView] = useState<ViewType>("dashboard");
  const [selectedAnalysisId, setSelectedAnalysisId] = useState<string | null>(null);
  const [stats, setStats] = useState<AnalysisStats | null>(null);
  const [statsLoading, setStatsLoading] = useState(false);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const showToast = useCallback((message: string) => {
    setToastMessage(message);
    setTimeout(() => {
      setToastMessage((prev) => (prev === message ? null : prev));
    }, 3500);
  }, []);

  const refreshStats = useCallback(async () => {
    try {
      setStatsLoading(true);
      const data = await api.getStats();
      setStats(data);
    } catch {
      // stats error handled by component views
    } finally {
      setStatsLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshStats();
  }, [refreshStats]);

  const openAnalysis = useCallback((analysisId: string) => {
    setSelectedAnalysisId(analysisId);
    setCurrentView("detail");
  }, []);

  return (
    <WorkspaceContext.Provider
      value={{
        currentView,
        setCurrentView,
        selectedAnalysisId,
        openAnalysis,
        stats,
        statsLoading,
        refreshStats,
        toastMessage,
        showToast,
      }}
    >
      {children}
      {toastMessage && (
        <div
          role="status"
          aria-live="polite"
          className="fixed bottom-5 right-5 z-50 max-w-sm px-4 py-2.5 rounded-lg border border-[#00F0FF]/30 bg-[#1c232c] text-white text-xs shadow-2xl transition-all"
        >
          {toastMessage}
        </div>
      )}
    </WorkspaceContext.Provider>
  );
}

export function useWorkspace() {
  const context = useContext(WorkspaceContext);
  if (!context) {
    throw new Error("useWorkspace must be used within a WorkspaceProvider");
  }
  return context;
}
