import type { DatabaseInfo, Program, MetaFile, MetaContent } from '../types';

const API_BASE = import.meta.env.VITE_API_URL || '/api';

export async function listDatabases(): Promise<DatabaseInfo[]> {
  const response = await fetch(`${API_BASE}/runs`);
  if (!response.ok) {
    throw new Error(`Failed to load runs (HTTP ${response.status})`);
  }
  const data = await response.json();
  return (data.runs ?? []).map(
    (r: {
      run_id: string;
      task_name: string;
      status: string;
      start_time: string;
      population_size: number;
      total_generations: number;
    }) => ({
      path: r.run_id,
      name: `${r.task_name} (${r.status})`,
      sort_key: r.start_time,
      stats: {
        total: r.population_size,
        working: r.total_generations,
      },
    })
  );
}

export async function getPrograms(runId: string): Promise<Program[]> {
  const response = await fetch(`${API_BASE}/runs/${runId}/individuals`);
  if (!response.ok) {
    if (response.status === 503) {
      throw new Error(
        'Database temporarily unavailable - evolution may be running'
      );
    }
    throw new Error(`Failed to load data (HTTP ${response.status})`);
  }
  const data = await response.json();
  return (data.individuals ?? []).map(
    (r: {
      id: string;
      parent_id: string | null;
      code: string;
      language: string;
      generation: number;
      timestamp: string;
      agent_name: string;
      combined_score: number;
      fitness_score: number;
      metrics: Record<string, unknown>;
      text_feedback: string;
      metadata: {
        patch_name: string;
        patch_type: string;
        api_cost: number;
        embed_cost: number;
        novelty_cost: number;
      };
      correct: boolean;
      is_pareto: boolean;
      code_size: number;
    }) => ({
      id: r.id,
      parent_id: r.parent_id,
      code: r.code,
      language: r.language,
      generation: r.generation,
      timestamp: new Date(r.timestamp).getTime() / 1000,
      agent_name: r.agent_name,
      combined_score: r.combined_score,
      public_metrics: r.metrics,
      private_metrics: null,
      text_feedback: r.text_feedback || null,
      metadata: r.metadata ?? { patch_name: 'unknown', patch_type: 'unknown' },
      complexity: r.code_size ?? null,
      embedding: null,
      embedding_pca_2d: null,
      embedding_pca_3d: null,
      island_idx: null,
      correct: r.correct,
    })
  );
}

export async function getMetaFiles(runId: string): Promise<MetaFile[]> {
  const response = await fetch(`${API_BASE}/runs/${runId}/generations`);
  if (!response.ok) {
    if (response.status === 404) {
      return [];
    }
    throw new Error(`Failed to load generations (HTTP ${response.status})`);
  }
  const data = await response.json();
  return (data.generations ?? []).map(
    (g: { generation: number; timestamp: string }) => ({
      generation: g.generation,
      filename: `generation_${g.generation}`,
      path: `${runId}/generations/${g.generation}`,
    })
  );
}

export async function getMetaContent(
  runId: string,
  generation: number
): Promise<MetaContent> {
  const response = await fetch(
    `${API_BASE}/runs/${runId}/generations/${generation}`
  );
  if (!response.ok) {
    throw new Error(
      `Failed to load generation details (HTTP ${response.status})`
    );
  }
  const data = await response.json();
  const content = [
    `# Generation ${data.generation}`,
    ``,
    `- **Individuals**: ${data.num_individuals}`,
    `- **Best Score**: ${data.best_score?.toFixed(4) ?? 'N/A'}`,
    `- **Avg Score**: ${data.avg_score?.toFixed(4) ?? 'N/A'}`,
    `- **Pareto Size**: ${data.pareto_size}`,
    `- **Total Cost**: $${data.total_cost?.toFixed(4) ?? '0'}`,
    ``,
    data.metadata ? `## Metadata\n\`\`\`json\n${JSON.stringify(data.metadata, null, 2)}\n\`\`\`` : '',
  ].join('\n');

  return {
    generation: data.generation,
    filename: `generation_${data.generation}`,
    content,
  };
}

export function getMetaPdfUrl(runId: string, generation: number): string {
  return `${API_BASE}/runs/${runId}/generations/${generation}`;
}
