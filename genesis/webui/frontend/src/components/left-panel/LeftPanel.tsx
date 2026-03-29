import { useGenesis } from '../../context/GenesisContext';
import TreeView from './TreeView';
import ProgramsTable from './ProgramsTable';
import MetricsView from './MetricsView';
import EmbeddingsView from './EmbeddingsView';
import ClustersView from './ClustersView';
import IslandsView from './IslandsView';
import ModelPosteriorsView from './ModelPosteriorsView';
import BestPathView from './BestPathView';
import './LeftPanel.css';

const LEFT_TABS = [
  { id: 'tree-view', label: 'Tree' },
  { id: 'table-view', label: 'Programs' },
  { id: 'metrics-view', label: 'Metrics' },
  { id: 'embeddings-view', label: 'Embeddings' },
  { id: 'clusters-view', label: 'Clusters' },
  { id: 'islands-view', label: 'Islands' },
  { id: 'model-posteriors-view', label: 'LLM Posterior' },
  { id: 'best-path-view', label: 'Path → Best' },
];

export default function LeftPanel() {
  const { state, setLeftTab } = useGenesis();
  const { selectedLeftTab, programs } = state;

  const renderContent = () => {
    if (programs.length === 0) {
      return (
        <div className="empty-state">
          <p>Select a database to view evolution results.</p>
        </div>
      );
    }

    switch (selectedLeftTab) {
      case 'tree-view':
        return <TreeView />;
      case 'table-view':
        return <ProgramsTable />;
      case 'metrics-view':
        return <MetricsView />;
      case 'embeddings-view':
        return <EmbeddingsView />;
      case 'clusters-view':
        return <ClustersView />;
      case 'islands-view':
        return <IslandsView />;
      case 'model-posteriors-view':
        return <ModelPosteriorsView />;
      case 'best-path-view':
        return <BestPathView />;
      default:
        return <TreeView />;
    }
  };

  return (
    <div className="left-panel-content">
      <div className="panel-header">
        <h2 className="panel-title">
          <span className="highlight">🎏 Genesis</span>: Open-Ended Program
          Evolution 🎏
        </h2>
      </div>

      <div className="left-tabs">
        {LEFT_TABS.map((tab) => (
          <button
            key={tab.id}
            className={`left-tab ${selectedLeftTab === tab.id ? 'active' : ''}`}
            onClick={() => setLeftTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="left-tab-content">{renderContent()}</div>
    </div>
  );
}
