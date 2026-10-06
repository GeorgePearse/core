import { StartRunPayload, ViewerEvent, ViewerRun } from "@/lib/types";

function trimTrailingSlash(value: string): string {
  return value.endsWith("/") ? value.slice(0, -1) : value;
}

export function getApiBaseUrl(): string {
  const configured = process.env.NEXT_PUBLIC_AGENTIC_VISION_VIEWER_API_BASE_URL;
  return trimTrailingSlash(configured || "http://localhost:8000");
}

export function buildRunApiUrl(path: string): string {
  return `${getApiBaseUrl()}/agentic-vision-viewer${path}`;
}

export async function fetchRuns(): Promise<ViewerRun[]> {
  const response = await fetch(buildRunApiUrl("/runs"), { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to load runs (${response.status})`);
  }
  const payload = (await response.json()) as { runs: ViewerRun[] };
  return payload.runs;
}

export async function fetchRun(runId: string): Promise<ViewerRun> {
  const response = await fetch(buildRunApiUrl(`/runs/${runId}`), { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to load run ${runId} (${response.status})`);
  }
  return (await response.json()) as ViewerRun;
}

export async function fetchRunEvents(runId: string, afterSequence = 0): Promise<ViewerEvent[]> {
  const response = await fetch(buildRunApiUrl(`/runs/${runId}/events?after_sequence=${afterSequence}`), {
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`Failed to load events for ${runId} (${response.status})`);
  }
  const payload = (await response.json()) as { events: ViewerEvent[] };
  return payload.events;
}

export async function startRun(payload: StartRunPayload): Promise<{ run_id: string; status: string }> {
  const response = await fetch(buildRunApiUrl("/runs"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Failed to start run (${response.status}): ${errorText}`);
  }
  return (await response.json()) as { run_id: string; status: string };
}

export function buildArtifactUrl(runId: string, artifactId: string): string {
  return buildRunApiUrl(`/runs/${runId}/artifacts/${artifactId}`);
}

export function buildSseUrl(runId: string, afterSequence = 0): string {
  return buildRunApiUrl(`/runs/${runId}/stream?after_sequence=${afterSequence}`);
}
