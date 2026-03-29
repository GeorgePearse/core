import { useEffect } from 'react';
import { useGenesis } from '../context/GenesisContext';
import { 
  Calculator, 
  Code, 
  FileText, 
  GitBranch, 
  GitGraph, 
  Layout, 
  RefreshCw, 
  Database,
  Activity,
  Map as MapIcon,
  BarChart2,
  Cpu,
  Zap,
  CheckCircle,
  FileDiff,
  Terminal,
  Brain,
  History
} from 'lucide-react';
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandShortcut,
} from "@/components/ui/command"

export default function CommandMenu() {
  const { 
    state, 
    loadDatabase, 
    setLeftTab, 
    setRightTab, 
    refreshData, 
    setAutoRefresh,
    setCommandMenuOpen
  } = useGenesis();
  
  const open = state.isCommandMenuOpen;

  // Toggle the menu when ⌘K is pressed
  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.key === 'k' && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setCommandMenuOpen(!open);
      }
    };

    document.addEventListener('keydown', down);
    return () => document.removeEventListener('keydown', down);
  }, [open, setCommandMenuOpen]);

  const runCommand = (command: () => void) => {
    command();
    setCommandMenuOpen(false);
  };

  return (
    <CommandDialog open={open} onOpenChange={setCommandMenuOpen}>
      <CommandInput placeholder="Type a command or search..." />
      <CommandList>
        <CommandEmpty>No results found.</CommandEmpty>

        <CommandGroup heading="Left Panel Views">
          <CommandItem value="tree-view" onSelect={() => runCommand(() => setLeftTab('tree-view'))}>
            <GitGraph className="mr-2 h-4 w-4" />
            <span>Tree View</span>
          </CommandItem>
          <CommandItem value="table-view" onSelect={() => runCommand(() => setLeftTab('table-view'))}>
            <Layout className="mr-2 h-4 w-4" />
            <span>Programs Table</span>
          </CommandItem>
          <CommandItem value="metrics-view" onSelect={() => runCommand(() => setLeftTab('metrics-view'))}>
            <BarChart2 className="mr-2 h-4 w-4" />
            <span>Metrics</span>
          </CommandItem>
          <CommandItem value="embeddings-view" onSelect={() => runCommand(() => setLeftTab('embeddings-view'))}>
            <Cpu className="mr-2 h-4 w-4" />
            <span>Embeddings</span>
          </CommandItem>
          <CommandItem value="clusters-view" onSelect={() => runCommand(() => setLeftTab('clusters-view'))}>
            <Activity className="mr-2 h-4 w-4" />
            <span>Clusters</span>
          </CommandItem>
          <CommandItem value="islands-view" onSelect={() => runCommand(() => setLeftTab('islands-view'))}>
            <MapIcon className="mr-2 h-4 w-4" />
            <span>Islands</span>
          </CommandItem>
          <CommandItem value="model-posteriors-view" onSelect={() => runCommand(() => setLeftTab('model-posteriors-view'))}>
            <Brain className="mr-2 h-4 w-4" />
            <span>LLM Posteriors</span>
          </CommandItem>
          <CommandItem value="best-path-view" onSelect={() => runCommand(() => setLeftTab('best-path-view'))}>
            <History className="mr-2 h-4 w-4" />
            <span>Path to Best</span>
          </CommandItem>
        </CommandGroup>

        <CommandGroup heading="Right Panel Views">
          <CommandItem value="meta-info" onSelect={() => runCommand(() => setRightTab('meta-info'))}>
            <FileText className="mr-2 h-4 w-4" />
            <span>Meta Info</span>
          </CommandItem>
          <CommandItem value="pareto-front" onSelect={() => runCommand(() => setRightTab('pareto-front'))}>
            <GitBranch className="mr-2 h-4 w-4" />
            <span>Pareto Front</span>
          </CommandItem>
          <CommandItem value="scratchpad" onSelect={() => runCommand(() => setRightTab('scratchpad'))}>
            <Terminal className="mr-2 h-4 w-4" />
            <span>Scratchpad</span>
          </CommandItem>
          <CommandItem value="node-details" onSelect={() => runCommand(() => setRightTab('node-details'))}>
            <CheckCircle className="mr-2 h-4 w-4" />
            <span>Node Details</span>
          </CommandItem>
          <CommandItem value="code-viewer" onSelect={() => runCommand(() => setRightTab('code-viewer'))}>
            <Code className="mr-2 h-4 w-4" />
            <span>Code Viewer</span>
          </CommandItem>
          <CommandItem value="diff-viewer" onSelect={() => runCommand(() => setRightTab('diff-viewer'))}>
            <FileDiff className="mr-2 h-4 w-4" />
            <span>Diff Viewer</span>
          </CommandItem>
          <CommandItem value="evaluation" onSelect={() => runCommand(() => setRightTab('evaluation'))}>
            <Calculator className="mr-2 h-4 w-4" />
            <span>Evaluation Results</span>
          </CommandItem>
          <CommandItem value="llm-result" onSelect={() => runCommand(() => setRightTab('llm-result'))}>
            <Brain className="mr-2 h-4 w-4" />
            <span>LLM Output</span>
          </CommandItem>
        </CommandGroup>

        <CommandGroup heading="Actions">
          <CommandItem value="refresh-data" onSelect={() => runCommand(() => refreshData())}>
            <RefreshCw className="mr-2 h-4 w-4" />
            <span>Refresh Data</span>
            <CommandShortcut>R</CommandShortcut>
          </CommandItem>
          <CommandItem value="toggle-auto-refresh" onSelect={() => runCommand(() => setAutoRefresh(!state.autoRefreshEnabled))}>
            <Zap className="mr-2 h-4 w-4" />
            <span>{state.autoRefreshEnabled ? 'Disable' : 'Enable'} Auto-Refresh</span>
          </CommandItem>
        </CommandGroup>

        <CommandGroup heading="Databases">
          {state.databases.map((db) => {
             // Create a readable label
             const parts = db.path.split('/');
             const task = parts.length >= 3 ? parts[parts.length - 3] : 'Unknown';
             const name = parts.length >= 2 ? parts[parts.length - 2] : 'Unknown';
             return (
               <CommandItem
                 key={db.path}
                 value={`db-${task}-${name}`}
                 onSelect={() => runCommand(() => loadDatabase(db.path))}
                 data-selected={state.currentDbPath === db.path ? "true" : "false"}
               >
                 <Database className="mr-2 h-4 w-4" />
                 <span>{task} / {name}</span>
               </CommandItem>
             );
          })}
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
}
