export interface ViewerRun {
  run_id: string;
  frame_id?: string | null;
  frame_uri: string;
  dataset_name?: string | null;
  run_label?: string | null;
  max_iters?: number | null;
  sam3_handler_name?: string | null;
  status: string;
  created_at: string;
  updated_at: string;
  last_sequence?: number | null;
  result_annotations?: string | null;
  error?: string | null;
}

export interface ViewerArtifact {
  artifact_id: string;
  artifact_kind: string;
  content_type: string;
  relative_path: string;
  width: number;
  height: number;
}

export interface ViewerEvent {
  sequence: number;
  event_type: string;
  timestamp: string;
  run_id: string;
  frame_id?: string | null;
  stage_name?: string | null;
  status?: string | null;
  message?: string | null;
  payload?: Record<string, unknown> | null;
  artifact?: ViewerArtifact | null;
}

export interface StartRunPayload {
  frame_uri: string;
  dataset_name?: string;
  run_label?: string;
  max_iters: number;
  sam3_handler_name: string;
}
