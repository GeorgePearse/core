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
import './MetricsView.css';

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

// Dark theme colors
const darkTheme = {
  background: '#161b22',
  gridColor: 'rgba(139, 148, 158, 0.1)',
  textColor: '#8b949e',
  textColorLight: '#c9d1d9',
};

export default function MetricsView() {
  const { state } = useGenesis();
  const { programs } = state;

  const metricsData = useMemo(() => {
    if (programs.length === 0) return null;

    // Group by generation
    const byGeneration = new Map<number, typeof programs>();
    programs.forEach((p) => {
      if (!byGeneration.has(p.generation)) {
        byGeneration.set(p.generation, []);
      }
      byGeneration.get(p.generation)!.push(p);
    });

    const generations = [...byGeneration.keys()].sort((a, b) => a - b);
    const maxScores: number[] = [];
    const avgScores: number[] = [];
    const cumulativeCosts: number[] = [];
    let runningCost = 0;

    generations.forEach((gen) => {
      const genPrograms = byGeneration.get(gen)!;
      const correctPrograms = genPrograms.filter(
        (p) => p.correct && p.combined_score !== null
      );

      if (correctPrograms.length > 0) {
        const scores = correctPrograms.map((p) => p.combined_score as number);
        maxScores.push(Math.max(...scores));
        avgScores.push(scores.reduce((a, b) => a + b, 0) / scores.length);
      } else {
        maxScores.push(maxScores[maxScores.length - 1] || 0);
        avgScores.push(avgScores[avgScores.length - 1] || 0);
      }

      genPrograms.forEach((p) => {
        runningCost +=
          (p.metadata.api_cost || 0) +
          (p.metadata.embed_cost || 0) +
          (p.metadata.novelty_cost || 0) +
          (p.metadata.meta_cost || 0);
      });
      cumulativeCosts.push(runningCost);
    });

    return { generations, maxScores, avgScores, cumulativeCosts };
  }, [programs]);

  if (!metricsData) {
    return (
      <div className="metrics-view empty">
        <p>No data available</p>
      </div>
    );
  }

  const scoreChartData = {
    labels: metricsData.generations.map((g) => `Gen ${g}`),
    datasets: [
      {
        label: 'Max Score',
        data: metricsData.maxScores,
        borderColor: '#3fb950',
        backgroundColor: 'rgba(63, 185, 80, 0.15)',
        pointBackgroundColor: '#3fb950',
        pointBorderColor: '#3fb950',
        pointHoverBackgroundColor: '#7ee787',
        pointHoverBorderColor: '#7ee787',
        tension: 0.3,
        fill: true,
        borderWidth: 2,
        pointRadius: 3,
        pointHoverRadius: 5,
      },
      {
        label: 'Avg Score',
        data: metricsData.avgScores,
        borderColor: '#58a6ff',
        backgroundColor: 'rgba(88, 166, 255, 0.1)',
        pointBackgroundColor: '#58a6ff',
        pointBorderColor: '#58a6ff',
        pointHoverBackgroundColor: '#a5d6ff',
        pointHoverBorderColor: '#a5d6ff',
        tension: 0.3,
        fill: false,
        borderWidth: 2,
        pointRadius: 3,
        pointHoverRadius: 5,
      },
    ],
  };

  const costChartData = {
    labels: metricsData.generations.map((g) => `Gen ${g}`),
    datasets: [
      {
        label: 'Cumulative Cost ($)',
        data: metricsData.cumulativeCosts,
        borderColor: '#f85149',
        backgroundColor: 'rgba(248, 81, 73, 0.15)',
        pointBackgroundColor: '#f85149',
        pointBorderColor: '#f85149',
        pointHoverBackgroundColor: '#ffa198',
        pointHoverBorderColor: '#ffa198',
        fill: true,
        tension: 0.3,
        borderWidth: 2,
        pointRadius: 3,
        pointHoverRadius: 5,
      },
    ],
  };

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: {
      mode: 'index' as const,
      intersect: false,
    },
    plugins: {
      legend: {
        position: 'top' as const,
        labels: {
          color: darkTheme.textColorLight,
          font: {
            size: 12,
            family: "'Inter', sans-serif",
          },
          padding: 16,
          usePointStyle: true,
          pointStyle: 'rect',
        },
      },
      tooltip: {
        backgroundColor: '#21262d',
        titleColor: '#e6edf3',
        bodyColor: '#c9d1d9',
        borderColor: '#30363d',
        borderWidth: 1,
        padding: 12,
        titleFont: {
          size: 13,
          weight: 600 as const,
        },
        bodyFont: {
          size: 12,
        },
        cornerRadius: 8,
      },
    },
    scales: {
      x: {
        grid: {
          color: darkTheme.gridColor,
          drawBorder: false,
        },
        ticks: {
          color: darkTheme.textColor,
          font: {
            size: 11,
          },
          maxRotation: 45,
          minRotation: 45,
        },
        border: {
          display: false,
        },
      },
      y: {
        beginAtZero: false,
        grid: {
          color: darkTheme.gridColor,
          drawBorder: false,
        },
        ticks: {
          color: darkTheme.textColor,
          font: {
            size: 11,
          },
          padding: 8,
        },
        border: {
          display: false,
        },
      },
    },
  };

  return (
    <div className="metrics-view">
      <h4>Metrics Over Generations</h4>

      <div className="chart-container">
        <h5>Performance Score</h5>
        <div className="chart-wrapper">
          <Line data={scoreChartData} options={chartOptions} />
        </div>
      </div>

      <div className="chart-container">
        <h5>Cumulative Cost</h5>
        <div className="chart-wrapper">
          <Line data={costChartData} options={chartOptions} />
        </div>
      </div>
    </div>
  );
}
