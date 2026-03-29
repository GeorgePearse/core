import { useGenesis } from '../../context/GenesisContext';
import './NodeDetailsPanel.css';

export default function NodeDetailsPanel() {
  const { state } = useGenesis();
  const { selectedProgram } = state;

  if (!selectedProgram) {
    return (
      <div className="node-details-panel empty">
        <p>Select a node to view its details.</p>
      </div>
    );
  }

  const formatValue = (value: unknown): string => {
    if (value === null || value === undefined) return 'N/A';
    if (typeof value === 'number') return value.toFixed(6);
    if (typeof value === 'boolean') return value ? 'Yes' : 'No';
    if (typeof value === 'object') return JSON.stringify(value, null, 2);
    return String(value);
  };

  return (
    <div className="node-details-panel">
      <h4>Node Details: {selectedProgram.metadata.patch_name}</h4>

      <div className="details-grid">
        <div className="details-section">
          <h5>Basic Info</h5>
          <p>
            <strong>ID:</strong>{' '}
            <span className="mono">{selectedProgram.id}</span>
          </p>
          <p>
            <strong>Parent ID:</strong>{' '}
            <span className="mono">{selectedProgram.parent_id || 'None'}</span>
          </p>
          <p>
            <strong>Generation:</strong> {selectedProgram.generation}
          </p>
          <p>
            <strong>Timestamp:</strong>{' '}
            {new Date(selectedProgram.timestamp * 1000).toLocaleString()}
          </p>
          <p>
            <strong>Language:</strong> {selectedProgram.language}
          </p>
        </div>

        <div className="details-section">
          <h5>Performance</h5>
          <p>
            <strong>Combined Score:</strong>{' '}
            {formatValue(selectedProgram.combined_score)}
          </p>
          <p>
            <strong>Correct:</strong> {selectedProgram.correct ? '✓ Yes' : '✗ No'}
          </p>
          <p>
            <strong>Complexity:</strong> {formatValue(selectedProgram.complexity)}
          </p>
          <p>
            <strong>Island:</strong> {selectedProgram.island_idx ?? 'N/A'}
          </p>
        </div>

        <div className="details-section">
          <h5>Metadata</h5>
          <p>
            <strong>Patch Type:</strong> {selectedProgram.metadata.patch_type}
          </p>
          <p>
            <strong>Model:</strong> {selectedProgram.metadata.model || 'N/A'}
          </p>
          <p>
            <strong>API Cost:</strong> $
            {(selectedProgram.metadata.api_cost || 0).toFixed(4)}
          </p>
          <p>
            <strong>Embed Cost:</strong> $
            {(selectedProgram.metadata.embed_cost || 0).toFixed(4)}
          </p>
        </div>
      </div>

      {selectedProgram.public_metrics && (
        <div className="metrics-section">
          <h5>Public Metrics</h5>
          <pre>{JSON.stringify(selectedProgram.public_metrics, null, 2)}</pre>
        </div>
      )}

      {selectedProgram.text_feedback && (
        <div className="feedback-section">
          <h5>Text Feedback</h5>
          <pre>{selectedProgram.text_feedback}</pre>
        </div>
      )}
    </div>
  );
}
