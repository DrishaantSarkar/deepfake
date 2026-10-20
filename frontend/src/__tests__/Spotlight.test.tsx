import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import Spotlight from "../Spotlight";
import { WorkspaceProvider } from "../context/WorkspaceContext";

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
  },
}));

function renderWithWorkspace(ui: React.ReactElement) {
  return render(<WorkspaceProvider>{ui}</WorkspaceProvider>);
}

describe("Spotlight Command Deck", () => {
  it("opens on Cmd+K, displays commands, filters on search, and closes on Escape", () => {
    renderWithWorkspace(<Spotlight />);

    // Initially closed
    expect(
      screen.queryByRole("dialog", { name: "Spotlight Command Deck" })
    ).not.toBeInTheDocument();

    // Trigger Cmd+K
    fireEvent.keyDown(window, { key: "k", metaKey: true });

    // Verify modal is open and has dialog semantics
    const dialog = screen.getByRole("dialog", { name: "Spotlight Command Deck" });
    expect(dialog).toBeInTheDocument();

    // Verify search input is present
    const searchInput = screen.getByPlaceholderText(/Type a command/i);
    expect(searchInput).toBeInTheDocument();

    // Verify action items
    expect(screen.getByText("New Media Analysis")).toBeInTheDocument();
    expect(screen.getByText("Facial Manipulation Scan")).toBeInTheDocument();

    // Filter by query
    fireEvent.change(searchInput, { target: { value: "Facial" } });
    expect(screen.getByText("Facial Manipulation Scan")).toBeInTheDocument();
    expect(screen.queryByText("New Media Analysis")).not.toBeInTheDocument();

    // Press Escape to dismiss
    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(
      screen.queryByRole("dialog", { name: "Spotlight Command Deck" })
    ).not.toBeInTheDocument();
  });
});
