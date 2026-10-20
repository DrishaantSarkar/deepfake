import React, { useState, useEffect, useRef } from "react";
import { useWorkspace } from "./context/WorkspaceContext";

interface CommandItem {
  id: string;
  category: "Evidence" | "Pipelines" | "Reports";
  title: string;
  subtitle: string;
  shortcut?: string;
  action: () => void;
}

export default function Spotlight() {
  const { setCurrentView } = useWorkspace();
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);

  const inputRef = useRef<HTMLInputElement>(null);
  const prevFocusedElement = useRef<HTMLElement | null>(null);

  const commands: CommandItem[] = [
    {
      id: "new-analysis",
      category: "Pipelines",
      title: "New Media Analysis",
      subtitle: "Ingest and analyze image or video evidence",
      shortcut: "N",
      action: () => {
        setIsOpen(false);
        setCurrentView("new");
      },
    },
    {
      id: "scan-face",
      category: "Pipelines",
      title: "Facial Manipulation Scan",
      subtitle: "Execute deepfake facial artifact detection",
      action: () => {
        setIsOpen(false);
        setCurrentView("new");
      },
    },
    {
      id: "scan-audio",
      category: "Pipelines",
      title: "Audio Provenance Check",
      subtitle: "Synthesizer artifact and voice spoofing analysis",
      action: () => {
        setIsOpen(false);
        setCurrentView("new");
      },
    },
    {
      id: "evidence-history",
      category: "Evidence",
      title: "Browse Evidence Vault",
      subtitle: "Search local case files and immutable artifacts",
      shortcut: "E",
      action: () => {
        setIsOpen(false);
        setCurrentView("history");
      },
    },
    {
      id: "export-report",
      category: "Reports",
      title: "Export Forensic Dossier",
      subtitle: "Generate cryptographically verifiable JSON-LD report",
      shortcut: "X",
      action: () => {
        setIsOpen(false);
        setCurrentView("history");
      },
    },
  ];

  const filtered = commands.filter(
    (c) =>
      c.title.toLowerCase().includes(query.toLowerCase()) ||
      c.subtitle.toLowerCase().includes(query.toLowerCase()) ||
      c.category.toLowerCase().includes(query.toLowerCase())
  );

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setIsOpen((prev) => {
          if (!prev) {
            setQuery("");
            setSelectedIndex(0);
          }
          return !prev;
        });
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  useEffect(() => {
    if (isOpen) {
      prevFocusedElement.current = document.activeElement as HTMLElement;
      const timer = setTimeout(() => inputRef.current?.focus(), 50);
      return () => clearTimeout(timer);
    } else if (prevFocusedElement.current) {
      prevFocusedElement.current.focus();
    }
  }, [isOpen]);

  const handleKeyNavigation = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      e.preventDefault();
      setIsOpen(false);
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIndex((prev) => (filtered.length ? (prev + 1) % filtered.length : 0));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIndex((prev) =>
        filtered.length ? (prev - 1 + filtered.length) % filtered.length : 0
      );
    } else if (e.key === "Enter" && filtered[selectedIndex]) {
      e.preventDefault();
      filtered[selectedIndex].action();
    }
  };

  if (!isOpen) {
    return null;
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-24 px-4 bg-black/75 backdrop-blur-md"
      onClick={() => setIsOpen(false)}
      role="presentation"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Spotlight Command Deck"
        className="w-full max-w-xl bg-[#181818] border border-white/10 rounded-2xl shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={handleKeyNavigation}
      >
        <div className="flex items-center gap-3 px-4 py-3 border-b border-white/10 bg-[#121212]/50">
          <span className="text-[#00F0FF] text-lg font-bold" aria-hidden="true">
            ⌘
          </span>
          <input
            ref={inputRef}
            type="text"
            className="w-full bg-transparent border-0 outline-none text-white placeholder-neutral-500 text-sm"
            placeholder="Type a command, search evidence, or export reports (ESC to exit)..."
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setSelectedIndex(0);
            }}
            aria-autocomplete="list"
            aria-controls="spotlight-results"
          />
          <kbd className="px-2 py-0.5 text-[10px] font-mono text-neutral-400 bg-neutral-800 border border-neutral-700 rounded">
            ESC
          </kbd>
        </div>

        <ul
          id="spotlight-results"
          role="listbox"
          className="max-h-80 overflow-y-auto p-2 space-y-1"
        >
          {filtered.length === 0 ? (
            <li className="px-4 py-8 text-center text-xs text-neutral-500">
              No forensic actions or evidence matching &quot;{query}&quot;
            </li>
          ) : (
            filtered.map((item, idx) => {
              const isSelected = idx === selectedIndex;
              return (
                <li
                  key={item.id}
                  role="option"
                  aria-selected={isSelected}
                  onClick={() => item.action()}
                  onMouseEnter={() => setSelectedIndex(idx)}
                  className={`flex items-center justify-between px-3 py-2.5 rounded-lg cursor-pointer transition-colors ${
                    isSelected
                      ? "bg-[#1DB954]/15 border border-[#1DB954]/30 text-white"
                      : "text-neutral-300 hover:bg-neutral-800/60"
                  }`}
                >
                  <div className="flex flex-col">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold">{item.title}</span>
                      <span className="text-[10px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded bg-neutral-800 text-neutral-400">
                        {item.category}
                      </span>
                    </div>
                    <span className="text-xs text-neutral-500 mt-0.5">{item.subtitle}</span>
                  </div>
                  {item.shortcut && (
                    <kbd className="px-1.5 py-0.5 text-[10px] font-mono text-neutral-400 bg-neutral-900 border border-neutral-800 rounded">
                      {item.shortcut}
                    </kbd>
                  )}
                </li>
              );
            })
          )}
        </ul>

        <div className="flex items-center justify-between px-4 py-2 border-t border-white/5 bg-[#121212]/80 text-[11px] text-neutral-400">
          <span>Navigate with ↑ / ↓</span>
          <span>Press Enter to select</span>
        </div>
      </div>
    </div>
  );
}
