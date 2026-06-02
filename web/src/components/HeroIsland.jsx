/* HeroIsland.jsx — PLACEHOLDER landing-hero island.
 *
 * This is a deliberately tiny stub that proves the island pipeline works:
 * client-side React hydration + interval state + the painted design tokens.
 * It will be REPLACED by Claude Design's designated, polished hero component
 * (the no-cliffs CLI->TUI walkthrough or the system-monitor Surface) once the
 * packaged kit lands. Keep the boundary thin: one default export, mounted via
 * `client:load` from index.astro.
 *
 * Laning note: cosmetic recreation only — this is NOT painted's real renderer.
 */
import { useEffect, useState } from "react";

const SPIN = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"];

export default function HeroIsland() {
  const [frame, setFrame] = useState(0);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    setHydrated(true);
    const id = setInterval(() => setFrame((f) => (f + 1) % SPIN.length), 90);
    return () => clearInterval(id);
  }, []);

  const box = {
    fontFamily: "var(--font-mono)",
    background: "var(--panel)",
    border: "1px solid var(--line-bold)",
    borderRadius: "var(--radius)",
    maxWidth: "640px",
  };
  const titlebar = {
    background: "var(--cyan)",
    color: "var(--ink)",
    fontWeight: "var(--w-bold)",
    padding: "var(--sp-1) var(--sp-3)",
  };
  const body = { padding: "var(--sp-3)", color: "var(--fg-2)" };

  return (
    <div style={box}>
      <div style={titlebar}>painted · hero (placeholder island)</div>
      <div style={body}>
        <div>
          <span style={{ color: "var(--yellow)" }}>{SPIN[frame]}</span>{" "}
          <span style={{ color: "var(--fg-dim)" }}>
            scanning the cell grid…
          </span>
        </div>
        <div style={{ marginTop: "var(--sp-2)" }}>
          <span style={{ color: "var(--green)" }}>▸</span> island{" "}
          <span style={{ color: hydrated ? "var(--green)" : "var(--red)" }}>
            {hydrated ? "hydrated" : "static"}
          </span>{" "}
          <span style={{ color: "var(--fg-dim)" }}>
            — swap me for the Design hero
          </span>
        </div>
      </div>
    </div>
  );
}
