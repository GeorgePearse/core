import { useState, useRef, useEffect, useCallback } from 'react';
import { Database } from 'lucide-react';
import { useGenesis } from '../context/GenesisContext';

// Import existing panel components
import TreeView from './left-panel/TreeView';
import ProgramsTable from './left-panel/ProgramsTable';
import MetricsView from './left-panel/MetricsView';
import EmbeddingsView from './left-panel/EmbeddingsView';
import ClustersView from './left-panel/ClustersView';
import IslandsView from './left-panel/IslandsView';
import ModelPosteriorsView from './left-panel/ModelPosteriorsView';
import BestPathView from './left-panel/BestPathView';
import MetaInfoPanel from './right-panel/MetaInfoPanel';
import ParetoFrontPanel from './right-panel/ParetoFrontPanel';
import ScratchpadPanel from './right-panel/ScratchpadPanel';
import NodeDetailsPanel from './right-panel/NodeDetailsPanel';
import CodeViewerPanel from './right-panel/CodeViewerPanel';
import DiffViewerPanel from './right-panel/DiffViewerPanel';
import EvaluationPanel from './right-panel/EvaluationPanel';
import LLMResultPanel from './right-panel/LLMResultPanel';

// Tabs that show a split view with a right panel
const SPLIT_VIEW_TABS = [
  'tree-view',
  'table-view',
  'metrics-view',
  'embeddings-view',
  'clusters-view',
  'islands-view',
  'model-posteriors-view',
  'best-path-view'
];

// Right panel tab options
const RIGHT_TABS = [
  { id: 'code-viewer', label: 'Code' },
  { id: 'diff-viewer', label: 'Diff' },
  { id: 'node-details', label: 'Node' },
  { id: 'evaluation', label: 'Eval' },
  { id: 'llm-result', label: 'LLM' },
];

// Tab label mapping
const TAB_LABELS: Record<string, string> = {
  'tree-view': 'Tree',
  'table-view': 'Programs',
  'metrics-view': 'Metrics',
  'embeddings-view': 'Embeddings',
  'clusters-view': 'Clusters',
  'islands-view': 'Islands',
  'model-posteriors-view': 'LLM Posterior',
  'best-path-view': 'Path → Best',
  'meta-info': 'Meta',
  'pareto-front': 'Pareto Front',
  'scratchpad': 'Scratchpad',
  'node-details': 'Node',
  'code-viewer': 'Code',
  'diff-viewer': 'Diff',
  'evaluation': 'Evaluation',
  'llm-result': 'LLM Result'
};

// Min/max constraints for the right panel
const MIN_RIGHT_PANEL_WIDTH = 300;
const MAX_RIGHT_PANEL_WIDTH = 1200;
const DEFAULT_RIGHT_PANEL_WIDTH = 500;

export default function MainContent() {
  const { state, setRightTab, selectProgram: setProgram } = useGenesis();
  const { selectedLeftTab: activeTab, selectedRightTab, selectedProgram } = state;

  // Resizable panel state
  const [rightPanelWidth, setRightPanelWidth] = useState(() => {
    const saved = localStorage.getItem('rightPanelWidth');
    return saved ? parseInt(saved, 10) : DEFAULT_RIGHT_PANEL_WIDTH;
  });
  const [isDragging, setIsDragging] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Save panel width to localStorage when it changes
  useEffect(() => {
    localStorage.setItem('rightPanelWidth', rightPanelWidth.toString());
  }, [rightPanelWidth]);

  // Handle mouse move during drag
  const handleMouseMove = useCallback((e: MouseEvent) => {
    if (!isDragging || !containerRef.current) return;

    const containerRect = containerRef.current.getBoundingClientRect();
    const newWidth = containerRect.right - e.clientX;
    
    // Debug logging
    // console.log('Drag:', { 
    //   clientX: e.clientX, 
    //   containerRight: containerRect.right, 
    //   newWidth, 
    //   clamped: Math.max(MIN_RIGHT_PANEL_WIDTH, Math.min(MAX_RIGHT_PANEL_WIDTH, newWidth)) 
    // });

    // Clamp to min/max
    const clampedWidth = Math.max(MIN_RIGHT_PANEL_WIDTH, Math.min(MAX_RIGHT_PANEL_WIDTH, newWidth));
    setRightPanelWidth(clampedWidth);
  }, [isDragging]);

  // Handle mouse up to stop dragging
  const handleMouseUp = useCallback(() => {
    setIsDragging(false);
  }, []);

  // Add/remove global mouse listeners for dragging
  useEffect(() => {
    if (isDragging) {
      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';
    } else {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    }

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
  }, [isDragging, handleMouseMove, handleMouseUp]);

  // Start dragging
  const handleDividerMouseDown = (e: React.MouseEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  // Double-click to reset to default
  const handleDividerDoubleClick = () => {
    setRightPanelWidth(DEFAULT_RIGHT_PANEL_WIDTH);
  };

  // Maximize code view state
  const [isMaximized, setIsMaximized] = useState(false);

  const renderLeftPanel = () => {
    switch (activeTab) {
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

  const renderRightPanel = () => {
    switch (selectedRightTab) {
      case 'code-viewer':
        return <CodeViewerPanel />;
      case 'diff-viewer':
        return <DiffViewerPanel />;
      case 'node-details':
        return <NodeDetailsPanel />;
      case 'evaluation':
        return <EvaluationPanel />;
      case 'llm-result':
        return <LLMResultPanel />;
      default:
        return <CodeViewerPanel />;
    }
  };

  const renderSinglePanel = () => {
    switch (activeTab) {
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
        return null;
    }
  };

  // Check if we should be in maximized code view mode
  // This happens when a user selects a program while in the 'table-view' (Programs) tab
  useEffect(() => {
    if (activeTab === 'table-view' && selectedProgram) {
      setIsMaximized(true);
    } else if (!selectedProgram) {
      setIsMaximized(false);
    }
  }, [activeTab, selectedProgram]);

  // Handle exiting maximized view
  const exitMaximized = () => {
    setProgram(null);
    setIsMaximized(false);
  };

  // If no data loaded, show empty state
  if (state.programs.length === 0) {
    return (
      <div className="flex-1 flex flex-col">
        <div className="bg-gray-900 border-b border-gray-800 px-6 py-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-medium text-white">{TAB_LABELS[activeTab] || activeTab}</h2>
            <div className="flex items-center gap-2">
              <button className="px-3 py-1.5 text-sm text-gray-400 hover:text-white hover:bg-gray-800 rounded transition-colors">
                Export
              </button>
              <button className="px-3 py-1.5 text-sm text-gray-400 hover:text-white hover:bg-gray-800 rounded transition-colors">
                Settings
              </button>
            </div>
          </div>
        </div>
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center max-w-md">
            <div className="mb-6 p-8 bg-gray-900 rounded-lg border border-gray-800">
              <Database className="w-16 h-16 text-gray-600 mx-auto mb-4" />
              <h3 className="text-lg font-medium text-gray-300 mb-2">
                No Database Selected
              </h3>
              <p className="text-sm text-gray-500 mb-6">
                Select a database to view evolution results and begin analysis.
              </p>
              <button className="px-5 py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded font-medium text-sm transition-colors">
                Load Database
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ... (existing check for SPLIT_VIEW_TABS)

  // Maximized View Layout
  if (isMaximized && activeTab === 'table-view' && selectedProgram) {
    return (
      <div className="flex-1 flex flex-col h-full bg-gray-950">
        <div className="bg-gray-900 border-b border-gray-800 px-4 py-3 flex items-center gap-4">
          <button
            onClick={exitMaximized}
            className="flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-gray-300 hover:text-white bg-gray-800 hover:bg-gray-700 rounded-md transition-colors"
          >
            ← Back to Programs
          </button>
          <div className="h-6 w-px bg-gray-700 mx-2" />
          <div className="flex items-center gap-3 text-sm">
            <span className="font-medium text-white">
              {selectedProgram.metadata.patch_name || `Program ${selectedProgram.id}`}
            </span>
            <span className="text-gray-500">Gen {selectedProgram.generation}</span>
            <span className="text-orange-400">
              {selectedProgram.combined_score?.toFixed(4) ?? 'N/A'}
            </span>
          </div>
        </div>
        
        <div className="flex-1 overflow-hidden p-4">
          <CodeViewerPanel />
        </div>
      </div>
    );
  }
  const isSplitView = SPLIT_VIEW_TABS.includes(activeTab);

  if (!isSplitView) {
    return (
      <div className="flex-1 flex flex-col">
        <div className="bg-gray-900 border-b border-gray-800 px-6 py-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-medium text-white">{TAB_LABELS[activeTab] || activeTab}</h2>
            <div className="flex items-center gap-2">
              <button className="px-3 py-1.5 text-sm text-gray-400 hover:text-white hover:bg-gray-800 rounded transition-colors">
                Export
              </button>
              <button className="px-3 py-1.5 text-sm text-gray-400 hover:text-white hover:bg-gray-800 rounded transition-colors">
                Settings
              </button>
            </div>
          </div>
        </div>
        <div className="flex-1 p-8 overflow-auto">{renderSinglePanel()}</div>
      </div>
    );
  }

  // Split view layout
  return (
    <div className="flex-1 flex flex-col">
      {/* Content Header */}
      <div className="bg-gray-900 border-b border-gray-800 px-6 py-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-medium text-white">{TAB_LABELS[activeTab] || activeTab}</h2>
          <div className="flex items-center gap-2">
            <button className="px-3 py-1.5 text-sm text-gray-400 hover:text-white hover:bg-gray-800 rounded transition-colors">
              Export
            </button>
            <button className="px-3 py-1.5 text-sm text-gray-400 hover:text-white hover:bg-gray-800 rounded transition-colors">
              Settings
            </button>
          </div>
        </div>
      </div>

      {/* Split Content Area */}
      <div ref={containerRef} className="flex-1 flex overflow-hidden">
        {/* Left Panel - Main View */}
        <div className="flex-1 p-6 overflow-auto min-w-0">
          {renderLeftPanel()}
        </div>

        {/* Resizable Divider */}
        <div
          onMouseDown={handleDividerMouseDown}
          onDoubleClick={handleDividerDoubleClick}
          className={`w-1 bg-gray-800 hover:bg-blue-500 cursor-col-resize transition-colors flex-shrink-0 group relative z-10 ${
            isDragging ? 'bg-blue-500' : ''
          }`}
          title="Drag to resize, double-click to reset"
        >
          {/* Visual indicator for drag handle */}
          <div className="absolute inset-y-0 -left-1 -right-1 group-hover:bg-blue-500/20" />
        </div>

        {/* Right Panel - Code/Details View */}
        <div
          style={{ width: rightPanelWidth }}
          className={`flex flex-col bg-gray-950 flex-shrink-0 transition-[width] duration-0 ${isDragging ? 'pointer-events-none select-none' : ''}`}
        >
          {/* Right Panel Header with Node Info */}
          {selectedProgram && (
            <div className="px-4 py-3 bg-gray-900 border-b border-gray-800">
              <div className="flex items-center gap-3 text-sm">
                <span className="font-medium text-white">
                  {selectedProgram.metadata.patch_name || `Program ${selectedProgram.id}`}
                </span>
                <span className="text-gray-500">Gen {selectedProgram.generation}</span>
                <span className="text-orange-400">
                  {selectedProgram.combined_score?.toFixed(4) ?? 'N/A'}
                </span>
                <span className={selectedProgram.correct ? 'text-green-400' : 'text-red-400'}>
                  {selectedProgram.correct ? 'Correct' : 'Incorrect'}
                </span>
              </div>
            </div>
          )}

          {/* Right Panel Tabs */}
          <div className="flex border-b border-gray-800 bg-gray-900">
            {RIGHT_TABS.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setRightTab(tab.id)}
                className={`px-4 py-2.5 text-sm font-medium transition-colors ${
                  selectedRightTab === tab.id
                    ? 'text-white border-b-2 border-blue-500 bg-gray-800'
                    : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Right Panel Content */}
          <div className="flex-1 overflow-auto p-4">
            {renderRightPanel()}
          </div>
        </div>
      </div>
    </div>
  );
}
