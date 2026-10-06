import type { Program } from '../types';

export interface ParetoMetric {
  name: string;
  path: string;
  objective: 'min' | 'max';
}

export interface ParetoPoint {
  x: number;
  y: number;
  program: Program;
}

export interface ParetoData {
  allPoints: ParetoPoint[];
  paretoPoints: ParetoPoint[];
}

/**
 * Get a nested value from an object using dot notation
 * e.g., getNestedValue(obj, 'public_metrics.accuracy') -> obj.public_metrics.accuracy
 */
export function getNestedValue(obj: unknown, path: string): unknown {
  if (!path) return undefined;
  const parts = path.split('.');
  let current: unknown = obj;
  for (const part of parts) {
    if (current === null || typeof current === 'undefined') return undefined;
    current = (current as Record<string, unknown>)[part];
  }
  return current;
}

/**
 * Discover all numeric metrics available across programs
 */
export function getAvailableParetoMetrics(programs: Program[]): ParetoMetric[] {
  if (!programs || programs.length === 0) return [];

  const metricsMap = new Map<string, ParetoMetric>();

  const addMetric = (program: Program, path: string) => {
    const value = getNestedValue(program, path);
    if (typeof value === 'number' && !metricsMap.has(path)) {
      // Create a human-readable name
      let name = path
        .split('.')
        .map((s) => s.charAt(0).toUpperCase() + s.slice(1))
        .join(' ');
      name = name.replace(/_/g, ' ');

      if (path.startsWith('public_metrics.')) {
        name = `Public: ${path.split('.')[1]}`;
      }
      if (path.startsWith('private_metrics.')) {
        name = `Private: ${path.split('.')[1]}`;
      }

      // Infer default objective
      let objective: 'min' | 'max' = 'max';
      const key = path.split('.').pop() || '';
      if (
        key.includes('cost') ||
        key.includes('time') ||
        key.includes('complexity') ||
        key.includes('latency')
      ) {
        objective = 'min';
      }

      metricsMap.set(path, { name, path, objective });
    }
  };

  const discoverInObject = (
    program: Program,
    subObj: Record<string, unknown> | null,
    prefix: string
  ) => {
    if (!subObj) return;
    for (const key in subObj) {
      if (typeof subObj[key] === 'number') {
        addMetric(program, `${prefix}.${key}`);
      }
    }
  };

  programs.forEach((p) => {
    addMetric(p, 'combined_score');
    addMetric(p, 'complexity');
    if (p.metadata) {
      addMetric(p, 'metadata.api_cost');
      addMetric(p, 'metadata.embed_cost');
      addMetric(p, 'metadata.novelty_cost');
      addMetric(p, 'metadata.meta_cost');
    }
    discoverInObject(
      p,
      p.public_metrics as Record<string, unknown> | null,
      'public_metrics'
    );
    discoverInObject(
      p,
      p.private_metrics as Record<string, unknown> | null,
      'private_metrics'
    );
  });

  return Array.from(metricsMap.values());
}

/**
 * Calculate which points lie on the Pareto frontier
 */
export function calculateParetoFront(
  programs: Program[],
  xMetric: ParetoMetric,
  yMetric: ParetoMetric
): ParetoData {
  // Extract all points with valid numeric values for both metrics
  const allPoints: ParetoPoint[] = programs
    .map((p) => {
      const x = getNestedValue(p, xMetric.path);
      const y = getNestedValue(p, yMetric.path);
      if (typeof x === 'number' && typeof y === 'number') {
        return { x, y, program: p };
      }
      return null;
    })
    .filter((p): p is ParetoPoint => p !== null);

  // Only consider correct programs for Pareto optimality
  const correctPoints = allPoints.filter((p) => p.program.correct);

  // Find Pareto-optimal points among correct programs
  const paretoPoints = correctPoints.filter((p1) => {
    return !correctPoints.some((p2) => {
      if (p1 === p2) return false;

      // Check if p2 dominates p1
      const xP2Better =
        xMetric.objective === 'min' ? p2.x < p1.x : p2.x > p1.x;
      const yP2Better =
        yMetric.objective === 'min' ? p2.y < p1.y : p2.y > p1.y;
      const xEqual = p2.x === p1.x;
      const yEqual = p2.y === p1.y;

      // p2 dominates p1 if p2 is better or equal in both objectives and strictly better in at least one
      if (
        (xP2Better && (yP2Better || yEqual)) ||
        (yP2Better && (xP2Better || xEqual))
      ) {
        return true;
      }
      return false;
    });
  });

  return { allPoints, paretoPoints };
}

/**
 * Format a numeric value for display
 */
export function formatMetricValue(value: number | null | undefined): string {
  if (value === null || value === undefined) return 'N/A';
  if (Number.isInteger(value)) return value.toString();
  if (Math.abs(value) < 0.001 || Math.abs(value) >= 10000) {
    return value.toExponential(3);
  }
  return value.toFixed(4);
}
