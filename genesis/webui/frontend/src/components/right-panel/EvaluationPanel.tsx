import { useGenesis } from '../../context/GenesisContext';
import './EvaluationPanel.css';

export default function EvaluationPanel() {
  const { state } = useGenesis();
  const { selectedProgram } = state;

  if (!selectedProgram) {
    return (
      <div className="evaluation-panel empty">
        <p>Select a node to view its evaluation logs.</p>
      </div>
    );
  }

  return (
    <div className="evaluation-panel">
      <h4>Evaluation Results</h4>

      <div className="eval-section">
        <h5>Score</h5>
        <div className="score-display">
          <span
            className={`score ${selectedProgram.correct ? 'correct' : 'incorrect'}`}
          >
            {selectedProgram.combined_score?.toFixed(6) ?? 'N/A'}
          </span>
          <span className="correctness">
            {selectedProgram.correct ? '✓ Correct' : '✗ Incorrect'}
          </span>
        </div>
      </div>

      {selectedProgram.public_metrics && (
        <div className="eval-section">
          <h5>Public Metrics</h5>
          <table className="metrics-table">
            <tbody>
              {Object.entries(selectedProgram.public_metrics).map(
                ([key, value]) => (
                  <tr key={key}>
                    <td className="metric-key">{key}</td>
                    <td className="metric-value">
                      {typeof value === 'number' ? value.toFixed(6) : String(value)}
                    </td>
                  </tr>
                )
              )}
            </tbody>
          </table>
        </div>
      )}

      {selectedProgram.private_metrics && (
        <div className="eval-section">
          <h5>Private Metrics</h5>
          <table className="metrics-table">
            <tbody>
              {Object.entries(selectedProgram.private_metrics).map(
                ([key, value]) => (
                  <tr key={key}>
                    <td className="metric-key">{key}</td>
                    <td className="metric-value">
                      {typeof value === 'number' ? value.toFixed(6) : String(value)}
                    </td>
                  </tr>
                )
              )}
            </tbody>
          </table>
        </div>
      )}

      {selectedProgram.text_feedback && (
        <div className="eval-section">
          <h5>Text Feedback</h5>
          <pre className="feedback-content">{selectedProgram.text_feedback}</pre>
        </div>
      )}
    </div>
  );
}
