import { useGenesis } from '../../context/GenesisContext';
import MetaInfoPanel from './MetaInfoPanel';
import ParetoFrontPanel from './ParetoFrontPanel';
import ScratchpadPanel from './ScratchpadPanel';
import NodeDetailsPanel from './NodeDetailsPanel';
import CodeViewerPanel from './CodeViewerPanel';
import DiffViewerPanel from './DiffViewerPanel';
import EvaluationPanel from './EvaluationPanel';
import LLMResultPanel from './LLMResultPanel';
import './RightPanel.css';

const RIGHT_TABS = [
  { id: 'meta-info', label: 'Meta' },
  { id: 'pareto-front', label: 'Pareto Front' },
  { id: 'scratchpad', label: 'Scratchpad' },
  { id: 'node-details', label: 'Node' },
  { id: 'code-viewer', label: 'Code' },
  { id: 'diff-viewer', label: 'Diff' },
  { id: 'evaluation', label: 'Evaluation' },
  { id: 'llm-result', label: 'LLM Result' },
];

export default function RightPanel() {
  const { state, setRightTab } = useGenesis();
  const { selectedRightTab, selectedProgram, programs } = state;

  const renderContent = () => {
    switch (selectedRightTab) {
      case 'meta-info':
        return <MetaInfoPanel />;
      case 'pareto-front':
        return <ParetoFrontPanel />;
      case 'scratchpad':
        return <ScratchpadPanel />;
      case 'node-details':
        return <NodeDetailsPanel />;
      case 'code-viewer':
        return <CodeViewerPanel />;
      case 'diff-viewer':
        return <DiffViewerPanel />;
      case 'evaluation':
        return <EvaluationPanel />;
      case 'llm-result':
        return <LLMResultPanel />;
      default:
        return <MetaInfoPanel />;
    }
  };

  // Show node summary if a program is selected
  const renderNodeSummary = () => {
    if (!selectedProgram) return null;

    const score =
      selectedProgram.combined_score !== null
        ? selectedProgram.combined_score.toFixed(4)
        : 'N/A';

    return (
      <div className="node-summary">
        <strong>{selectedProgram.metadata.patch_name}</strong>
        <span className="summary-item">Gen: {selectedProgram.generation}</span>
        <span className="summary-item">Score: {score}</span>
        <span
          className={`summary-item ${selectedProgram.correct ? 'correct' : 'incorrect'}`}
        >
          {selectedProgram.correct ? '✓ Correct' : '✗ Incorrect'}
        </span>
      </div>
    );
  };

  return (
    <div className="right-panel-content">
      {renderNodeSummary()}

      <div className="right-tabs">
        {RIGHT_TABS.map((tab) => (
          <button
            key={tab.id}
            className={`right-tab ${selectedRightTab === tab.id ? 'active' : ''}`}
            onClick={() => setRightTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="right-tab-content">
        {programs.length === 0 ? (
          <div className="empty-state">
            <p>Select a database to view evolution results.</p>
          </div>
        ) : (
          renderContent()
        )}
      </div>
    </div>
  );
}
