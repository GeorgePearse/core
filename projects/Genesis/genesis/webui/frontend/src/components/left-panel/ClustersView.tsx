import { useMemo } from 'react';
import Plot from 'react-plotly.js';
import { useGenesis } from '../../context/GenesisContext';
import './ClustersView.css';

export default function ClustersView() {
  const { state, selectProgram } = useGenesis();
  const { programs } = state;

  const programsWithEmbeddings = useMemo(() => {
    return programs.filter(
      (p) =>
        p.correct &&
        p.embedding_pca_2d &&
        p.embedding_pca_2d.length === 2 &&
        p.embedding_pca_3d &&
        p.embedding_pca_3d.length === 3 &&
        p.combined_score !== null
    );
  }, [programs]);

  const plotData = useMemo(() => {
    if (programsWithEmbeddings.length === 0) return null;

    const scores = programsWithEmbeddings.map((p) => p.combined_score as number);
    const minScore = Math.min(...scores);
    const maxScore = Math.max(...scores);
    
    // Size scale
    const getSize = (score: number) => {
        if (maxScore === minScore) return 10;
        return 5 + 15 * (score - minScore) / (maxScore - minScore);
    };

    const sizes = programsWithEmbeddings.map(p => getSize(p.combined_score as number));
    const bestProgram = programsWithEmbeddings.reduce((best, curr) => 
        (curr.combined_score! > best.combined_score!) ? curr : best
    , programsWithEmbeddings[0]);

    const symbols = programsWithEmbeddings.map(p => p.id === bestProgram.id ? 'star' : 'circle');
    const symbols3d = programsWithEmbeddings.map(p => p.id === bestProgram.id ? 'diamond' : 'circle');
    const lineColors = programsWithEmbeddings.map(p => p.id === bestProgram.id ? 'gold' : 'white');
    const lineWidths = programsWithEmbeddings.map(p => p.id === bestProgram.id ? 2 : 0.5);

    // Use island_idx or cluster if available
    // Legacy code uses p.embedding_cluster_id but my types interface doesn't show it explicitly
    // checking types again: it is NOT in types.ts I read earlier.
    // But legacy code uses it. I should check if `Program` type has it.
    // If not, use island_idx for coloring
    const colorData = programsWithEmbeddings.map(p => (p as any).embedding_cluster_id ?? p.island_idx ?? 0);

    return {
        x2d: programsWithEmbeddings.map(p => p.embedding_pca_2d![0]),
        y2d: programsWithEmbeddings.map(p => p.embedding_pca_2d![1]),
        x3d: programsWithEmbeddings.map(p => p.embedding_pca_3d![0]),
        y3d: programsWithEmbeddings.map(p => p.embedding_pca_3d![1]),
        z3d: programsWithEmbeddings.map(p => p.embedding_pca_3d![2]),
        ids: programsWithEmbeddings.map(p => p.id),
        text: programsWithEmbeddings.map(p => `<b>${p.metadata.patch_name || 'unnamed'}</b><br>Score: ${p.combined_score?.toFixed(4)}`),
        sizes,
        symbols,
        symbols3d,
        lineColors,
        lineWidths,
        colorData
    };
  }, [programsWithEmbeddings]);

  if (programsWithEmbeddings.length === 0) {
    return (
      <div className="clusters-view empty">
        <p>No PCA embedding data available for this evolution run.</p>
      </div>
    );
  }

  if (!plotData) return null;

  const handlePlotClick = (event: Readonly<Plotly.PlotMouseEvent>) => {
    if (event.points && event.points.length > 0) {
        const pointIndex = event.points[0].pointIndex; // or pointNumber
        // pointIndex corresponds to the index in the data arrays
        const program = programsWithEmbeddings[pointIndex];
        if (program) {
            selectProgram(program);
        }
    }
  };

  return (
    <div className="clusters-view">
      <h4>PCA Embeddings</h4>
      <div className="clusters-content">
        <div className="plot-container">
            <Plot
                data={[
                    {
                        x: plotData.x2d,
                        y: plotData.y2d,
                        mode: 'markers',
                        type: 'scatter',
                        text: plotData.text,
                        hoverinfo: 'text',
                        marker: {
                            color: plotData.colorData,
                            colorscale: 'Portland',
                            size: plotData.sizes,
                            symbol: plotData.symbols,
                            line: {
                                color: plotData.lineColors,
                                width: plotData.lineWidths
                            }
                        }
                    }
                ]}
                layout={{
                    title: { text: '2D PCA', font: { color: '#e6edf3' } },
                    autosize: true,
                    margin: { t: 40, l: 50, r: 20, b: 50 },
                    xaxis: {
                      title: { text: 'PC1', font: { color: '#8b949e' } },
                      tickfont: { color: '#8b949e' },
                      gridcolor: 'rgba(139, 148, 158, 0.1)',
                      zerolinecolor: 'rgba(139, 148, 158, 0.2)'
                    },
                    yaxis: {
                      title: { text: 'PC2', font: { color: '#8b949e' } },
                      tickfont: { color: '#8b949e' },
                      gridcolor: 'rgba(139, 148, 158, 0.1)',
                      zerolinecolor: 'rgba(139, 148, 158, 0.2)',
                      scaleanchor: 'x'
                    },
                    paper_bgcolor: '#161b22',
                    plot_bgcolor: '#0d1117'
                }}
                useResizeHandler={true}
                style={{ width: '100%', height: '50%' }}
                onClick={handlePlotClick}
            />
            <Plot
                data={[
                    {
                        x: plotData.x3d,
                        y: plotData.y3d,
                        z: plotData.z3d,
                        mode: 'markers',
                        type: 'scatter3d',
                        text: plotData.text,
                        hoverinfo: 'text',
                        marker: {
                            color: plotData.colorData,
                            colorscale: 'Portland',
                            size: plotData.sizes,
                            symbol: plotData.symbols3d,
                            line: {
                                color: plotData.lineColors,
                                width: plotData.lineWidths
                            }
                        }
                    }
                ]}
                layout={{
                    title: { text: '3D PCA', font: { color: '#e6edf3' } },
                    autosize: true,
                    margin: { t: 40, l: 0, r: 0, b: 0 },
                    scene: {
                        xaxis: {
                          title: { text: 'PC1', font: { color: '#8b949e' } },
                          tickfont: { color: '#8b949e' },
                          gridcolor: 'rgba(139, 148, 158, 0.15)',
                          backgroundcolor: '#0d1117'
                        },
                        yaxis: {
                          title: { text: 'PC2', font: { color: '#8b949e' } },
                          tickfont: { color: '#8b949e' },
                          gridcolor: 'rgba(139, 148, 158, 0.15)',
                          backgroundcolor: '#0d1117'
                        },
                        zaxis: {
                          title: { text: 'PC3', font: { color: '#8b949e' } },
                          tickfont: { color: '#8b949e' },
                          gridcolor: 'rgba(139, 148, 158, 0.15)',
                          backgroundcolor: '#0d1117'
                        },
                        bgcolor: '#0d1117'
                    },
                    paper_bgcolor: '#161b22'
                }}
                useResizeHandler={true}
                style={{ width: '100%', height: '50%' }}
                onClick={handlePlotClick}
            />
        </div>
      </div>
    </div>
  );
}
