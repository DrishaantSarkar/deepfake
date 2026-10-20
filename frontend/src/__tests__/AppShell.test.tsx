import React from "react";
import { render, screen } from "@testing-library/react";
import AppShell from "../AppShell";

// Mock the API module so no real HTTP calls are made during tests.
jest.mock("../services/api", () => ({
  api: {
    getStats: jest.fn().mockResolvedValue({
      total: 0,
      completed: 0,
      partial: 0,
      failed: 0,
      unavailable: 0,
      human_review: 0,
    }),
    getAnalyses: jest.fn().mockResolvedValue({ total: 0, limit: 5, offset: 0, items: [] }),
    getHealth: jest
      .fn()
      .mockResolvedValue({ status: "ok", application: "TRUSTLENS", persistence: "sqlite" }),
    getCapabilities: jest.fn().mockResolvedValue({
      supported_upload_extensions: [".jpg", ".mp4"],
      max_upload_bytes: 104857600,
      image: { ingestion: "AVAILABLE" },
      video: { ingestion: "AVAILABLE" },
      provenance: {},
      fusion: "UNAVAILABLE",
      audio_analysis: "UNAVAILABLE",
      source_media_retention: "temporary",
      report_persistence: "sqlite",
      authentication: "none",
    }),
    hasSession: jest.fn().mockReturnValue(true),
    onSessionRequired: jest.fn().mockReturnValue(() => {}),
    login: jest.fn().mockResolvedValue(true),
    logout: jest.fn(),
  },
}));

describe("AppShell Smoke Test", () => {
  it("renders the TRUSTLENS application shell, navigation, and overview workspace", async () => {
    render(<AppShell />);

    // Verify Brand / Header text
    expect(screen.getByText("LOCAL FORENSICS")).toBeInTheDocument();

    // Verify Primary navigation
    expect(screen.getByRole("navigation", { name: /primary navigation/i })).toBeInTheDocument();

    // Verify Workspace section (from DashboardView rendered by InvestigationDesk)
    expect(screen.getByText("INVESTIGATION DESK")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Overview" })).toBeInTheDocument();

    // Verify metrics category cards are present
    expect(screen.getByText("TOTAL ANALYSES")).toBeInTheDocument();
    expect(screen.getByText("COMPLETED")).toBeInTheDocument();
    expect(screen.getByText("HUMAN REVIEW")).toBeInTheDocument();
  });
});
