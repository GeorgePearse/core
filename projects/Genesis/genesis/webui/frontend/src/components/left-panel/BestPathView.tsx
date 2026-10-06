import { useMemo } from 'react';
import { useGenesis } from '../../context/GenesisContext';
import type { Program } from '../../types';
import './BestPathView.css';

export default function BestPathView() {
  const { state, stats, selectProgram, setRightTab } = useGenesis();
  const { programs, selectedProgram } = state;
  const { bestProgram } = stats;

  // Build path to best program
  const pathToBest = useMemo(() => {
    if (!bestProgram) return [];

    const path: Program[] = [];
    const programMap = new Map(programs.map((p) => [p.id, p]));

    let current: Program | undefined = bestProgram;
    while (current) {
      path.unshift(current);
      if (current.parent_id) {
        current = programMap.get(current.parent_id);
      } else {
        break;
      }
    }

    return path;
  }, [bestProgram, programs]);

  const handleNodeClick = (program: Program) => {
    selectProgram(program);
    setRightTab('code-viewer');
  };

  if (pathToBest.length === 0) {
    return (
      <div className="best-path-view empty">
        <p>No best path available.</p>
      </div>
    );
  }

  return (
    <div className="best-path-view">
      <h4>Path to Best Solution</h4>
      <div className="timeline">
        {pathToBest.map((program, index) => (
          <div
            key={program.id}
            className={`timeline-item ${selectedProgram?.id === program.id ? 'selected' : ''}`}
            onClick={() => handleNodeClick(program)}
          >
            <div className="timeline-marker" />
            <div className="timeline-content">
              <h5>
                Generation {program.generation}
                {index === pathToBest.length - 1 && (
                  <span className="best-badge">🏆 Best</span>
                )}
              </h5>
              <p>
                <strong>{program.metadata.patch_name}</strong>
              </p>
              <p className="score">
                Score: {program.combined_score?.toFixed(4) || 'N/A'}
              </p>
              <p className="meta">
                Type: {program.metadata.patch_type} | Island:{' '}
                {program.island_idx ?? 'N/A'}
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
