export type AltitudeId = "paint" | "compose" | "lens" | "cli" | "live" | "surface";

export interface AltitudeStep {
  id: AltitudeId;
  title: string;
  shortTitle: string;
  summary: string;
  outcome: string;
  contract: string;
}

export const altitudeSteps: AltitudeStep[] = [
  {
    id: "paint",
    title: "Paint a value",
    shortTitle: "paint",
    summary:
      "Begin with paint(), the direct path from a Python value to terminal output. Declared shapes are transcribed; an explicit lens interprets when you need more meaning.",
    outcome: "Deliver useful output without first building a CLI or application shell.",
    contract: "paint(subject, *, zoom=None, lens=None, file=None)",
  },
  {
    id: "compose",
    title: "Compose blocks",
    shortTitle: "compose",
    summary:
      "Turn output into immutable Blocks, then join, pad, border, truncate, or arrange them responsively with pure composition functions.",
    outcome: "Build a layout that remains a value: easy to inspect, reuse, and deliver.",
    contract: "Block → compose → Block",
  },
  {
    id: "lens",
    title: "Declare a lens",
    shortTitle: "lens",
    summary:
      "Use a lens when raw data needs an explicit visual interpretation. A lens receives only the data, a zoom level, and the available width, and returns a Block.",
    outcome: "Separate domain meaning from terminal delivery while keeping the rendering rule pure.",
    contract: "lens(data, zoom, width) → Block",
  },
  {
    id: "cli",
    title: "Put the lens behind a CLI",
    shortTitle: "CLI",
    summary:
      "run_cli uses a broader renderer contract: it compiles declared flags into Fidelity, resolves format and mode, and offers current width at delivery time. A renderer can pass fidelity.depth to a zoom-based lens.",
    outcome: "Gain quiet, verbose, plain, JSON, help, and completion behavior around one renderer.",
    contract: "renderer(data, fidelity, width) → Block",
  },
  {
    id: "live",
    title: "Deliver changing state",
    shortTitle: "live",
    summary:
      "Add a stream of state while keeping the renderer pure. Painted chooses in-place or stream-surface delivery from the resolved host context.",
    outcome: "Refresh terminal output without changing the data-to-Block contract.",
    contract: "fetch_stream → renderer → LIVE delivery",
  },
  {
    id: "surface",
    title: "Own an interactive Surface",
    shortTitle: "Surface",
    summary:
      "Escalate when input, focus, cursor, search, or modal layers become part of the experience. Surface owns terminal lifecycle and frame delivery; your app owns state.",
    outcome: "Build and replay-test a full interactive terminal application.",
    contract: "state + events → layers → Surface frame",
  },
];

export interface InternalRung {
  id: string;
  name: string;
  summary: string;
  altitude: AltitudeId;
}

export const internalRungs: InternalRung[] = [
  {
    id: "cell",
    name: "Cell",
    summary: "One display cell: a character plus semantic style and optional denotation.",
    altitude: "paint",
  },
  {
    id: "style",
    name: "Style",
    summary: "Composable foreground, background, and text attributes carried by cells.",
    altitude: "paint",
  },
  {
    id: "span",
    name: "Span",
    summary: "A styled run of text measured in terminal display columns.",
    altitude: "paint",
  },
  {
    id: "line",
    name: "Line",
    summary: "An ordered group of spans that materializes as one row of cells.",
    altitude: "paint",
  },
  {
    id: "block",
    name: "Block",
    summary: "The immutable rectangle shared by rendering, composition, and delivery.",
    altitude: "compose",
  },
  {
    id: "buffer",
    name: "Buffer",
    summary: "The mutable canvas a host uses to assemble and diff a complete frame.",
    altitude: "compose",
  },
  {
    id: "lens",
    name: "Lens",
    summary: "A pure (data, zoom, width) → Block function for explicit visual interpretation.",
    altitude: "lens",
  },
  {
    id: "surface",
    name: "Surface",
    summary: "The interactive host that owns lifecycle, input, and frame delivery.",
    altitude: "surface",
  },
];

export const altitudeHref = (id: AltitudeId) => `/learn/${id}/`;
