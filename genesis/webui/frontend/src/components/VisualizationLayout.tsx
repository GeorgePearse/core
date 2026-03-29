import { useState, useCallback, useRef, useEffect } from 'react';
import DatabaseSelector from './DatabaseSelector';
import LeftPanel from './left-panel/LeftPanel';
import RightPanel from './right-panel/RightPanel';
import './VisualizationLayout.css';

export default function VisualizationLayout() {
  const [leftPanelWidth, setLeftPanelWidth] = useState(50); // percentage
  const containerRef = useRef<HTMLDivElement>(null);
  const isDragging = useRef(false);

  const handleMouseDown = useCallback(() => {
    isDragging.current = true;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  }, []);

  const handleMouseMove = useCallback((e: MouseEvent) => {
    if (!isDragging.current || !containerRef.current) return;

    const containerRect = containerRef.current.getBoundingClientRect();
    const newWidth =
      ((e.clientX - containerRect.left) / containerRect.width) * 100;

    // Enforce min/max constraints (20% - 80%)
    const clampedWidth = Math.max(20, Math.min(80, newWidth));
    setLeftPanelWidth(clampedWidth);
  }, []);

  const handleMouseUp = useCallback(() => {
    isDragging.current = false;
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
  }, []);

  useEffect(() => {
    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [handleMouseMove, handleMouseUp]);

  return (
    <div className="visualization-layout">
      <DatabaseSelector />
      <div className="panels-container" ref={containerRef}>
        <div className="left-panel" style={{ width: `${leftPanelWidth}%` }}>
          <LeftPanel />
        </div>
        <div
          className="divider"
          onMouseDown={handleMouseDown}
          role="separator"
          aria-orientation="vertical"
        />
        <div
          className="right-panel"
          style={{ width: `${100 - leftPanelWidth}%` }}
        >
          <RightPanel />
        </div>
      </div>
    </div>
  );
}
