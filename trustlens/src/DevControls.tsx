import React, { useState, useEffect } from "react";

export default function DevControls() {
  const [isOpen, setIsOpen] = useState(false);
  const [density, setDensity] = useState(
    () => localStorage.getItem("trustlens_dev_density") || "1"
  );
  const [glass, setGlass] = useState(() => localStorage.getItem("trustlens_dev_glass") || "1");
  const [saturation, setSaturation] = useState(
    () => localStorage.getItem("trustlens_dev_sat") || "100"
  );

  useEffect(() => {
    document.documentElement.style.setProperty("--ui-density-scale", density);
    localStorage.setItem("trustlens_dev_density", density);
  }, [density]);

  useEffect(() => {
    document.documentElement.style.setProperty("--ui-glass-intensity", glass);
    localStorage.setItem("trustlens_dev_glass", glass);
  }, [glass]);

  useEffect(() => {
    document.documentElement.style.setProperty("--ui-accent-saturation", `${saturation}%`);
    localStorage.setItem("trustlens_dev_sat", saturation);
  }, [saturation]);

  if (process.env.NODE_ENV === "production") {
    return null;
  }

  return (
    <aside
      aria-label="Development Controls"
      style={{
        position: "fixed",
        bottom: "16px",
        left: "16px",
        zIndex: 9999,
        background: "rgba(20, 24, 30, 0.95)",
        border: "1px solid #3a4350",
        borderRadius: "8px",
        padding: "10px 14px",
        fontSize: "11px",
        color: "#edf1f7",
        boxShadow: "0 4px 16px rgba(0,0,0,0.5)",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "10px",
        }}
      >
        <span style={{ fontWeight: 600, color: "#8bcbd2" }}>DEV CONTROLS</span>
        <button
          type="button"
          onClick={() => setIsOpen(!isOpen)}
          style={{
            background: "#292f39",
            border: "none",
            color: "#edf1f7",
            padding: "2px 8px",
            borderRadius: "4px",
            cursor: "pointer",
            fontSize: "10px",
          }}
        >
          {isOpen ? "Hide" : "Tune UI"}
        </button>
      </div>

      {isOpen && (
        <div
          style={{
            marginTop: "10px",
            display: "flex",
            flexDirection: "column",
            gap: "8px",
          }}
        >
          <div>
            <label htmlFor="dev-density" style={{ display: "block", marginBottom: "2px" }}>
              Density Scale: {density}x
            </label>
            <input
              id="dev-density"
              type="range"
              min="0.8"
              max="1.2"
              step="0.05"
              value={density}
              onChange={(e) => setDensity(e.target.value)}
              style={{ width: "100%" }}
            />
          </div>
          <div>
            <label htmlFor="dev-glass" style={{ display: "block", marginBottom: "2px" }}>
              Glass Intensity: {glass}x
            </label>
            <input
              id="dev-glass"
              type="range"
              min="0"
              max="2"
              step="0.1"
              value={glass}
              onChange={(e) => setGlass(e.target.value)}
              style={{ width: "100%" }}
            />
          </div>
          <div>
            <label htmlFor="dev-sat" style={{ display: "block", marginBottom: "2px" }}>
              Accent Saturation: {saturation}%
            </label>
            <input
              id="dev-sat"
              type="range"
              min="50"
              max="150"
              step="5"
              value={saturation}
              onChange={(e) => setSaturation(e.target.value)}
              style={{ width: "100%" }}
            />
          </div>
        </div>
      )}
    </aside>
  );
}
