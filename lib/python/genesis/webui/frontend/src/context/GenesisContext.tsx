import {
  createContext,
  useContext,
  useReducer,
  useCallback,
  useEffect,
  useRef,
  type ReactNode,
} from 'react';
import type {
  DatabaseInfo,
  Program,
  TasksAndResults,
  AppState,
  EvolutionStats,
} from '../types';
import { listDatabases, getPrograms } from '../services/api';

// Action types
type Action =
  | { type: 'SET_DATABASES'; payload: DatabaseInfo[] }
  | { type: 'SET_TASKS_AND_RESULTS'; payload: TasksAndResults }
  | { type: 'SET_CURRENT_DB'; payload: string | null }
  | { type: 'SET_PROGRAMS'; payload: Program[] }
  | { type: 'SET_SELECTED_PROGRAM'; payload: Program | null }
  | { type: 'SET_LEFT_TAB'; payload: string }
  | { type: 'SET_RIGHT_TAB'; payload: string }
  | { type: 'SET_LOADING'; payload: boolean }
  | { type: 'SET_ERROR'; payload: string | null }
  | { type: 'SET_AUTO_REFRESH'; payload: boolean }
  | { type: 'SET_SELECTED_TASK'; payload: string | null }
  | { type: 'SET_SELECTED_RESULT'; payload: string | null }
  | { type: 'SET_COMMAND_MENU_OPEN'; payload: boolean };

const initialState: AppState = {
  databases: [],
  tasksAndResults: {},
  currentDbPath: null,
  programs: [],
  selectedProgram: null,
  selectedLeftTab: 'tree-view',
  selectedRightTab: 'meta-info',
  isLoading: false,
  error: null,
  autoRefreshEnabled: false,
  selectedTask: null,
  selectedResult: null,
  isCommandMenuOpen: false,
};

function reducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case 'SET_DATABASES':
      return { ...state, databases: action.payload };
    case 'SET_TASKS_AND_RESULTS':
      return { ...state, tasksAndResults: action.payload };
    case 'SET_CURRENT_DB':
      return { ...state, currentDbPath: action.payload };
    case 'SET_PROGRAMS':
      return { ...state, programs: action.payload };
    case 'SET_SELECTED_PROGRAM':
      return { ...state, selectedProgram: action.payload };
    case 'SET_LEFT_TAB':
      return { ...state, selectedLeftTab: action.payload };
    case 'SET_RIGHT_TAB':
      return { ...state, selectedRightTab: action.payload };
    case 'SET_LOADING':
      return { ...state, isLoading: action.payload };
    case 'SET_ERROR':
      return { ...state, error: action.payload };
    case 'SET_AUTO_REFRESH':
      return { ...state, autoRefreshEnabled: action.payload };
    case 'SET_SELECTED_TASK':
      return { ...state, selectedTask: action.payload, selectedResult: null };
    case 'SET_SELECTED_RESULT':
      return { ...state, selectedResult: action.payload };
    case 'SET_COMMAND_MENU_OPEN':
      return { ...state, isCommandMenuOpen: action.payload };
    default:
      return state;
  }
}

// Helper to organize databases by task
function organizeDatabases(dbs: DatabaseInfo[]): TasksAndResults {
  const tasksAndResults: TasksAndResults = {};

  dbs.forEach((db) => {
    const pathParts = db.path.split('/');
    if (pathParts.length >= 3) {
      const task = pathParts[pathParts.length - 3];
      const result = pathParts[pathParts.length - 2];

      if (!tasksAndResults[task]) {
        tasksAndResults[task] = [];
      }

      tasksAndResults[task].push({
        name: result,
        path: db.path,
        sortKey: db.sort_key || '0',
        stats: db.stats,
      });
    }
  });

  // Sort results within each task by date (newest first)
  Object.keys(tasksAndResults).forEach((task) => {
    tasksAndResults[task].sort((a, b) => b.sortKey.localeCompare(a.sortKey));
  });

  return tasksAndResults;
}

// Compute evolution stats
function computeStats(programs: Program[]): EvolutionStats {
  const correctPrograms = programs.filter((p) => p.correct);
  const generations = [...new Set(programs.map((p) => p.generation))];

  let totalApiCost = 0;
  let totalEmbedCost = 0;
  let totalNoveltyCost = 0;
  let totalMetaCost = 0;

  programs.forEach((p) => {
    totalApiCost += p.metadata.api_cost || 0;
    totalEmbedCost += p.metadata.embed_cost || 0;
    totalNoveltyCost += p.metadata.novelty_cost || 0;
    totalMetaCost += p.metadata.meta_cost || 0;
  });

  const totalCost =
    totalApiCost + totalEmbedCost + totalNoveltyCost + totalMetaCost;

  // Find best program (correct only)
  let bestProgram: Program | null = null;
  let bestScore = -Infinity;
  correctPrograms.forEach((p) => {
    if (p.combined_score !== null && p.combined_score > bestScore) {
      bestScore = p.combined_score;
      bestProgram = p;
    }
  });

  return {
    totalGenerations: generations.length,
    totalPrograms: programs.length,
    correctPrograms: correctPrograms.length,
    totalCost,
    avgCostPerProgram: programs.length > 0 ? totalCost / programs.length : 0,
    bestScore: bestScore === -Infinity ? 0 : bestScore,
    bestProgram,
    costBreakdown: {
      api: totalApiCost,
      embed: totalEmbedCost,
      novelty: totalNoveltyCost,
      meta: totalMetaCost,
    },
  };
}

// Context value type
interface GenesisContextValue {
  state: AppState;
  stats: EvolutionStats;
  dispatch: React.Dispatch<Action>;
  loadDatabases: (force?: boolean) => Promise<void>;
  loadDatabase: (dbPath: string) => Promise<void>;
  loadPrograms: (dbPath: string) => Promise<void>;
  selectProgram: (program: Program | null) => void;
  setLeftTab: (tab: string) => void;
  setRightTab: (tab: string) => void;
  setAutoRefresh: (enabled: boolean) => void;
  refreshData: () => Promise<void>;
  setCommandMenuOpen: (open: boolean) => void;
}

const GenesisContext = createContext<GenesisContextValue | null>(null);

export function GenesisProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState);
  const autoRefreshRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stats = computeStats(state.programs);

  const loadDatabases = useCallback(async (_force = false) => {
    dispatch({ type: 'SET_LOADING', payload: true });
    dispatch({ type: 'SET_ERROR', payload: null });

    try {
      const dbs = await listDatabases();
      dispatch({ type: 'SET_DATABASES', payload: dbs });
      dispatch({
        type: 'SET_TASKS_AND_RESULTS',
        payload: organizeDatabases(dbs),
      });
    } catch (error) {
      dispatch({
        type: 'SET_ERROR',
        payload: error instanceof Error ? error.message : 'Unknown error',
      });
    } finally {
      dispatch({ type: 'SET_LOADING', payload: false });
    }
  }, []);

  const loadDatabase = useCallback(async (dbPath: string) => {
    dispatch({ type: 'SET_LOADING', payload: true });
    dispatch({ type: 'SET_ERROR', payload: null });
    dispatch({ type: 'SET_CURRENT_DB', payload: dbPath });

    try {
      const programs = await getPrograms(dbPath);
      console.log(`Loaded ${programs.length} programs from ${dbPath}`);
      if (programs.length > 0) {
        console.log('Sample program embedding:', programs[0].embedding ? 'Present' : 'Missing');
        console.log('Sample program PCA:', programs[0].embedding_pca_2d ? 'Present' : 'Missing');
      }
      // Sort by generation and timestamp
      programs.sort((a, b) => {
        if (a.generation !== b.generation)
          return a.generation - b.generation;
        return a.timestamp - b.timestamp;
      });
      // Add iter_id
      const genCounters: Record<number, number> = {};
      programs.forEach((p) => {
        if (!genCounters[p.generation]) genCounters[p.generation] = 0;
        p.iter_id = genCounters[p.generation]++;
      });
      dispatch({ type: 'SET_PROGRAMS', payload: programs });
    } catch (error) {
      dispatch({
        type: 'SET_ERROR',
        payload: error instanceof Error ? error.message : 'Unknown error',
      });
    } finally {
      dispatch({ type: 'SET_LOADING', payload: false });
    }
  }, []);

  const selectProgram = useCallback((program: Program | null) => {
    dispatch({ type: 'SET_SELECTED_PROGRAM', payload: program });
  }, []);

  const setLeftTab = useCallback((tab: string) => {
    dispatch({ type: 'SET_LEFT_TAB', payload: tab });
  }, []);

  const setRightTab = useCallback((tab: string) => {
    dispatch({ type: 'SET_RIGHT_TAB', payload: tab });
  }, []);

  const refreshData = useCallback(async () => {
    if (state.currentDbPath) {
      await loadDatabase(state.currentDbPath);
    }
  }, [state.currentDbPath, loadDatabase]);

  const setAutoRefresh = useCallback(
    (enabled: boolean) => {
      dispatch({ type: 'SET_AUTO_REFRESH', payload: enabled });
      if (enabled && state.currentDbPath) {
        if (autoRefreshRef.current) {
          clearInterval(autoRefreshRef.current);
        }
        autoRefreshRef.current = setInterval(refreshData, 3000);
      } else if (autoRefreshRef.current) {
        clearInterval(autoRefreshRef.current);
        autoRefreshRef.current = null;
      }
    },
    [state.currentDbPath, refreshData]
  );

  const setCommandMenuOpen = useCallback((open: boolean) => {
    dispatch({ type: 'SET_COMMAND_MENU_OPEN', payload: open });
  }, []);

  // Cleanup auto-refresh on unmount
  useEffect(() => {
    return () => {
      if (autoRefreshRef.current) {
        clearInterval(autoRefreshRef.current);
      }
    };
  }, []);

  // Auto-load first database on mount
  useEffect(() => {
    let mounted = true;
    
    const autoLoad = async () => {
      if (!mounted) return;
      
      try {
        console.log('🔄 Auto-loading databases...');
        const dbs = await listDatabases();
        
        if (!mounted || dbs.length === 0) {
          console.log('⚠️  No databases found');
          return;
        }
        
        console.log(`✅ Found ${dbs.length} databases`);
        
        if (!mounted) return;
        dispatch({ type: 'SET_DATABASES', payload: dbs });
        dispatch({
          type: 'SET_TASKS_AND_RESULTS',
          payload: organizeDatabases(dbs),
        });
        
        // Auto-select the first database (most recent)
        const firstDb = dbs[0];
        console.log(`🎯 Auto-loading database: ${firstDb.name}`);
        
        if (!mounted) return;
        dispatch({ type: 'SET_CURRENT_DB', payload: firstDb.path });
        dispatch({ type: 'SET_LOADING', payload: true });
        
        // Load programs for the first database
        const programs = await getPrograms(firstDb.path);
        console.log(`📦 Loaded ${programs.length} programs`);
        
        if (!mounted) return;
        
        // Sort by generation and timestamp
        programs.sort((a, b) => {
          if (a.generation !== b.generation)
            return a.generation - b.generation;
          return a.timestamp - b.timestamp;
        });
        
        // Add iter_id
        const genCounters: Record<number, number> = {};
        programs.forEach((p) => {
          if (!genCounters[p.generation]) genCounters[p.generation] = 0;
          p.iter_id = genCounters[p.generation]++;
        });
        
        dispatch({ type: 'SET_PROGRAMS', payload: programs });
        dispatch({ type: 'SET_LOADING', payload: false });
        
        console.log('✅ Database auto-loaded successfully');
      } catch (error) {
        console.error('❌ Failed to auto-load database:', error);
        if (mounted) {
          dispatch({
            type: 'SET_ERROR',
            payload: error instanceof Error ? error.message : 'Failed to load database',
          });
          dispatch({ type: 'SET_LOADING', payload: false });
        }
      }
    };
    
    autoLoad();
    
    return () => {
      mounted = false;
    };
  }, []); // Run only once on mount

  return (
    <GenesisContext.Provider
      value={{
        state,
        stats,
        dispatch,
        loadDatabases,
        loadDatabase,
        loadPrograms: loadDatabase,
        selectProgram,
        setLeftTab,
        setRightTab,
        setAutoRefresh,
        refreshData,
        setCommandMenuOpen,
      }}
    >
      {children}
    </GenesisContext.Provider>
  );
}

export function useGenesis() {
  const context = useContext(GenesisContext);
  if (!context) {
    throw new Error('useGenesis must be used within a GenesisProvider');
  }
  return context;
}
