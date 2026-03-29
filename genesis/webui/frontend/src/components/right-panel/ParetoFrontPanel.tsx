import { useState, useMemo, useCallback, useEffect } from 'react';
import Plot from 'react-plotly.js';
import type { PlotMouseEvent, Data, Layout } from 'plotly.js';
import { useGenesis } from '../../context/GenesisContext';
import {
  getAvailableParetoMetrics,
  calculateParetoFront,
  getNestedValue,
  formatMetricValue,
  type ParetoMetric,
  type ParetoPoint,
} from '../../utils/pareto';
import './ParetoFrontPanel.css';

export default function ParetoFrontPanel() {
  const { state, selectProgram } = useGenesis();
  const { programs } = state;

  // Get available metrics
  const availableMetrics = useMemo(
    () => getAvailableParetoMetrics(programs),
    [programs]
  );

  // State for axis selections
  const [yAxisPath, setYAxisPath] = useState<string>('combined_score');
  const [xAxisPath, setXAxisPath] = useState<string>('complexity');
  const [yObjective, setYObjective] = useState<'min' | 'max'>('max');
  const [xObjective, setXObjective] = useState<'min' | 'max'>('min');

  // Update defaults when metrics are discovered
  useEffect(() => {
    if (availableMetrics.length > 0) {
      // Set Y-axis default
      const yDefault = availableMetrics.find(
        (m) => m.path === 'combined_score'
      );
      if (yDefault) {
        setYAxisPath(yDefault.path);
        setYObjective(yDefault.objective);
      }

      // Set X-axis default: prefer api_cost, then complexity
      const xDefault =
        availableMetrics.find((m) => m.path === 'metadata.api_cost') ||
        availableMetrics.find((m) => m.path === 'complexity');
      if (xDefault) {
        setXAxisPath(xDefault.path);
        setXObjective(xDefault.objective);
      }
    }
  }, [availableMetrics]);

  // Get current metric objects
  const yMetric: ParetoMetric | undefined = useMemo(() => {
    const base = availableMetrics.find((m) => m.path === yAxisPath);
    return base ? { ...base, objective: yObjective } : undefined;
  }, [availableMetrics, yAxisPath, yObjective]);

  const xMetric: ParetoMetric | undefined = useMemo(() => {
    const base = availableMetrics.find((m) => m.path === xAxisPath);
    return base ? { ...base, objective: xObjective } : undefined;
  }, [availableMetrics, xAxisPath, xObjective]);

  // Calculate Pareto data
  const paretoData = useMemo(() => {
    if (!xMetric || !yMetric || programs.length === 0) return null;
    return calculateParetoFront(programs, xMetric, yMetric);
  }, [programs, xMetric, yMetric]);

  // Handle axis change
  const handleYAxisChange = useCallback(
    (path: string) => {
      setYAxisPath(path);
      const metric = availableMetrics.find((m) => m.path === path);
      if (metric) setYObjective(metric.objective);
    },
    [availableMetrics]
  );

  const handleXAxisChange = useCallback(
    (path: string) => {
      setXAxisPath(path);
      const metric = availableMetrics.find((m) => m.path === path);
      if (metric) setXObjective(metric.objective);
    },
    [availableMetrics]
  );

  // Handle point click
  const handleClick = useCallback(
    (event: PlotMouseEvent) => {
      if (event.points.length > 0) {
        const point = event.points[0];
        const programId = point.customdata as string;
        const program = programs.find((p) => p.id === programId);
        if (program) {
          selectProgram(program);
        }
      }
    },
    [programs, selectProgram]
  );

  // Build hover text for a point
  const buildHoverText = useCallback(
    (point: ParetoPoint): string => {
      const p = point.program;
      let text = `<b>${p.metadata?.patch_name || p.id}</b><br>`;
      text += `Combined Score: ${formatMetricValue(p.combined_score)}<br>`;

      if (xMetric) {
        const xValue = getNestedValue(p, xMetric.path) as number;
        text += `${xMetric.name}: ${formatMetricValue(xValue)}<br>`;
      }
      if (yMetric) {
        const yValue = getNestedValue(p, yMetric.path) as number;
        text += `${yMetric.name}: ${formatMetricValue(yValue)}<br>`;
      }

      return text;
    },
    [xMetric, yMetric]
  );

  // Empty state
  if (programs.length === 0) {
    return (
      <div className="pareto-front-panel empty">
        <p>Load a database to view Pareto front.</p>
      </div>
    );
  }

  if (availableMetrics.length < 2) {
    return (
      <div className="pareto-front-panel empty">
        <p>Not enough numeric metrics available for Pareto analysis.</p>
      </div>
    );
  }

  if (!paretoData || !xMetric || !yMetric) {
    return (
      <div className="pareto-front-panel empty">
        <p>Select metrics to view Pareto front.</p>
      </div>
    );
  }

  const { allPoints, paretoPoints } = paretoData;

  // Categorize points
  const incorrectPoints = allPoints.filter((p) => !p.program.correct);
  const correctDominatedPoints = allPoints.filter(
    (p) => p.program.correct && !paretoPoints.includes(p)
  );

  // Sort Pareto points by x for the boundary line
  const sortedPareto = [...paretoPoints].sort((a, b) => a.x - b.x);

  // Calculate bounds for correct programs
  const correctPointsForBounds = [...paretoPoints, ...correctDominatedPoints];
  const hasCorrectPoints = correctPointsForBounds.length > 0;

  const correctX = correctPointsForBounds.map((p) => p.x);
  const correctY = correctPointsForBounds.map((p) => p.y);
  const xRange = hasCorrectPoints
    ? Math.max(...correctX) - Math.min(...correctX)
    : 1;
  const yRange = hasCorrectPoints
    ? Math.max(...correctY) - Math.min(...correctY)
    : 1;

  // Build Plotly traces
  const traces: Data[] = [];

  // Dominated region fill (render first so it's behind everything)
  if (sortedPareto.length > 0 && hasCorrectPoints) {
    const xFill: number[] = [];
    const yFill: number[] = [];

    const paretoX = sortedPareto.map((p) => p.x);
    const paretoY = sortedPareto.map((p) => p.y);

    const extendRight = xMetric.objective === 'min';
    const extendUp = yMetric.objective === 'min';

    const minX = Math.min(...correctX);
    const maxX = Math.max(...correctX);
    const minY = Math.min(...correctY);
    const maxY = Math.max(...correctY);
    const xPad = xRange * 0.05;
    const yPad = yRange * 0.05;

    if (extendRight && !extendUp) {
      // Dominated region is bottom-right
      xFill.push(minX);
      yFill.push(paretoY[0]);
      for (let i = 0; i < paretoX.length; i++) {
        xFill.push(paretoX[i]);
        yFill.push(paretoY[i]);
      }
      xFill.push(maxX);
      yFill.push(paretoY[paretoY.length - 1]);
      xFill.push(maxX);
      yFill.push(minY);
      xFill.push(minX);
      yFill.push(minY);
    } else if (!extendRight && !extendUp) {
      // Dominated region is bottom-left
      xFill.push(maxX + xPad);
      yFill.push(paretoY[paretoY.length - 1]);
      for (let i = paretoX.length - 1; i >= 0; i--) {
        xFill.push(paretoX[i]);
        yFill.push(paretoY[i]);
      }
      xFill.push(minX - xPad);
      yFill.push(paretoY[0]);
      xFill.push(minX - xPad);
      yFill.push(minY - yPad);
      xFill.push(maxX + xPad);
      yFill.push(minY - yPad);
    } else if (extendRight && extendUp) {
      // Dominated region is top-right
      xFill.push(minX - xPad);
      yFill.push(paretoY[0]);
      for (let i = 0; i < paretoX.length; i++) {
        xFill.push(paretoX[i]);
        yFill.push(paretoY[i]);
      }
      xFill.push(maxX + xPad);
      yFill.push(paretoY[paretoY.length - 1]);
      xFill.push(maxX + xPad);
      yFill.push(maxY + yPad);
      xFill.push(minX - xPad);
      yFill.push(maxY + yPad);
    } else {
      // Dominated region is top-left
      xFill.push(maxX + xPad);
      yFill.push(paretoY[paretoY.length - 1]);
      for (let i = paretoX.length - 1; i >= 0; i--) {
        xFill.push(paretoX[i]);
        yFill.push(paretoY[i]);
      }
      xFill.push(minX - xPad);
      yFill.push(paretoY[0]);
      xFill.push(minX - xPad);
      yFill.push(maxY + yPad);
      xFill.push(maxX + xPad);
      yFill.push(maxY + yPad);
    }

    traces.push({
      x: xFill,
      y: yFill,
      fill: 'toself',
      fillcolor: 'rgba(231, 76, 60, 0.15)',
      line: { width: 0 },
      mode: 'none',
      type: 'scatter',
      hoverinfo: 'none',
      showlegend: false,
      name: 'Dominated Region',
    });
  }

  // Dominated correct points (gray)
  traces.push({
    x: correctDominatedPoints.map((p) => p.x),
    y: correctDominatedPoints.map((p) => p.y),
    mode: 'markers',
    type: 'scatter',
    name: 'Dominated',
    text: correctDominatedPoints.map(buildHoverText),
    hoverinfo: 'text',
    marker: { color: 'rgba(150, 150, 150, 0.5)', size: 8 },
    customdata: correctDominatedPoints.map((p) => p.program.id),
  });

  // Incorrect points (red X)
  traces.push({
    x: incorrectPoints.map((p) => p.x),
    y: incorrectPoints.map((p) => p.y),
    mode: 'markers',
    type: 'scatter',
    name: 'Incorrect',
    text: incorrectPoints.map(buildHoverText),
    hoverinfo: 'text',
    marker: { color: '#e74c3c', size: 8, symbol: 'x' },
    customdata: incorrectPoints.map((p) => p.program.id),
  });

  // Pareto-optimal points (orange diamonds)
  traces.push({
    x: paretoPoints.map((p) => p.x),
    y: paretoPoints.map((p) => p.y),
    mode: 'markers',
    type: 'scatter',
    name: 'Pareto Optimal',
    text: paretoPoints.map(buildHoverText),
    hoverinfo: 'text',
    marker: { color: '#e58e26', size: 12, symbol: 'diamond' },
    customdata: paretoPoints.map((p) => p.program.id),
  });

  // Pareto boundary line
  if (sortedPareto.length > 1) {
    traces.push({
      x: sortedPareto.map((p) => p.x),
      y: sortedPareto.map((p) => p.y),
      mode: 'lines',
      type: 'scatter',
      name: 'Pareto Boundary',
      line: {
        color: '#e58e26',
        width: 2,
        shape: 'linear',
      },
      hoverinfo: 'none',
      showlegend: false,
    });
  }

  // Layout
  const xPadding = xRange * 0.1;
  const yPadding = yRange * 0.1;

  const layout: Partial<Layout> = {
    title: { text: 'Pareto Front Analysis' },
    xaxis: {
      title: { text: `${xMetric.name} (${xMetric.objective === 'min' ? 'Lower' : 'Higher'} is better)` },
      autorange: xMetric.objective === 'min' ? 'reversed' : true,
      ...(xMetric.objective !== 'min' &&
        hasCorrectPoints && {
          range: [
            Math.min(...correctX) - xPadding,
            Math.max(...correctX) + xPadding,
          ],
        }),
    },
    yaxis: {
      title: { text: `${yMetric.name} (${yMetric.objective === 'min' ? 'Lower' : 'Higher'} is better)` },
      autorange: yMetric.objective === 'min' ? 'reversed' : true,
      ...(yMetric.objective !== 'min' &&
        hasCorrectPoints && {
          range: [
            Math.min(...correctY) - yPadding,
            Math.max(...correctY) + yPadding,
          ],
        }),
    },
    hovermode: 'closest',
    showlegend: true,
    legend: {
      x: 1,
      xanchor: 'right',
      y: 1,
    },
    margin: { t: 50, r: 10, b: 60, l: 70 },
  };

  return (
    <div className="pareto-front-panel">
      <div className="pareto-controls">
        <div className="pareto-control-group">
          <label>Y Axis:</label>
          <select
            value={yAxisPath}
            onChange={(e) => handleYAxisChange(e.target.value)}
          >
            {availableMetrics.map((m) => (
              <option key={m.path} value={m.path}>
                {m.name}
              </option>
            ))}
          </select>
          <div className="objective-toggle">
            <button
              className={yObjective === 'max' ? 'active' : ''}
              onClick={() => setYObjective('max')}
            >
              Max
            </button>
            <button
              className={yObjective === 'min' ? 'active' : ''}
              onClick={() => setYObjective('min')}
            >
              Min
            </button>
          </div>
        </div>

        <div className="pareto-control-group">
          <label>X Axis:</label>
          <select
            value={xAxisPath}
            onChange={(e) => handleXAxisChange(e.target.value)}
          >
            {availableMetrics.map((m) => (
              <option key={m.path} value={m.path}>
                {m.name}
              </option>
            ))}
          </select>
          <div className="objective-toggle">
            <button
              className={xObjective === 'max' ? 'active' : ''}
              onClick={() => setXObjective('max')}
            >
              Max
            </button>
            <button
              className={xObjective === 'min' ? 'active' : ''}
              onClick={() => setXObjective('min')}
            >
              Min
            </button>
          </div>
        </div>
      </div>

      <div className="pareto-stats">
        <span>
          Total: {allPoints.length} | Correct: {correctDominatedPoints.length + paretoPoints.length} | Pareto Optimal: {paretoPoints.length}
        </span>
      </div>

      <div className="pareto-chart-container">
        <Plot
          data={traces}
          layout={layout}
          config={{ responsive: true, displayModeBar: true }}
          style={{ width: '100%', height: '100%' }}
          useResizeHandler={true}
          onClick={handleClick}
        />
      </div>
    </div>
  );
}
