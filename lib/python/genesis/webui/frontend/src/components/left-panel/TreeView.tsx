import { useEffect, useRef, useCallback } from 'react';
import * as d3 from 'd3';
import { useGenesis } from '../../context/GenesisContext';
import type { Program } from '../../types';
import './TreeView.css';

interface TreeNode extends Program {
  isUnifiedRoot?: boolean;
  isVirtual?: boolean;
  children?: TreeNode[];
}

interface D3TreeNode extends d3.HierarchyPointNode<TreeNode> {}

// Shape map for patch types
const SHAPE_MAP: Record<string, d3.SymbolType> = {
  init: d3.symbolDiamond,
  full: d3.symbolCircle,
  diff: d3.symbolSquare,
  cross: d3.symbolCross,
};

// Island colors (avoiding orange used for best path)
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

export default function TreeView() {
  const containerRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);
  const { state, selectProgram, stats, setRightTab } = useGenesis();
  const { programs, selectedProgram } = state;

  const renderTree = useCallback(() => {
    if (!containerRef.current || programs.length === 0) return;

    // Clear previous SVG
    d3.select(containerRef.current).select('svg').remove();

    const container = containerRef.current;
    const width = container.offsetWidth;
    const height = container.offsetHeight;

    // Process data to create unified root if needed
    let processedData: TreeNode[] = [...programs];
    const gen0Programs = programs.filter((p) => p.generation === 0);
    const unifiedRootId = '___unified_root___';

    if (gen0Programs.length > 1) {
      const firstGen0 = gen0Programs[0];
      const unifiedRoot: TreeNode = {
        ...firstGen0,
        id: unifiedRootId,
        parent_id: null,
        metadata: { ...firstGen0.metadata, patch_name: 'Initial Program' },
        island_idx: null,
        isUnifiedRoot: true,
      };
      processedData.push(unifiedRoot);
      processedData = processedData.map((d) => {
        if (d.generation === 0 && d.id !== unifiedRootId) {
          return { ...d, parent_id: unifiedRootId };
        }
        return d;
      });
    }

    const nodes = processedData.map((d) => ({
      ...d,
      agent_name: d.metadata.patch_name || d.agent_name || 'unnamed_agent',
    }));

    const nodeMap = new Map(nodes.map((node) => [node.id, node]));

    // Create hierarchy data
    let hierarchyData = JSON.parse(JSON.stringify(nodes));
    const rootNodes = hierarchyData.filter(
      (n: TreeNode) => !n.parent_id || !nodeMap.has(n.parent_id)
    );
    const virtualRootId = '___virtual_root___';

    const hasUnifiedRoot = rootNodes.some((n: TreeNode) => n.isUnifiedRoot);
    if (rootNodes.length > 1 && !hasUnifiedRoot) {
      hierarchyData.push({
        id: virtualRootId,
        parent_id: '',
        agent_name: 'VIRTUAL ROOT',
        isVirtual: true,
        generation: -1,
      } as TreeNode);
      rootNodes.forEach((rn: TreeNode) => {
        rn.parent_id = virtualRootId;
      });
    }

    // Create stratify layout
    const root = d3
      .stratify<TreeNode>()
      .id((d) => d.id)
      .parentId((d) => d.parent_id || undefined)(hierarchyData);

    root.sort(
      (a, b) =>
        (a.data.generation ?? 0) - (b.data.generation ?? 0) ||
        (a.data.timestamp ?? 0) - (b.data.timestamp ?? 0)
    );

    // Create tree layout
    const nodeWidth = 100;
    const nodeHeight = 200;
    const treeLayout = d3.tree<TreeNode>().nodeSize([nodeWidth, nodeHeight]);
    treeLayout(root);

    // Calculate dimensions
    let minX = Infinity,
      maxX = -Infinity;
    root.each((d) => {
      const x = d.x ?? 0;
      if (x < minX) minX = x;
      if (x > maxX) maxX = x;
    });
    const treeWidth = maxX - minX;
    const treeHeight = root.height * nodeHeight;

    const margin = { top: 100, right: 120, bottom: 100, left: 120 };

    // Create SVG
    const svg = d3
      .select(container)
      .append('svg')
      .attr('width', width)
      .attr('height', height)
      .attr(
        'viewBox',
        `${minX - margin.left} 0 ${treeWidth + margin.left + margin.right} ${treeHeight + margin.top + margin.bottom}`
      )
      .call(
        d3
          .zoom<SVGSVGElement, unknown>()
          .scaleExtent([0.1, 8])
          .on('zoom', (event) => g.attr('transform', event.transform))
      );

    svgRef.current = svg.node();

    const g = svg.append('g').attr('transform', `translate(0, ${margin.top})`);

    // Find best program
    const bestProgram = stats.bestProgram;
    const bestNodeId = bestProgram?.id;

    // Calculate ancestor path for best node
    const ancestorIds = new Set<string>();
    if (bestNodeId) {
      const descendants = root.descendants() as D3TreeNode[];
      const bestNodeD3 = descendants.find((d) => d.data.id === bestNodeId);
      if (bestNodeD3) {
        bestNodeD3.ancestors().forEach((ancestor: D3TreeNode) => {
          ancestorIds.add(ancestor.data.id);
        });
      }
    }

    // Color scale for scores
    const correctPrograms = programs.filter(
      (p) => p.correct && p.combined_score !== null
    );
    const scores = correctPrograms.map((p) => p.combined_score as number);
    const minScore = scores.length > 0 ? Math.min(...scores) : 0;
    const maxScore = scores.length > 0 ? Math.max(...scores) : 1;
    const colorScale = d3
      .scaleSequential(d3.interpolateViridis)
      .domain([minScore, maxScore]);

    // Island color scale
    const islandColorScale = d3.scaleOrdinal(ISLAND_COLORS);

    // Filter visible nodes (exclude virtual)
    const visibleLinks = root
      .links()
      .filter((d) => !(d.source.data as TreeNode).isVirtual);
    const visibleNodes = root
      .descendants()
      .filter((d) => !(d.data as TreeNode).isVirtual);

    // Draw links
    g.append('g')
      .attr('class', 'links')
      .selectAll('path')
      .data(visibleLinks)
      .enter()
      .append('path')
      .attr('class', 'link')
      .attr('fill', 'none')
      .style('stroke', (d) => {
        const sourceId = d.source.data.id;
        const targetId = d.target.data.id;
        if (ancestorIds.has(sourceId) && ancestorIds.has(targetId)) {
          return '#ff8c00';
        }
        return '#999';
      })
      .style('stroke-width', (d) => {
        const sourceId = d.source.data.id;
        const targetId = d.target.data.id;
        if (ancestorIds.has(sourceId) && ancestorIds.has(targetId)) {
          return 4;
        }
        return 1.5;
      })
      .attr('d', (d) => {
        const sourceX = (d.source as D3TreeNode).x ?? 0;
        const sourceY = (d.source as D3TreeNode).y ?? 0;
        const targetX = (d.target as D3TreeNode).x ?? 0;
        const targetY = (d.target as D3TreeNode).y ?? 0;
        return `M${sourceX},${sourceY}C${sourceX},${(sourceY + targetY) / 2} ${targetX},${(sourceY + targetY) / 2} ${targetX},${targetY}`;
      });

    // Symbol generator
    const symbol = d3.symbol().size(2500);
    const getShape = (patchType: string) =>
      SHAPE_MAP[patchType] || d3.symbolCircle;

    // Draw nodes
    const node = g
      .append('g')
      .attr('class', 'nodes')
      .selectAll('g')
      .data(visibleNodes)
      .enter()
      .append('g')
      .attr(
        'class',
        (d) =>
          `node ${d.data.id === bestNodeId ? 'best-node' : ''} ${d.data.id === selectedProgram?.id ? 'selected' : ''}`
      )
      .attr('transform', (d) => `translate(${d.x ?? 0},${d.y ?? 0})`)
      .style('cursor', 'pointer')
      .on('click', (_, d) => {
        let originalProgram = programs.find((p) => p.id === d.data.id);

        // Handle unified root node - select the first gen0 program
        if (!originalProgram && d.data.isUnifiedRoot) {
          originalProgram = programs.find((p) => p.generation === 0);
        }

        if (originalProgram) {
          selectProgram(originalProgram);
          setRightTab('code-viewer');
        }
      });

    // Draw node shapes
    node
      .append('path')
      .attr('d', (d) => {
        if (d.data.isUnifiedRoot) {
          symbol.type(d3.symbolStar).size(750);
        } else {
          symbol.type(getShape(d.data.metadata?.patch_type || 'full'));
        }
        return symbol() || '';
      })
      .style('fill', (d) => {
        if (d.data.isUnifiedRoot) return '#9b59b6';
        if (d.data.id === bestNodeId) return '#ffd700';
        if (!d.data.correct) return '#e74c3c';
        const score = d.data.combined_score;
        if (score !== null && !isNaN(score)) {
          return colorScale(score);
        }
        return '#3498db';
      })
      .style('stroke', (d) => {
        if (ancestorIds.has(d.data.id) && d.data.correct) {
          return '#ff8c00';
        }
        return '#000';
      })
      .style('stroke-width', (d) => (ancestorIds.has(d.data.id) ? 4 : 3))
      .style('filter', (d) =>
        d.data.id === bestNodeId
          ? 'drop-shadow(0px 3px 6px rgba(255, 140, 0, 0.5))'
          : 'drop-shadow(0px 2px 4px rgba(0,0,0,0.2))'
      );

    // Add pulse ring for best node
    node
      .filter((d) => d.data.id === bestNodeId)
      .insert('circle', ':first-child')
      .attr('r', 24)
      .style('fill', 'none')
      .style('stroke', '#ff8c00')
      .style('stroke-width', 3)
      .style('stroke-dasharray', '5,3')
      .style('opacity', 0.8);

    // Add generation text
    node
      .append('text')
      .attr('dy', '0.75em')
      .attr('text-anchor', 'middle')
      .style('font-size', '24px')
      .style('font-weight', 'bold')
      .style('fill', 'white')
      .style('pointer-events', 'none')
      .text((d) => d.data.generation);

    // Add island indicators
    const islandNodes = node.filter(
      (d) => d.data.island_idx !== null && d.data.island_idx !== undefined
    );

    islandNodes
      .append('rect')
      .attr('x', -15)
      .attr('y', -35)
      .attr('width', 30)
      .attr('height', 20)
      .attr('rx', 4)
      .style('fill', (d) => islandColorScale(String(d.data.island_idx)))
      .style('stroke', '#2c3e50')
      .style('stroke-width', '1px');

    islandNodes
      .append('text')
      .attr('x', 0)
      .attr('y', -15)
      .attr('text-anchor', 'middle')
      .attr('dy', '0.35em')
      .style('font-size', '17px')
      .style('font-weight', 'bold')
      .style('fill', 'white')
      .style('pointer-events', 'none')
      .text((d) => `I${d.data.island_idx}`);

    // Add tooltips
    node
      .on('mouseover', (_, d) => {
        const tooltip = d3.select('.tree-tooltip');
        tooltip.style('opacity', 1).html(`
          <strong>${d.data.metadata?.patch_name || 'Unknown'}</strong><br>
          Score: ${d.data.combined_score?.toFixed(4) || 'N/A'}<br>
          Type: ${d.data.metadata?.patch_type || 'N/A'}<br>
          Island: ${d.data.island_idx ?? 'N/A'}
        `);
      })
      .on('mousemove', (event) => {
        d3.select('.tree-tooltip')
          .style('left', event.pageX + 15 + 'px')
          .style('top', event.pageY - 10 + 'px');
      })
      .on('mouseout', () => {
        d3.select('.tree-tooltip').style('opacity', 0);
      });
  }, [programs, selectedProgram, stats.bestProgram, selectProgram, setRightTab]);

  useEffect(() => {
    renderTree();

    // Handle window resize
    const handleResize = () => {
      renderTree();
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [renderTree]);

  return (
    <div className="tree-view-container" ref={containerRef}>
      <div className="tree-tooltip" />
      <div className="tree-legend">
        <div className="legend-section">
          <h5>Nodes</h5>
          <div className="legend-item">
            <svg width="16" height="16">
              <circle
                cx="8"
                cy="8"
                r="6"
                fill="#ffd700"
                stroke="#ff8c00"
                strokeWidth="3"
              />
            </svg>
            <span>Best</span>
          </div>
          <div className="legend-item">
            <svg width="16" height="16">
              <circle
                cx="8"
                cy="8"
                r="6"
                fill="#e74c3c"
                stroke="#c0392b"
                strokeWidth="2"
              />
            </svg>
            <span>Error</span>
          </div>
        </div>
      </div>
    </div>
  );
}
