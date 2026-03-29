import { useEffect, useRef, useState, useMemo } from 'react';
import * as d3 from 'd3';
import { useGenesis } from '../../context/GenesisContext';
import './EmbeddingsView.css';

function cosineSimilarity(vecA: number[], vecB: number[]): number {
  let dotProduct = 0;
  let normA = 0;
  let normB = 0;
  for (let i = 0; i < vecA.length; i++) {
    dotProduct += vecA[i] * vecB[i];
    normA += vecA[i] * vecA[i];
    normB += vecB[i] * vecB[i];
  }
  if (normA === 0 || normB === 0) return 0;
  return dotProduct / (Math.sqrt(normA) * Math.sqrt(normB));
}

function computeSimilarityMatrix(embeddings: number[][]): number[][] {
  const n = embeddings.length;
  const matrix = Array(n)
    .fill(0)
    .map(() => Array(n).fill(0));
  for (let i = 0; i < n; i++) {
    for (let j = i; j < n; j++) {
      const sim = cosineSimilarity(embeddings[i], embeddings[j]);
      matrix[i][j] = sim;
      matrix[j][i] = sim;
    }
  }
  return matrix;
}

export default function EmbeddingsView() {
  const { state, selectProgram } = useGenesis();
  const { programs } = state;
  const containerRef = useRef<HTMLDivElement>(null);
  
  // Controls state
  const [sortBy, setSortBy] = useState<'chronological' | 'performance'>('chronological');
  const [colorScaleName, setColorScaleName] = useState('magma');
  const [cellSize, setCellSize] = useState(8);
  const [minVal, setMinVal] = useState(0.5);
  const [maxVal, setMaxVal] = useState(1.0);

  // Filter programs with embeddings
  const dataWithEmbeddings = useMemo(() => {
    // Deduplicate generation 0 programs (logic from legacy)
    let filtered = [...programs];
    const gen0Programs = programs.filter(d => d.generation === 0);
    if (gen0Programs.length > 1) {
        const gen0Groups: Record<string, typeof programs> = {};
        gen0Programs.forEach(prog => {
            const key = prog.code || 'no-code';
            if (!gen0Groups[key]) gen0Groups[key] = [];
            gen0Groups[key].push(prog);
        });
        const duplicateIds = new Set<string>();
        Object.values(gen0Groups).forEach(group => {
            if (group.length > 1) {
                group.sort((a, b) => (a.island_idx || 0) - (b.island_idx || 0));
                group.slice(1).forEach(prog => duplicateIds.add(prog.id));
            }
        });
        filtered = programs.filter(d => !duplicateIds.has(d.id));
    }
    return filtered.filter(p => p.embedding && p.embedding.length > 0);
  }, [programs]);

  useEffect(() => {
    if (!containerRef.current || dataWithEmbeddings.length === 0) return;

    const container = d3.select(containerRef.current);
    container.selectAll('*').remove();

    const embeddings = dataWithEmbeddings.map(d => d.embedding!);
    const similarityMatrix = computeSimilarityMatrix(embeddings);

    // Sorting
    let ordering = Array.from({ length: dataWithEmbeddings.length }, (_, i) => i);
    if (sortBy === 'performance') {
        const indexed = dataWithEmbeddings.map((p, i) => ({ p, i }));
        indexed.sort((a, b) => {
            const scoreA = (a.p.correct && a.p.combined_score != null) ? a.p.combined_score : -Infinity;
            const scoreB = (b.p.correct && b.p.combined_score != null) ? b.p.combined_score : -Infinity;
            return scoreB - scoreA;
        });
        ordering = indexed.map(x => x.i);
    }

    // Prepare ordered data
    const orderedMatrix = ordering.map(i => ordering.map(j => similarityMatrix[i][j]));
    const orderedPrograms = ordering.map(i => dataWithEmbeddings[i]);

    // Visualization parameters
    const margin = { top: 50, right: 50, bottom: 50, left: 50 };
    const width = orderedMatrix.length * cellSize;
    const height = orderedMatrix.length * cellSize;
    const totalWidth = width + margin.left + margin.right + 50; // +50 for score bar
    const totalHeight = height + margin.top + margin.bottom;

    const svg = container.append('svg')
        .attr('width', totalWidth)
        .attr('height', totalHeight);

    const g = svg.append('g')
        .attr('transform', `translate(${margin.left},${margin.top})`);

    // Color scale
    let interpolator;
    switch (colorScaleName) {
        case 'viridis': interpolator = d3.interpolateViridis; break;
        case 'plasma': interpolator = d3.interpolatePlasma; break;
        case 'inferno': interpolator = d3.interpolateInferno; break;
        default: interpolator = d3.interpolateMagma;
    }
    const colorScale = d3.scaleSequential(interpolator).domain([minVal, maxVal]);

    // Draw cells
    const rows = g.selectAll('.row')
        .data(orderedMatrix)
        .enter().append('g')
        .attr('transform', (_, i) => `translate(0,${i * cellSize})`);

    rows.selectAll('.cell')
        .data(d => d)
        .enter().append('rect')
        .attr('class', 'cell')
        .attr('x', (_, i) => i * cellSize)
        .attr('width', cellSize)
        .attr('height', cellSize)
        .style('fill', d => colorScale(d))
        .on('mouseover', (event: MouseEvent, d) => {
            d3.select(event.currentTarget as Element).append('title').text(`Similarity: ${d.toFixed(3)}`);
        });
    
    // Re-implementing cells with indices for click handling
    g.selectAll('*').remove(); // Clear first
    
    orderedMatrix.forEach((row, i) => {
        row.forEach((val, j) => {
            g.append('rect')
                .attr('x', j * cellSize)
                .attr('y', i * cellSize)
                .attr('width', cellSize)
                .attr('height', cellSize)
                .style('fill', colorScale(val))
                .style('stroke', 'none')
                .on('mouseover', function(event: MouseEvent) {
                    d3.select(this).style('stroke', '#fff').style('stroke-width', 1);
                    const progA = orderedPrograms[i];
                    const progB = orderedPrograms[j];
                    const tooltip = d3.select('.embeddings-tooltip');
                    tooltip.style('opacity', 1)
                        .html(`
                            <strong>${progA.metadata.patch_name}</strong> vs <strong>${progB.metadata.patch_name}</strong><br>
                            Gen ${progA.generation} vs Gen ${progB.generation}<br>
                            Similarity: ${val.toFixed(3)}
                        `)
                        .style('left', (event.pageX + 10) + 'px')
                        .style('top', (event.pageY - 10) + 'px');
                })
                .on('mouseout', function() {
                    d3.select(this).style('stroke', 'none');
                    d3.select('.embeddings-tooltip').style('opacity', 0);
                })
                .on('click', () => {
                    selectProgram(orderedPrograms[i]); // Select the row program
                });
        });
    });

    // Performance bar
    const scoreScale = d3.scaleSequential(d3.interpolatePlasma).domain([0, 1]); // Assuming normalized scores or use min/max
    const scores = orderedPrograms.map(p => p.combined_score);
    const minScore = Math.min(...scores.filter(s => s !== null) as number[]) || 0;
    const maxScore = Math.max(...scores.filter(s => s !== null) as number[]) || 1;
    scoreScale.domain([minScore, maxScore]);

    const perfBarX = width + 10;
    orderedPrograms.forEach((p, i) => {
        g.append('rect')
            .attr('x', perfBarX)
            .attr('y', i * cellSize)
            .attr('width', 15)
            .attr('height', cellSize)
            .style('fill', p.correct && p.combined_score !== null ? scoreScale(p.combined_score) : '#ccc')
            .append('title').text(`Score: ${p.combined_score?.toFixed(4) ?? 'N/A'}`);
    });

    g.append('text')
        .attr('x', perfBarX + 7.5)
        .attr('y', -10)
        .style('text-anchor', 'middle')
        .style('font-size', '10px')
        .style('fill', '#8b949e')
        .text('Score');

    // Island Subplots
    // Filter islands with > 1 programs
    const islands = [...new Set(dataWithEmbeddings.map(d => d.island_idx).filter(idx => idx !== null))].sort((a, b) => (a || 0) - (b || 0));
    const validIslands = islands.filter(islandId => 
        dataWithEmbeddings.filter(d => d.island_idx === islandId).length > 1
    );

    if (validIslands.length > 0) {
        const subplotsContainer = container.append('div')
            .attr('class', 'subplots-container')
            .style('margin-top', '30px')
            .style('display', 'flex')
            .style('flex-wrap', 'wrap')
            .style('gap', '20px')
            .style('justify-content', 'center');
        
        container.append('h4').text('Individual Islands - Embedding Similarity Matrices').style('margin-top', '20px').style('text-align', 'center');

        validIslands.forEach(islandId => {
            const islandData = dataWithEmbeddings.filter(d => d.island_idx === islandId);
            const islandEmbeddings = islandData.map(d => d.embedding!);
            const islandMatrix = computeSimilarityMatrix(islandEmbeddings);
            
            const subCellSize = Math.min(cellSize, 6);
            const subWidth = islandData.length * subCellSize;
            const subHeight = islandData.length * subCellSize;
            
            const subplotDiv = subplotsContainer.append('div')
                .style('border', '1px solid #30363d')
                .style('padding', '12px')
                .style('background', '#161b22')
                .style('border-radius', '8px');
            
            subplotDiv.append('h5').text(`Island ${islandId} (${islandData.length})`).style('margin', '0 0 10px 0').style('text-align', 'center').style('color', '#e6edf3').style('font-size', '13px');
            
            const subSvg = subplotDiv.append('svg')
                .attr('width', subWidth + 20) // minimal margin
                .attr('height', subHeight + 20);
            
            const subG = subSvg.append('g').attr('transform', 'translate(10,10)');
            
            islandMatrix.forEach((row, i) => {
                row.forEach((val, j) => {
                    subG.append('rect')
                        .attr('x', j * subCellSize)
                        .attr('y', i * subCellSize)
                        .attr('width', subCellSize)
                        .attr('height', subCellSize)
                        .style('fill', colorScale(val))
                        .style('stroke', 'none')
                        .on('mouseover', function(event: MouseEvent) {
                            const progA = islandData[i];
                            const progB = islandData[j];
                            const tooltip = d3.select('.embeddings-tooltip');
                            tooltip.style('opacity', 1)
                                .html(`
                                    <strong>Island ${islandId}</strong><br>
                                    ${progA.metadata.patch_name} vs ${progB.metadata.patch_name}<br>
                                    Similarity: ${val.toFixed(3)}
                                `)
                                .style('left', (event.pageX + 10) + 'px')
                                .style('top', (event.pageY - 10) + 'px');
                        })
                        .on('mouseout', () => d3.select('.embeddings-tooltip').style('opacity', 0))
                        .on('click', () => selectProgram(islandData[i]));
                });
            });
        });
    }

  }, [dataWithEmbeddings, sortBy, colorScaleName, cellSize, minVal, maxVal, selectProgram]);

  if (dataWithEmbeddings.length === 0) {
    return (
      <div className="embeddings-view empty">
        <p>No embedding data available for this evolution run.</p>
      </div>
    );
  }

  return (
    <div className="embeddings-view">
      <div className="embeddings-controls">
        <div className="control-group">
            <label>Sort by: 
                <select value={sortBy} onChange={e => setSortBy(e.target.value as any)}>
                    <option value="chronological">Chronological</option>
                    <option value="performance">Performance</option>
                </select>
            </label>
            <label>Color Scale: 
                <select value={colorScaleName} onChange={e => setColorScaleName(e.target.value)}>
                    <option value="magma">Magma</option>
                    <option value="inferno">Inferno</option>
                    <option value="plasma">Plasma</option>
                    <option value="viridis">Viridis</option>
                </select>
            </label>
            <label>Cell Size: 
                <input type="range" min="2" max="20" value={cellSize} onChange={e => setCellSize(Number(e.target.value))} />
                {cellSize}px
            </label>
        </div>
        <div className="control-group">
            <label>Min Val: <input type="number" step="0.05" value={minVal} onChange={e => setMinVal(Number(e.target.value))} /></label>
            <label>Max Val: <input type="number" step="0.05" value={maxVal} onChange={e => setMaxVal(Number(e.target.value))} /></label>
        </div>
      </div>
      <div className="embeddings-container" style={{ overflow: 'auto', height: 'calc(100% - 80px)', position: 'relative' }}>
        <div className="embeddings-tooltip" style={{position: 'fixed', opacity: 0, pointerEvents: 'none', background: 'rgba(0,0,0,0.8)', color: 'white', padding: '5px', borderRadius: '4px', fontSize: '12px', zIndex: 1000}}></div>
        <div ref={containerRef}></div>
      </div>
    </div>
  );
}
