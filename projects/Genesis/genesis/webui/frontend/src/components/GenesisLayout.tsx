import { useEffect } from 'react';
import Sidebar from './Sidebar';
import MainContent from './MainContent';
import { useGenesis } from '../context/GenesisContext';

export default function GenesisLayout() {
  const { loadDatabases } = useGenesis();

  // Load databases on mount
  useEffect(() => {
    loadDatabases();
  }, [loadDatabases]);

  return (
    <div className="h-screen bg-gray-950 text-gray-100 flex overflow-hidden">
      <Sidebar />
      <MainContent />
    </div>
  );
}
