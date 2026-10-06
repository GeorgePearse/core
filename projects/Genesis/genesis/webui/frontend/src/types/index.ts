// Program data from database
export interface Program {
  id: string;
  parent_id: string | null;
  code: string;
  language: string;
  generation: number;
  timestamp: number;
  agent_name: string;
  combined_score: number | null;
  public_metrics: Record<string, number | string> | null;
  private_metrics: Record<string, number | string> | null;
  text_feedback: string | null;
  metadata: ProgramMetadata;
  complexity: number | null;
  embedding: number[] | null;
  embedding_pca_2d: [number, number] | null;
  embedding_pca_3d: [number, number, number] | null;
  island_idx: number | null;
  correct: boolean;
  llm_result?: LLMResult | null;
  iter_id?: number;
}

export interface ProgramMetadata {
  patch_name: string;
  patch_type: 'init' | 'full' | 'diff' | 'cross' | string;
  model?: string;
  api_cost?: number;
  embed_cost?: number;
  novelty_cost?: number;
  meta_cost?: number;
  llm_result?: LLMResult;
  model_posteriors?: Record<string, number>;
  [key: string]: unknown;
}

export interface LLMResult {
  thought?: string;
  solution?: string;
  raw_response?: string;
  prompt_tokens?: number;
  completion_tokens?: number;
  model?: string;
  [key: string]: unknown;
}

// Database listing
export interface DatabaseInfo {
  path: string;
  name: string;
  actual_path?: string;
  sort_key?: string;
  stats?: {
    total: number;
    working: number;
  };
}

// Meta files
export interface MetaFile {
  generation: number;
  filename: string;
  path: string;
}

export interface MetaContent {
  generation: number;
  filename: string;
  content: string;
}

// Organized databases by task
export interface TasksAndResults {
  [taskName: string]: {
    name: string;
    path: string;
    sortKey: string;
    stats?: {
      total: number;
      working: number;
    };
  }[];
}

// Tree node for D3 visualization
export interface TreeNode extends Program {
  isUnifiedRoot?: boolean;
  isVirtual?: boolean;
}

// Sort state
export interface SortState {
  key: string;
  direction: 'asc' | 'desc';
}

// Application state
export interface AppState {
  databases: DatabaseInfo[];
  tasksAndResults: TasksAndResults;
  currentDbPath: string | null;
  programs: Program[];
  selectedProgram: Program | null;
  selectedLeftTab: string;
  selectedRightTab: string;
  isLoading: boolean;
  error: string | null;
  autoRefreshEnabled: boolean;
  selectedTask: string | null;
  selectedResult: string | null;
  isCommandMenuOpen: boolean;
}

// Computed stats
export interface EvolutionStats {
  totalGenerations: number;
  totalPrograms: number;
  correctPrograms: number;
  totalCost: number;
  avgCostPerProgram: number;
  bestScore: number;
  bestProgram: Program | null;
  costBreakdown: {
    api: number;
    embed: number;
    novelty: number;
    meta: number;
  };
}
