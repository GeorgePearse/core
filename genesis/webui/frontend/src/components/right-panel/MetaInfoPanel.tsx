import { useMemo } from 'react';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler,
} from 'chart.js';
import { Line } from 'react-chartjs-2';
import { useGenesis } from '../../context/GenesisContext';
import './MetaInfoPanel.css';

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler
);

export default function MetaInfoPanel() {
  const { state, stats } = useGenesis();
  const { programs } = state;

  const chartData = useMemo(() => {
    if (programs.length === 0) return null;

    const byGeneration = new Map<number, typeof programs>();
    programs.forEach((p) => {
      if (!byGeneration.has(p.generation)) {
        byGeneration.set(p.generation, []);
      }
      byGeneration.get(p.generation)!.push(p);
    });

    const generations = [...byGeneration.keys()].sort((a, b) => a - b);
    const maxScores: number[] = [];
    const cumulativeCosts: number[] = [];
    let runningCost = 0;
    let runningMax = 0;

    generations.forEach((gen) => {
      const genPrograms = byGeneration.get(gen)!;
      const correctPrograms = genPrograms.filter(
        (p) => p.correct && p.combined_score !== null
      );

      if (correctPrograms.length > 0) {
        const scores = correctPrograms.map((p) => p.combined_score as number);
        runningMax = Math.max(runningMax, ...scores);
      }
      maxScores.push(runningMax);

      genPrograms.forEach((p) => {
        runningCost +=
          (p.metadata.api_cost || 0) +
          (p.metadata.embed_cost || 0) +
          (p.metadata.novelty_cost || 0) +
          (p.metadata.meta_cost || 0);
      });
      cumulativeCosts.push(runningCost);
    });

    return { generations, maxScores, cumulativeCosts };
  }, [programs]);

  if (programs.length === 0) {
    return (
      <div className="meta-info-panel empty">
        <p>Select a database to view evolution statistics.</p>
      </div>
    );
  }

  const { bestProgram, totalCost, costBreakdown } = stats;

  return (
    <div className="meta-info-panel">
      <h3>Meta Information</h3>

      <div className="stats-cards">
        <div className="stat-card">
          <h4>Overview</h4>
          <p>
            <strong>Total Generations:</strong> {stats.totalGenerations}
          </p>
          <p>
            <strong>Correct:</strong> {stats.correctPrograms} /{' '}
            {stats.totalPrograms}
          </p>
          <p>
            <strong>Total Cost:</strong> ${totalCost.toFixed(4)}
          </p>
          <p>
            <strong>Avg Cost/Program:</strong> $
            {stats.avgCostPerProgram.toFixed(4)}
          </p>
        </div>

        <div className="stat-card">
          <h4>Best Solution</h4>
          <p>
            <strong>Best Score:</strong>{' '}
            <span className="metric-good">{stats.bestScore.toFixed(4)}</span>
          </p>
          <p>
            <strong>Name:</strong>{' '}
            {bestProgram?.metadata.patch_name || 'N/A'}
          </p>
          <p>
            <strong>Generation:</strong> {bestProgram?.generation ?? 'N/A'}
          </p>
          <p>
            <strong>Island:</strong> {bestProgram?.island_idx ?? 'N/A'}
          </p>
        </div>

        <div className="stat-card">
          <h4>Cost Breakdown</h4>
          <p>
            <strong>API Cost:</strong> ${costBreakdown.api.toFixed(4)}
          </p>
          <p>
            <strong>Embedding Cost:</strong> ${costBreakdown.embed.toFixed(4)}
          </p>
          <p>
            <strong>Novelty Cost:</strong> ${costBreakdown.novelty.toFixed(4)}
          </p>
          <p>
            <strong>Meta Cost:</strong> ${costBreakdown.meta.toFixed(4)}
          </p>
        </div>
      </div>

      {chartData && (
        <div className="charts-section">
          <div className="chart-container">
            <h4>Performance Over Generations</h4>
            <div className="chart-wrapper">
              <Line
                data={{
                  labels: chartData.generations.map((g) => `Gen ${g}`),
                  datasets: [
                    {
                      label: 'Best Score (Cumulative)',
                      data: chartData.maxScores,
                      borderColor: '#2ecc71',
                      backgroundColor: 'rgba(46, 204, 113, 0.1)',
                      fill: true,
                      tension: 0.1,
                    },
                  ],
                }}
                options={{
                  responsive: true,
                  maintainAspectRatio: false,
                  plugins: {
                    legend: { position: 'top' },
                  },
                }}
              />
            </div>
          </div>

          <div className="chart-container">
            <h4>Cumulative Cost</h4>
            <div className="chart-wrapper">
              <Line
                data={{
                  labels: chartData.generations.map((g) => `Gen ${g}`),
                  datasets: [
                    {
                      label: 'Total Cost ($)',
                      data: chartData.cumulativeCosts,
                      borderColor: '#e74c3c',
                      backgroundColor: 'rgba(231, 76, 60, 0.1)',
                      fill: true,
                      tension: 0.1,
                    },
                  ],
                }}
                options={{
                  responsive: true,
                  maintainAspectRatio: false,
                  plugins: {
                    legend: { position: 'top' },
                  },
                }}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
