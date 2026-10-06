"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { buildArtifactUrl, buildSseUrl, fetchRun, fetchRunEvents } from "@/lib/api";
import { ViewerArtifact, ViewerEvent, ViewerRun } from "@/lib/types";

const STREAM_EVENT_TYPES = [
  "reasoning",
  "run_started",
  "tool_called",
  "tool_result",
  "overlay_generated",
  "log",
  "frameStarted",
  "frame_completed",
  "run_completed",
  "run_failed",
  "run_terminal",
] as const;

function formatTimestamp(value: string): string {
  return new Date(value).toLocaleTimeString();
}

function appendDedupedEvents(current: ViewerEvent[], incoming: ViewerEvent[]): ViewerEvent[] {
  const merged = new Map<number, ViewerEvent>();
  for (const event of current) {
    merged.set(event.sequence, event);
  }
  for (const event of incoming) {
    merged.set(event.sequence, event);
  }
  return Array.from(merged.values()).toSorted((left, right) => left.sequence - right.sequence);
}

function resolveArtifactFromEvent(event: ViewerEvent | null): ViewerArtifact | null {
  return event?.artifact || null;
}

function summarizePayload(value: Record<string, unknown> | null | undefined): string {
  if (!value) {
    return "No structured payload";
  }
  return JSON.stringify(value, null, 2);
}

export function RunDetailPage({ runId }: { runId: string }) {
  const [run, setRun] = useState<ViewerRun | null>(null);
  const [events, setEvents] = useState<ViewerEvent[]>([]);
  const [selectedEventSequence, setSelectedEventSequence] = useState<number | null>(null);
  const [streamAfterSequence, setStreamAfterSequence] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadInitialState(): Promise<void> {
      try {
        const [nextRun, nextEvents] = await Promise.all([fetchRun(runId), fetchRunEvents(runId)]);
        if (cancelled) {
          return;
        }
        setRun(nextRun);
        setEvents(nextEvents);
        setStreamAfterSequence(nextEvents.length > 0 ? nextEvents[nextEvents.length - 1].sequence : 0);
        const latestOverlay = nextEvents.toReversed().find((event) => event.event_type === "overlay_generated");
        if (latestOverlay) {
          setSelectedEventSequence(latestOverlay.sequence);
        } else if (nextEvents.length > 0) {
          setSelectedEventSequence(nextEvents[nextEvents.length - 1].sequence);
        }
      } catch (nextError) {
        if (!cancelled) {
          setError(nextError instanceof Error ? nextError.message : "Failed to load run");
        }
      }
    }

    void loadInitialState();
    return () => {
      cancelled = true;
    };
  }, [runId]);

  useEffect(() => {
    if (streamAfterSequence === null) {
      return;
    }

    const eventSource = new EventSource(buildSseUrl(runId, streamAfterSequence));

    const handleStreamEvent = (messageEvent: MessageEvent<string>) => {
      const parsed = JSON.parse(messageEvent.data) as ViewerEvent | { status?: string };
      if ("sequence" in parsed) {
        setEvents((current) => appendDedupedEvents(current, [parsed]));
        if (parsed.event_type === "overlay_generated") {
          setSelectedEventSequence(parsed.sequence);
        }
        if (parsed.event_type === "run_completed" || parsed.event_type === "run_failed") {
          void fetchRun(runId).then(setRun).catch(() => undefined);
        }
        return;
      }

      if (parsed.status) {
        setRun((current) => (current ? { ...current, status: parsed.status || current.status } : current));
      }
    };

    for (const eventType of STREAM_EVENT_TYPES) {
      eventSource.addEventListener(eventType, handleStreamEvent as EventListener);
    }

    const handleStreamError = () => {
      eventSource.close();
    };
    eventSource.addEventListener("error", handleStreamError);

    return () => {
      for (const eventType of STREAM_EVENT_TYPES) {
        eventSource.removeEventListener(eventType, handleStreamEvent as EventListener);
      }
      eventSource.removeEventListener("error", handleStreamError);
      eventSource.close();
    };
  }, [runId, streamAfterSequence]);

  const selectedEvent = useMemo(
    () => events.find((event) => event.sequence === selectedEventSequence) || null,
    [events, selectedEventSequence],
  );

  const overlayEvents = useMemo(
    () => events.filter((event) => event.event_type === "overlay_generated"),
    [events],
  );

  const reasoningEvents = useMemo(
    () => events.filter((event) => event.event_type === "reasoning"),
    [events],
  );

  const selectedArtifact = resolveArtifactFromEvent(selectedEvent) || resolveArtifactFromEvent(overlayEvents.at(-1) || null);

  return (
    <main className="viewer-shell run-detail-shell">
      <section className="detail-header panel-card">
        <div>
          <Link className="back-link" href="/">
            Back to runs
          </Link>
          <p className="panel-kicker">Run</p>
          <h1>{run?.run_label || run?.frame_id || runId}</h1>
          <p className="viewer-subtitle">{run?.frame_uri || "Loading frame URI…"}</p>
        </div>
        <div className="detail-header-meta">
          <span className={`status-pill status-${run?.status || "queued"}`}>{run?.status || "queued"}</span>
          <span>{run ? formatTimestamp(run.updated_at) : "…"}</span>
        </div>
      </section>

      {error ? <p className="error-banner">{error}</p> : null}

      <section className="detail-grid">
        <aside className="panel-card artifact-rail">
          <div className="panel-header">
            <div>
              <p className="panel-kicker">Artifacts</p>
              <h2>Stage overlays</h2>
            </div>
          </div>
          <div className="artifact-list">
            {overlayEvents.length === 0 ? <p className="empty-state">No overlay artifacts yet.</p> : null}
            {overlayEvents.map((event) => {
              const artifact = event.artifact;
              if (!artifact) {
                return null;
              }
              return (
                <button
                  className={`artifact-card ${selectedEventSequence === event.sequence ? "artifact-card-active" : ""}`}
                  key={event.sequence}
                  onClick={() => setSelectedEventSequence(event.sequence)}
                  type="button"
                >
                  <span className="artifact-stage">{event.stage_name || artifact.artifact_kind}</span>
                  <strong>{artifact.artifact_kind}</strong>
                  <span className="artifact-meta">
                    {artifact.width}×{artifact.height}
                  </span>
                </button>
              );
            })}
          </div>
        </aside>

        <section className="panel-card main-viewport">
          <div className="panel-header">
            <div>
              <p className="panel-kicker">Viewport</p>
              <h2>{selectedEvent?.stage_name || "Latest overlay"}</h2>
            </div>
          </div>

          <div className="image-stage">
            {selectedArtifact ? (
              <img
                alt={selectedArtifact.artifact_kind}
                className="artifact-image"
                src={buildArtifactUrl(runId, selectedArtifact.artifact_id)}
              />
            ) : (
              <div className="empty-state image-empty">Waiting for the first rendered artifact…</div>
            )}
          </div>

          <div className="detail-panels">
            <div className="detail-panel">
              <p className="panel-kicker">Selected event</p>
              <pre>{selectedEvent ? summarizePayload(selectedEvent.payload ?? null) : "No event selected."}</pre>
            </div>
            <div className="detail-panel">
              <p className="panel-kicker">Final annotations</p>
              <pre>{run?.result_annotations || "Run still in progress."}</pre>
            </div>
          </div>

          {reasoningEvents.length > 0 ? (
            <div className="reasoning-trace">
              <div className="panel-header">
                <div>
                  <p className="panel-kicker">Agent reasoning</p>
                  <h2>Thought / Action / Observation</h2>
                </div>
              </div>
              <div className="reasoning-list">
                {reasoningEvents.map((event) => {
                  const stage = event.stage_name || "thought";
                  const iteration = event.payload?.iteration as number | undefined;
                  return (
                    <div key={event.sequence} className={`reasoning-step reasoning-${stage}`}>
                      <div className="reasoning-step-header">
                        <span className={`reasoning-badge badge-${stage}`}>{stage}</span>
                        {iteration !== undefined ? <span className="reasoning-iter">Step {iteration}</span> : null}
                        <span className="event-time">{formatTimestamp(event.timestamp)}</span>
                      </div>
                      <p className="reasoning-message">{event.message || ""}</p>
                      {stage === "action" && event.payload?.tool_name ? (
                        <p className="reasoning-detail">Tool: <strong>{event.payload.tool_name as string}</strong></p>
                      ) : null}
                      {stage === "observation" && event.payload?.observation_length ? (
                        <p className="reasoning-detail">Observation: {(event.payload.observation_length as number).toLocaleString()} chars</p>
                      ) : null}
                    </div>
                  );
                })}
              </div>
            </div>
          ) : null}
        </section>

        <aside className="panel-card event-stream">
          <div className="panel-header">
            <div>
              <p className="panel-kicker">Stream</p>
              <h2>Logs and tool calls</h2>
            </div>
          </div>

          <div className="event-list">
            {events.length === 0 ? <p className="empty-state">Waiting for events…</p> : null}
            {events.map((event) => (
              <button
                className={`event-card ${selectedEventSequence === event.sequence ? "event-card-active" : ""}`}
                key={event.sequence}
                onClick={() => setSelectedEventSequence(event.sequence)}
                type="button"
              >
                <div className="event-card-top">
                  <span className={`status-dot status-dot-${event.status || "info"}`} />
                  <strong>{event.stage_name || event.event_type}</strong>
                  <span className="event-time">{formatTimestamp(event.timestamp)}</span>
                </div>
                <p>{event.message || event.event_type}</p>
                <span className="event-type">{event.event_type}</span>
              </button>
            ))}
          </div>
        </aside>
      </section>
    </main>
  );
}
