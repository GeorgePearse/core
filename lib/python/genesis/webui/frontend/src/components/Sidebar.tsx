import { useState, useEffect } from 'react';
import {
  ChevronDown,
  Code2,
  GitBranch,
  Activity,
  Layers,
  Globe,
  Route,
  Database,
  Cpu,
  FileCode,
  GitCompare,
  BarChart3,
  Brain,
  Search,
  Zap,
} from 'lucide-react';
import { useGenesis } from '../context/GenesisContext';

const analysisOptions = [
  { id: 'tree-view', label: 'Tree', icon: GitBranch },
  { id: 'table-view', label: 'Programs', icon: Code2 },
  { id: 'metrics-view', label: 'Metrics', icon: BarChart3 },
  { id: 'embeddings-view', label: 'Embeddings', icon: Layers },
  { id: 'clusters-view', label: 'Clusters', icon: Activity },
  { id: 'islands-view', label: 'Islands', icon: Globe },
  { id: 'model-posteriors-view', label: 'LLM Posterior', icon: Brain },
  { id: 'best-path-view', label: 'Path → Best', icon: Route },
];

const viewOptions = [
  { id: 'meta-info', label: 'Meta', icon: Database },
  { id: 'pareto-front', label: 'Pareto Front', icon: Activity },
  { id: 'scratchpad', label: 'Scratchpad', icon: FileCode },
  { id: 'node-details', label: 'Node', icon: Cpu },
  { id: 'code-viewer', label: 'Code', icon: Code2 },
  { id: 'diff-viewer', label: 'Diff', icon: GitCompare },
  { id: 'evaluation', label: 'Evaluation', icon: BarChart3 },
  { id: 'llm-result', label: 'LLM Result', icon: Brain },
];

export default function Sidebar() {
  const { state, dispatch, loadDatabase, setLeftTab, setCommandMenuOpen } = useGenesis();
  const [analysisOpen, setAnalysisOpen] = useState(true);
  const [viewOpen, setViewOpen] = useState(true);
  const [taskOpen, setTaskOpen] = useState(false);
  const [resultOpen, setResultOpen] = useState(false);

  const activeTab = state.selectedLeftTab;

  const tasks = Object.keys(state.tasksAndResults).sort();
  const results = state.selectedTask
    ? state.tasksAndResults[state.selectedTask] || []
    : [];

  // Load database when both task and result are selected
  useEffect(() => {
    if (state.selectedTask && state.selectedResult) {
      const result = results.find((r) => r.name === state.selectedResult);
      if (result) {
        loadDatabase(result.path);
      }
    }
  }, [state.selectedTask, state.selectedResult, results, loadDatabase]);

  const handleTaskSelect = (task: string) => {
    dispatch({ type: 'SET_SELECTED_TASK', payload: task });
    setTaskOpen(false);
    // Auto-select first result if available
    const taskResults = state.tasksAndResults[task] || [];
    if (taskResults.length > 0) {
      dispatch({ type: 'SET_SELECTED_RESULT', payload: taskResults[0].name });
    }
  };

  const handleResultSelect = (resultName: string) => {
    dispatch({ type: 'SET_SELECTED_RESULT', payload: resultName });
    setResultOpen(false);
  };

  return (
    <div className="w-72 bg-gray-900 border-r border-gray-800 flex flex-col h-full">
      {/* Logo/Title */}
      <div className="px-5 py-5 border-b border-gray-800 flex-shrink-0">
        <div className="flex items-center gap-3 mb-2">
          <div className="p-2 bg-blue-600 rounded-lg">
            <Zap className="w-5 h-5 text-white" />
          </div>
          <h1 className="text-xl font-semibold text-white">Genesis</h1>
        </div>
        <p className="text-sm text-gray-500">Open-Ended Program Evolution</p>
      </div>

      {/* Task and Result Dropdowns */}
      <div className="px-5 py-4 space-y-3 border-b border-gray-800 flex-shrink-0">
        {/* Task Dropdown */}
        <div className="space-y-1.5">
          <label className="text-xs font-medium text-gray-500 uppercase tracking-wider">
            Task
          </label>
          <div className="relative">
            <button
              onClick={() => setTaskOpen(!taskOpen)}
              className="w-full flex items-center justify-between px-3 py-2 bg-gray-800 hover:bg-gray-750 transition-colors rounded-lg border border-gray-700"
            >
              <span className="text-sm text-gray-300 truncate">
                {state.selectedTask || 'Select a task...'}
              </span>
              <ChevronDown className="w-4 h-4 text-gray-500 flex-shrink-0 ml-2" />
            </button>
            {taskOpen && tasks.length > 0 && (
              <div className="absolute z-10 w-full mt-1 bg-gray-800 rounded-lg border border-gray-700 max-h-48 overflow-y-auto shadow-lg">
                {tasks.map((task) => (
                  <button
                    key={task}
                    onClick={() => handleTaskSelect(task)}
                    className={`w-full px-3 py-2 text-left text-sm hover:bg-gray-700 first:rounded-t-lg last:rounded-b-lg flex justify-between items-center ${
                      state.selectedTask === task
                        ? 'bg-gray-700 text-white'
                        : 'text-gray-400'
                    }`}
                  >
                    <span className="truncate">{task}</span>
                    <span className="text-xs opacity-50 ml-2">
                      {state.tasksAndResults[task]?.length || 0}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Result Dropdown */}
        <div className="space-y-1.5">
          <label className="text-xs font-medium text-gray-500 uppercase tracking-wider">
            Result
          </label>
          <div className="relative">
            <button
              onClick={() => setResultOpen(!resultOpen)}
              className="w-full flex items-center justify-between px-3 py-2 bg-gray-800 hover:bg-gray-750 transition-colors rounded-lg border border-gray-700"
            >
              <span className="text-sm text-gray-300 truncate">
                {state.selectedResult || 'Select a result...'}
              </span>
              <ChevronDown className="w-4 h-4 text-gray-500 flex-shrink-0 ml-2" />
            </button>
            {resultOpen && results.length > 0 && (
              <div className="absolute z-10 w-full mt-1 bg-gray-800 rounded-lg border border-gray-700 max-h-48 overflow-y-auto shadow-lg">
                {results.map((result) => (
                  <button
                    key={result.path}
                    onClick={() => handleResultSelect(result.name)}
                    className={`w-full px-3 py-2 text-left text-sm hover:bg-gray-700 first:rounded-t-lg last:rounded-b-lg flex justify-between items-center ${
                      state.selectedResult === result.name
                        ? 'bg-gray-700 text-white'
                        : 'text-gray-400'
                    }`}
                  >
                    <span className="truncate flex-1 mr-2">{result.name}</span>
                    {result.stats && (
                      <span className="text-xs opacity-50 font-mono">
                        ({result.stats.working}/{result.stats.total})
                      </span>
                    )}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Search Button */}
        <button 
          onClick={() => setCommandMenuOpen(true)}
          className="w-full flex items-center justify-center gap-2 px-3 py-2 bg-blue-600 hover:bg-blue-700 transition-colors rounded-lg text-sm font-medium"
        >
          <Search className="w-4 h-4" />
          Search
        </button>
      </div>

      {/* Navigation Sections - Scrollable area that fills remaining space */}
      <div className="flex-1 overflow-y-auto">
        {/* Analysis Section */}
        <div className="px-4 pt-4 pb-2">
          <button
            onClick={() => setAnalysisOpen(!analysisOpen)}
            className="flex items-center justify-between w-full text-left hover:bg-gray-800 px-2 py-1.5 rounded-lg transition-colors"
          >
            <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
              Analysis
            </span>
            <ChevronDown
              className={`w-4 h-4 text-gray-500 transition-transform ${
                analysisOpen ? '' : '-rotate-90'
              }`}
            />
          </button>
          {analysisOpen && (
            <div className="mt-2 space-y-1">
              {analysisOptions.map((option) => {
                const Icon = option.icon;
                return (
                  <button
                    key={option.id}
                    onClick={() => setLeftTab(option.id)}
                    className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors ${
                      activeTab === option.id
                        ? 'bg-blue-600 text-white'
                        : 'hover:bg-gray-800 text-gray-400 hover:text-gray-200'
                    }`}
                  >
                    <Icon className="w-4 h-4 flex-shrink-0" />
                    <span className="text-sm">{option.label}</span>
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* View Options Section */}
        <div className="px-4 pt-2 pb-4">
          <button
            onClick={() => setViewOpen(!viewOpen)}
            className="flex items-center justify-between w-full text-left hover:bg-gray-800 px-2 py-1.5 rounded-lg transition-colors"
          >
            <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
              View Options
            </span>
            <ChevronDown
              className={`w-4 h-4 text-gray-500 transition-transform ${
                viewOpen ? '' : '-rotate-90'
              }`}
            />
          </button>
          {viewOpen && (
            <div className="mt-2 space-y-1">
              {viewOptions.map((option) => {
                const Icon = option.icon;
                return (
                  <button
                    key={option.id}
                    onClick={() => setLeftTab(option.id)}
                    className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors ${
                      activeTab === option.id
                        ? 'bg-blue-600 text-white'
                        : 'hover:bg-gray-800 text-gray-400 hover:text-gray-200'
                    }`}
                  >
                    <Icon className="w-4 h-4 flex-shrink-0" />
                    <span className="text-sm">{option.label}</span>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* Status Bar - Always at bottom */}
      <div className="px-5 py-3 border-t border-gray-800 flex-shrink-0">
        <div className="flex items-center justify-between mb-1">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 bg-green-500 rounded-full"></div>
            <span className="text-xs text-gray-500">Connected</span>
          </div>
          <span className="text-xs text-gray-600">v1.0.0</span>
        </div>
        <div className="text-xs text-gray-600">
          Engine: Active &bull; LLM: Ready
        </div>
      </div>
    </div>
  );
}
