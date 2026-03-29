import { useState, useMemo } from 'react';
import { useGenesis } from '../../context/GenesisContext';
import type { Program, SortState } from '../../types';
import './ProgramsTable.css';

export default function ProgramsTable() {
  const { state, selectProgram, setRightTab } = useGenesis();
  const { programs, selectedProgram } = state;

  const [showIncorrect, setShowIncorrect] = useState(false);
  const [sortState, setSortState] = useState<SortState>({
    key: 'generation',
    direction: 'asc',
  });

  // Filter and sort programs
  const filteredPrograms = useMemo(() => {
    let filtered = showIncorrect
      ? programs
      : programs.filter((p) => p.correct);

    // Sort
    filtered = [...filtered].sort((a, b) => {
      const aVal = getSortValue(a, sortState.key);
      const bVal = getSortValue(b, sortState.key);

      if (aVal === null && bVal === null) return 0;
      if (aVal === null) return 1;
      if (bVal === null) return -1;

      if (typeof aVal === 'number' && typeof bVal === 'number') {
        return sortState.direction === 'asc' ? aVal - bVal : bVal - aVal;
      }

      const aStr = String(aVal);
      const bStr = String(bVal);
      return sortState.direction === 'asc'
        ? aStr.localeCompare(bStr)
        : bStr.localeCompare(aStr);
    });

    // Add rank
    return filtered.map((p, i) => ({ ...p, rank: i + 1 }));
  }, [programs, showIncorrect, sortState]);

  const handleSort = (key: string) => {
    setSortState((prev) => ({
      key,
      direction: prev.key === key && prev.direction === 'asc' ? 'desc' : 'asc',
    }));
  };

  const handleRowClick = (program: Program) => {
    selectProgram(program);
    setRightTab('code-viewer');
  };

  const getSortArrow = (key: string) => {
    if (sortState.key !== key) return '';
    return sortState.direction === 'asc' ? ' ↑' : ' ↓';
  };

  return (
    <div className="programs-table-container">
      <div className="table-controls">
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={showIncorrect}
            onChange={(e) => setShowIncorrect(e.target.checked)}
          />
          Show incorrect programs
        </label>
      </div>

      <div className="table-wrapper">
        <table className="programs-table">
          <thead>
            <tr>
              <th className="sortable" onClick={() => handleSort('rank')}>
                Rank{getSortArrow('rank')}
              </th>
              <th className="sortable" onClick={() => handleSort('generation')}>
                Gen{getSortArrow('generation')}
              </th>
              <th>Patch Name</th>
              <th>Type</th>
              <th
                className="sortable"
                onClick={() => handleSort('island_idx')}
              >
                Island{getSortArrow('island_idx')}
              </th>
              <th
                className="sortable"
                onClick={() => handleSort('combined_score')}
              >
                Score{getSortArrow('combined_score')}
              </th>
              <th className="sortable" onClick={() => handleSort('api_cost')}>
                API Cost{getSortArrow('api_cost')}
              </th>
              <th className="sortable" onClick={() => handleSort('complexity')}>
                Complexity{getSortArrow('complexity')}
              </th>
              <th>Model</th>
            </tr>
          </thead>
          <tbody>
            {filteredPrograms.map((program) => (
              <tr
                key={program.id}
                className={`${selectedProgram?.id === program.id ? 'selected' : ''} ${!program.correct ? 'incorrect' : ''}`}
                onClick={() => handleRowClick(program)}
              >
                <td>{(program as Program & { rank: number }).rank}</td>
                <td>{program.generation}</td>
                <td className="patch-name" title={program.metadata.patch_name}>
                  {program.metadata.patch_name}
                </td>
                <td>{program.metadata.patch_type}</td>
                <td>{program.island_idx ?? '-'}</td>
                <td>{program.combined_score?.toFixed(4) ?? 'N/A'}</td>
                <td>${(program.metadata.api_cost || 0).toFixed(4)}</td>
                <td>{program.complexity?.toFixed(2) ?? '-'}</td>
                <td className="model-cell" title={program.metadata.model}>
                  {program.metadata.model || '-'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function getSortValue(
  program: Program,
  key: string
): string | number | null {
  switch (key) {
    case 'generation':
      return program.generation;
    case 'combined_score':
      return program.combined_score;
    case 'island_idx':
      return program.island_idx;
    case 'api_cost':
      return program.metadata.api_cost || 0;
    case 'complexity':
      return program.complexity;
    default:
      return null;
  }
}
