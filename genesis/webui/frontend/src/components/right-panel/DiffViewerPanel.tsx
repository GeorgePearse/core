import { useMemo } from 'react';
import { diffLines } from 'diff';
import { useGenesis } from '../../context/GenesisContext';
import './DiffViewerPanel.css';

export default function DiffViewerPanel() {
  const { state } = useGenesis();
  const { selectedProgram, programs } = state;

  const diffData = useMemo(() => {
    if (!selectedProgram || !selectedProgram.parent_id) return null;

    const parent = programs.find((p) => p.id === selectedProgram.parent_id);
    if (!parent) return null;

    const changes = diffLines(parent.code, selectedProgram.code);
    return {
      parent,
      changes,
    };
  }, [selectedProgram, programs]);

  if (!selectedProgram) {
    return (
      <div className="diff-viewer-panel empty">
        <p>Select a node to view its code diff.</p>
      </div>
    );
  }

  if (!diffData) {
    return (
      <div className="diff-viewer-panel empty">
        <p>
          {selectedProgram.parent_id
            ? 'Parent program not found.'
            : 'This is a root node with no parent to compare.'}
        </p>
      </div>
    );
  }

  const { parent, changes } = diffData;

  // Count additions and deletions
  const additions = changes.filter((c) => c.added).reduce((sum, c) => sum + (c.count || 0), 0);
  const deletions = changes.filter((c) => c.removed).reduce((sum, c) => sum + (c.count || 0), 0);

  return (
    <div className="diff-viewer-panel">
      <div className="diff-header">
        <h4>Code Diff</h4>
        <div className="diff-stats">
          <span className="stat additions">+{additions} additions</span>
          <span className="stat deletions">-{deletions} deletions</span>
        </div>
      </div>

      <div className="diff-info">
        <span>
          <strong>From:</strong> {parent.metadata.patch_name} (Gen{' '}
          {parent.generation})
        </span>
        <span>→</span>
        <span>
          <strong>To:</strong> {selectedProgram.metadata.patch_name} (Gen{' '}
          {selectedProgram.generation})
        </span>
      </div>

      <div className="diff-content">
        {changes.map((part, index) => {
          const className = part.added
            ? 'diff-line added'
            : part.removed
              ? 'diff-line removed'
              : 'diff-line unchanged';

          return (
            <div key={index} className={className}>
              <span className="diff-marker">
                {part.added ? '+' : part.removed ? '-' : ' '}
              </span>
              <pre>{part.value}</pre>
            </div>
          );
        })}
      </div>
    </div>
  );
}
