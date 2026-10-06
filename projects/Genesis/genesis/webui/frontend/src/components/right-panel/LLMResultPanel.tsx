import { useGenesis } from '../../context/GenesisContext';
import './LLMResultPanel.css';

export default function LLMResultPanel() {
  const { state } = useGenesis();
  const { selectedProgram } = state;

  if (!selectedProgram) {
    return (
      <div className="llm-result-panel empty">
        <p>Select a node to view the LLM result.</p>
      </div>
    );
  }

  const llmResult = selectedProgram.llm_result;

  if (!llmResult) {
    return (
      <div className="llm-result-panel empty">
        <p>No LLM result data available for this program.</p>
      </div>
    );
  }

  return (
    <div className="llm-result-panel">
      <h4>LLM Result</h4>

      <table className="llm-result-table">
        <tbody>
          {llmResult.model && (
            <tr>
              <th>Model</th>
              <td>{llmResult.model}</td>
            </tr>
          )}
          {llmResult.prompt_tokens !== undefined && (
            <tr>
              <th>Prompt Tokens</th>
              <td>{llmResult.prompt_tokens}</td>
            </tr>
          )}
          {llmResult.completion_tokens !== undefined && (
            <tr>
              <th>Completion Tokens</th>
              <td>{llmResult.completion_tokens}</td>
            </tr>
          )}
        </tbody>
      </table>

      {llmResult.thought && (
        <div className="llm-section">
          <details className="llm-details">
            <summary className="llm-summary">Thought Process</summary>
            <div className="llm-content">
              <pre>{llmResult.thought}</pre>
            </div>
          </details>
        </div>
      )}

      {llmResult.solution && (
        <div className="llm-section">
          <details className="llm-details" open>
            <summary className="llm-summary">Solution</summary>
            <div className="llm-content">
              <pre>{llmResult.solution}</pre>
            </div>
          </details>
        </div>
      )}

      {llmResult.raw_response && (
        <div className="llm-section">
          <details className="llm-details">
            <summary className="llm-summary">Raw Response</summary>
            <div className="llm-content">
              <pre>{llmResult.raw_response}</pre>
            </div>
          </details>
        </div>
      )}
    </div>
  );
}
