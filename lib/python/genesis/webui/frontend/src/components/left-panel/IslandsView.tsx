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
} from 'chart.js';
import { Line } from 'react-chartjs-2';
import { useGenesis } from '../../context/GenesisContext';
import './IslandsView.css';

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend
);

const ISLAND_COLORS = [
  '#1f77b4',
  '#2ca02c',
  '#9467bd',
  '#8c564b',
  '#e377c2',
  '#7f7f7f',
  '#bcbd22',
  '#17becf',
  '#aec7e8',
];

export default function IslandsView() {
  const { state } = useGenesis();
  const { programs } = state;

  const chartData = useMemo(() => {
    // Get unique islands
    const islands = [
      ...new Set(
        programs
          .filter((p) => p.island_idx !== null && p.island_idx !== undefined)
          .map((p) => p.island_idx as number)
      ),
    ].sort((a, b) => a - b);

    if (islands.length === 0) return null;

    // Group by generation and island
    const generations = [...new Set(programs.map((p) => p.generation))].sort(
      (a, b) => a - b
    );

    const datasets = islands.map((island, idx) => {
      const data = generations.map((gen) => {
        const islandPrograms = programs.filter(
          (p) =>
            p.generation === gen &&
            p.island_idx === island &&
            p.correct &&
            p.combined_score !== null
        );
        if (islandPrograms.length === 0) return null;
        return Math.max(...islandPrograms.map((p) => p.combined_score as number));
      });

      return {
        label: `Island ${island}`,
        data,
        borderColor: ISLAND_COLORS[idx % ISLAND_COLORS.length],
        backgroundColor: ISLAND_COLORS[idx % ISLAND_COLORS.length] + '33',
        tension: 0.1,
        spanGaps: true,
      };
    });

    return {
      labels: generations.map((g) => `Gen ${g}`),
      datasets,
    };
  }, [programs]);

  if (!chartData) {
    return (
      <div className="islands-view empty">
        <p>No island data available for this evolution run.</p>
      </div>
    );
  }

  // Dark theme colors
  const darkTheme = {
    gridColor: 'rgba(139, 148, 158, 0.1)',
    textColor: '#8b949e',
    textColorLight: '#c9d1d9',
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: 'top' as const,
        labels: {
          color: darkTheme.textColorLight,
          font: { size: 12 },
          padding: 16,
        },
      },
      title: {
        display: true,
        text: 'Best Score per Island over Generations',
        color: '#e6edf3',
        font: { size: 16, weight: 600 as const },
      },
      tooltip: {
        backgroundColor: '#21262d',
        titleColor: '#e6edf3',
        bodyColor: '#c9d1d9',
        borderColor: '#30363d',
        borderWidth: 1,
        padding: 12,
        cornerRadius: 8,
      },
    },
    scales: {
      x: {
        grid: { color: darkTheme.gridColor },
        ticks: { color: darkTheme.textColor },
        border: { display: false },
      },
      y: {
        title: {
          display: true,
          text: 'Best Score',
          color: darkTheme.textColor,
        },
        grid: { color: darkTheme.gridColor },
        ticks: { color: darkTheme.textColor },
        border: { display: false },
      },
    },
  };

  return (
    <div className="islands-view">
      <div className="chart-container">
        <Line data={chartData} options={options} />
      </div>
    </div>
  );
}
