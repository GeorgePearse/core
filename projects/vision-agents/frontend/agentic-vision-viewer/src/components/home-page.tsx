"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useMemo, useState } from "react";

import { fetchRuns, startRun } from "@/lib/api";
import { StartRunPayload, ViewerRun } from "@/lib/types";

const DEFAULT_FORM: StartRunPayload = {
  frame_uri: "",
  dataset_name: "",
  run_label: "",
  max_iters: 16,
  sam3_handler_name: "premier",
};

function formatTimestamp(value: string): string {
  return new Date(value).toLocaleString();
}

export function HomePage() {
  const router = useRouter();
  const [runs, setRuns] = useState<ViewerRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [formState, setFormState] = useState<StartRunPayload>(DEFAULT_FORM);

  async function loadRuns(): Promise<void> {
    setLoading(true);
    setError(null);
    try {
      const nextRuns = await fetchRuns();
      setRuns(nextRuns);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Failed to load runs");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadRuns();
  }, []);

  const runCountLabel = useMemo(() => `${runs.length} run${runs.length === 1 ? "" : "s"}`, [runs.length]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const payload: StartRunPayload = {
        ...formState,
        dataset_name: formState.dataset_name || undefined,
        run_label: formState.run_label || undefined,
      };
      const result = await startRun(payload);
      router.push(`/runs/${result.run_id}`);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Failed to start run");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="viewer-shell">
      <section className="viewer-hero">
        <div className="viewer-hero-copy">
          <p className="viewer-eyebrow">Agentic Vision Viewer</p>
          <h1>Watch the segmentation loop think, call tools, and redraw masks in real time.</h1>
          <p className="viewer-subtitle">
            The viewer streams stage events, stores every overlay artifact, and lets you replay a completed run without tailing raw logs.
          </p>
        </div>
        <div className="viewer-hero-stats">
          <div className="metric-card">
            <span>Recent runs</span>
            <strong>{runCountLabel}</strong>
          </div>
          <div className="metric-card">
            <span>Primary use</span>
            <strong>SAM3 + Gemini critique</strong>
          </div>
        </div>
      </section>

      <section className="viewer-grid">
        <div className="panel-card launch-card">
          <div className="panel-header">
            <div>
              <p className="panel-kicker">Launch</p>
              <h2>Start a live run</h2>
            </div>
          </div>

          <form className="launch-form" onSubmit={(event) => void handleSubmit(event)}>
            <label>
              <span>Frame URI</span>
              <textarea
                required
                rows={4}
                placeholder="gs://bucket/path/to/frame.jpg"
                value={formState.frame_uri}
                onChange={(event) => setFormState((current) => ({ ...current, frame_uri: event.target.value }))}
              />
            </label>

            <div className="field-grid">
              <label>
                <span>Dataset name</span>
                <input
                  value={formState.dataset_name || ""}
                  onChange={(event) => setFormState((current) => ({ ...current, dataset_name: event.target.value }))}
                />
              </label>
              <label>
                <span>Run label</span>
                <input
                  value={formState.run_label || ""}
                  onChange={(event) => setFormState((current) => ({ ...current, run_label: event.target.value }))}
                />
              </label>
            </div>

            <div className="field-grid">
              <label>
                <span>Max iters</span>
                <input
                  type="number"
                  min={1}
                  max={40}
                  value={formState.max_iters}
                  onChange={(event) =>
                    setFormState((current) => ({
                      ...current,
                      max_iters: Number(event.target.value || 16),
                    }))
                  }
                />
              </label>
              <label>
                <span>SAM3 handler</span>
                <input
                  value={formState.sam3_handler_name}
                  onChange={(event) => setFormState((current) => ({ ...current, sam3_handler_name: event.target.value }))}
                />
              </label>
            </div>

            <div className="form-actions">
              <button className="primary-button" type="submit" disabled={submitting}>
                {submitting ? "Launching..." : "Launch run"}
              </button>
              <button className="ghost-button" type="button" onClick={() => void loadRuns()} disabled={loading}>
                Refresh list
              </button>
            </div>
          </form>

          {error ? <p className="error-banner">{error}</p> : null}
        </div>

        <div className="panel-card">
          <div className="panel-header">
            <div>
              <p className="panel-kicker">Replay</p>
              <h2>Recent runs</h2>
            </div>
          </div>

          <div className="run-list">
            {loading ? <p className="empty-state">Loading runs…</p> : null}
            {!loading && runs.length === 0 ? <p className="empty-state">No runs recorded yet.</p> : null}
            {runs.map((run) => (
              <Link className="run-card" href={`/runs/${run.run_id}`} key={run.run_id}>
                <div className="run-card-row">
                  <span className={`status-pill status-${run.status}`}>{run.status}</span>
                  <span className="run-timestamp">{formatTimestamp(run.updated_at)}</span>
                </div>
                <h3>{run.run_label || run.frame_id || run.run_id}</h3>
                <p className="run-uri">{run.frame_uri}</p>
                <div className="run-meta">
                  <span>{run.dataset_name || "no dataset"}</span>
                  <span>{run.sam3_handler_name || "default SAM3"}</span>
                </div>
              </Link>
            ))}
          </div>
        </div>
      </section>
    </main>
  );
}
