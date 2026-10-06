import { useEffect, useMemo } from 'react';
import { useGenesis } from '../context/GenesisContext';
import './DatabaseSelector.css';

export default function DatabaseSelector() {
  const {
    state,
    loadDatabases,
    loadDatabase,
    refreshData,
    setAutoRefresh,
  } = useGenesis();
  const { tasksAndResults, currentDbPath, isLoading, autoRefreshEnabled } =
    state;

  // Extract current task and result from path
  const { currentTask, currentResult } = useMemo(() => {
    if (!currentDbPath) return { currentTask: '', currentResult: '' };
    const parts = currentDbPath.split('/');
    if (parts.length >= 3) {
      return {
        currentTask: parts[parts.length - 3],
        currentResult: currentDbPath,
      };
    }
    return { currentTask: '', currentResult: '' };
  }, [currentDbPath]);

  // Load databases on mount
  useEffect(() => {
    loadDatabases();
  }, [loadDatabases]);

  // Get sorted task names
  const tasks = useMemo(
    () => Object.keys(tasksAndResults).sort(),
    [tasksAndResults]
  );

  // Get results for current task
  const results = useMemo(
    () => (currentTask ? tasksAndResults[currentTask] || [] : []),
    [currentTask, tasksAndResults]
  );

  const handleTaskChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const task = e.target.value;
    if (task && tasksAndResults[task]?.length > 0) {
      // Auto-select first result
      loadDatabase(tasksAndResults[task][0].path);
    }
  };

  const handleResultChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const path = e.target.value;
    if (path) {
      loadDatabase(path);
    }
  };

  const handleRefreshFiles = () => {
    loadDatabases(true);
  };

  const handleReloadData = () => {
    refreshData();
  };

  const handleAutoRefreshToggle = () => {
    setAutoRefresh(!autoRefreshEnabled);
  };

  return (
    <div className="database-selector">
      <label>
        Task:
        <select value={currentTask} onChange={handleTaskChange}>
          <option value="">Select a task...</option>
          {tasks.map((task) => (
            <option key={task} value={task}>
              {task}
            </option>
          ))}
        </select>
      </label>

      <label>
        Result:
        <select value={currentResult} onChange={handleResultChange}>
          <option value="">Select a result...</option>
          {results.map((result) => (
            <option key={result.path} value={result.path}>
              {result.name}
            </option>
          ))}
        </select>
      </label>

      <button
        className="icon-button"
        onClick={handleRefreshFiles}
        title="Refresh available databases"
        disabled={isLoading}
      >
        🔄
      </button>

      <button
        className="icon-button reload-button"
        onClick={handleReloadData}
        title="Reload current data"
        disabled={isLoading || !currentDbPath}
      >
        📊
      </button>

      <button
        className={`icon-button auto-refresh-button ${autoRefreshEnabled ? 'active' : ''}`}
        onClick={handleAutoRefreshToggle}
        title={
          autoRefreshEnabled
            ? 'Disable auto-refresh'
            : 'Enable auto-refresh (every 3 seconds)'
        }
        disabled={!currentDbPath}
      >
        ⏱️
      </button>

      {isLoading && <span className="loading-indicator">Loading...</span>}
    </div>
  );
}
