import express from 'express';
import cors from 'cors';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';
import { glob } from 'glob';
import Database from 'better-sqlite3';
import { marked } from 'marked';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const PORT = process.env.PORT || 8000;

// Search root for databases - relative to Genesis root
const GENESIS_ROOT = path.resolve(__dirname, '../../../../');
const SEARCH_ROOT = process.env.SEARCH_ROOT || path.join(GENESIS_ROOT, 'results');

// Cache for program data (5 second TTL)
const cache = new Map<string, { data: unknown; timestamp: number }>();
const CACHE_TTL = 5000;

app.use(cors());
app.use(express.json());

// Logging middleware
app.use((req, res, next) => {
  console.log(`[${new Date().toISOString()}] ${req.method} ${req.url}`);
  next();
});

// Types
interface DatabaseInfo {
  path: string;
  name: string;
  actual_path: string;
  sort_key?: string;
  stats?: {
    total: number;
    working: number;
  };
}

interface MetaFile {
  generation: number;
  filename: string;
  path: string;
}

interface MetaContent {
  generation: number;
  filename: string;
  content: string;
}

// Helper: Parse JSON field safely
function parseJsonField(value: string | null): unknown {
  if (!value) return null;
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}

// Helper: Replace NaN/Infinity with null in JSON
function sanitizeForJson(obj: unknown): unknown {
  if (typeof obj === 'number') {
    if (!isFinite(obj)) return null;
    return obj;
  }
  if (Array.isArray(obj)) {
    return obj.map(sanitizeForJson);
  }
  if (obj && typeof obj === 'object') {
    const result: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(obj)) {
      result[key] = sanitizeForJson(value);
    }
    return result;
  }
  return obj;
}

// Helper: Extract date from path for sorting
function extractSortKey(filepath: string): string {
  const match = filepath.match(/_(\d{8}_\d{6})/);
  return match ? match[1] : '0';
}

// Helper: Resolve database path
function resolveDatabasePath(dbPath: string): string {
  const normalized = path.normalize(dbPath).replace(/^(\.\.(\/|\\|$))+/, '');
  const parts = normalized.split('/');

  // Try with and without prefix
  const candidates = [
    path.join(SEARCH_ROOT, normalized),
    path.join(SEARCH_ROOT, parts.slice(1).join('/')),
    path.join(GENESIS_ROOT, normalized),
  ];

  const allowedRoots = [path.resolve(SEARCH_ROOT), path.resolve(GENESIS_ROOT)];

  for (const candidate of candidates) {
    const resolved = path.resolve(candidate);
    const withinAllowedRoot = allowedRoots.some((root) => resolved === root || resolved.startsWith(`${root}${path.sep}`));
    if (!withinAllowedRoot) {
      continue;
    }
    if (fs.existsSync(resolved)) {
      return resolved;
    }
  }

  return path.resolve(path.join(SEARCH_ROOT, normalized));
}

// GET /list_databases
app.get('/list_databases', async (req, res) => {
  try {
    console.log(`[SERVER] Scanning for databases in: ${SEARCH_ROOT}`);

    const pattern = path.join(SEARCH_ROOT, '**/*.{db,sqlite}');
    const files = await glob(pattern, { nodir: true });

    const taskName = path.basename(SEARCH_ROOT);

    const databases: DatabaseInfo[] = files.map((file) => {
      const relativePath = path.relative(SEARCH_ROOT, file);
      const parentDir = path.dirname(relativePath);
      const filename = path.basename(file, path.extname(file));

      // Get stats for this database
      let stats = { total: 0, working: 0 };
      try {
        const db = new Database(file, { readonly: true });
        try {
          const totalRow = db.prepare('SELECT COUNT(*) as count FROM programs').get() as { count: number };
          const workingRow = db.prepare('SELECT COUNT(*) as count FROM programs WHERE correct = 1').get() as { count: number };
          stats = {
            total: totalRow.count,
            working: workingRow.count,
          };
        } catch (e) {
          console.error(`[SERVER] Error querying stats for ${file}:`, e);
        } finally {
          db.close();
        }
      } catch (e) {
        console.error(`[SERVER] Error opening database ${file}:`, e);
      }

      return {
        path: `${taskName}/${relativePath}`,
        name: `${filename} - ${parentDir}`,
        actual_path: relativePath,
        sort_key: extractSortKey(relativePath),
        stats,
      };
    });

    // Sort by date (newest first)
    databases.sort((a, b) => (b.sort_key || '0').localeCompare(a.sort_key || '0'));

    console.log(`[SERVER] Found ${databases.length} databases`);
    res.json(databases);
  } catch (error) {
    console.error('[SERVER] Error listing databases:', error);
    res.status(500).json({ error: 'Failed to list databases' });
  }
});

// GET /get_programs?db_path=X
app.get('/get_programs', (req, res) => {
  const dbPath = req.query.db_path as string;

  if (!dbPath) {
    return res.status(400).json({ error: 'db_path parameter required' });
  }

  // Check cache
  const cacheKey = `programs:${dbPath}`;
  const cached = cache.get(cacheKey);
  if (cached && Date.now() - cached.timestamp < CACHE_TTL) {
    console.log(`[SERVER] Returning cached data for ${dbPath}`);
    return res.json(cached.data);
  }

  const resolvedPath = resolveDatabasePath(dbPath);
  console.log(`[SERVER] Loading programs from: ${resolvedPath}`);

  if (!fs.existsSync(resolvedPath)) {
    console.error(`[SERVER] Database not found: ${resolvedPath}`);
    return res.status(404).json({ error: 'Database not found' });
  }

  let db: Database.Database | null = null;

  try {
    db = new Database(resolvedPath, { readonly: true });
    db.pragma('busy_timeout = 10000');

    const rows = db.prepare(`
      SELECT p.*,
             CASE WHEN a.program_id IS NOT NULL THEN 1 ELSE 0 END as in_archive
      FROM programs p
      LEFT JOIN archive a ON p.id = a.program_id
    `).all() as Record<string, unknown>[];

    const programs = rows.map((row) => ({
      id: row.id,
      parent_id: row.parent_id,
      code: row.code,
      language: row.language || 'python',
      generation: row.generation,
      timestamp: row.timestamp,
      agent_name: (parseJsonField(row.metadata as string) as Record<string, unknown>)?.patch_name || 'unknown',
      combined_score: row.combined_score,
      public_metrics: parseJsonField(row.public_metrics as string),
      private_metrics: parseJsonField(row.private_metrics as string),
      text_feedback: row.text_feedback,
      metadata: parseJsonField(row.metadata as string) || {},
      complexity: row.complexity,
      embedding: parseJsonField(row.embedding as string),
      embedding_pca_2d: parseJsonField(row.embedding_pca_2d as string),
      embedding_pca_3d: parseJsonField(row.embedding_pca_3d as string),
      island_idx: row.island_idx,
      correct: Boolean(row.correct),
      in_archive: Boolean(row.in_archive),
      code_diff: row.code_diff,
    }));

    const sanitized = sanitizeForJson(programs);

    // Cache the result
    cache.set(cacheKey, { data: sanitized, timestamp: Date.now() });

    console.log(`[SERVER] Loaded ${programs.length} programs`);
    res.json(sanitized);
  } catch (error) {
    console.error('[SERVER] Database error:', error);
    const message = error instanceof Error ? error.message : 'Unknown error';

    if (message.includes('locked') || message.includes('busy')) {
      return res.status(503).json({ error: 'Database temporarily unavailable' });
    }

    res.status(500).json({ error: 'Database error' });
  } finally {
    db?.close();
  }
});

// GET /get_meta_files?db_path=X
app.get('/get_meta_files', (req, res) => {
  const dbPath = req.query.db_path as string;

  if (!dbPath) {
    return res.status(400).json({ error: 'db_path parameter required' });
  }

  const resolvedPath = resolveDatabasePath(dbPath);
  const dbDir = path.dirname(resolvedPath);

  if (!fs.existsSync(dbDir)) {
    return res.status(404).json([]);
  }

  try {
    const files = fs.readdirSync(dbDir);
    const metaFiles: MetaFile[] = [];

    for (const file of files) {
      const match = file.match(/^meta_(\d+)\.txt$/);
      if (match) {
        metaFiles.push({
          generation: parseInt(match[1], 10),
          filename: file,
          path: path.join(dbDir, file),
        });
      }
    }

    // Sort by generation
    metaFiles.sort((a, b) => a.generation - b.generation);

    console.log(`[SERVER] Found ${metaFiles.length} meta files`);
    res.json(metaFiles);
  } catch (error) {
    console.error('[SERVER] Error reading meta files:', error);
    res.status(500).json({ error: 'Failed to read meta files' });
  }
});

// GET /get_meta_content?db_path=X&generation=N
app.get('/get_meta_content', (req, res) => {
  const dbPath = req.query.db_path as string;
  const generation = req.query.generation as string;

  if (!dbPath || !generation) {
    return res.status(400).json({ error: 'db_path and generation parameters required' });
  }

  if (!/^\d+$/.test(generation)) {
    return res.status(400).json({ error: 'generation must be an integer' });
  }

  const resolvedPath = resolveDatabasePath(dbPath);
  const dbDir = path.dirname(resolvedPath);
  const metaFilename = `meta_${generation}.txt`;
  const metaPath = path.join(dbDir, metaFilename);

  if (!fs.existsSync(metaPath)) {
    return res.status(404).json({ error: 'Meta file not found' });
  }

  try {
    const content = fs.readFileSync(metaPath, 'utf-8');

    const result: MetaContent = {
      generation: parseInt(generation, 10),
      filename: metaFilename,
      content,
    };

    res.json(result);
  } catch (error) {
    console.error('[SERVER] Error reading meta content:', error);
    res.status(500).json({ error: 'Failed to read meta content' });
  }
});

// GET /download_meta_pdf?db_path=X&generation=N
app.get('/download_meta_pdf', (req, res) => {
  const dbPath = req.query.db_path as string;
  const generation = req.query.generation as string;

  if (!dbPath || !generation) {
    return res.status(400).json({ error: 'db_path and generation parameters required' });
  }

  if (!/^\d+$/.test(generation)) {
    return res.status(400).json({ error: 'generation must be an integer' });
  }

  const resolvedPath = resolveDatabasePath(dbPath);
  const dbDir = path.dirname(resolvedPath);
  const metaFilename = `meta_${generation}.txt`;
  const metaPath = path.join(dbDir, metaFilename);

  if (!fs.existsSync(metaPath)) {
    return res.status(404).json({ error: 'Meta file not found' });
  }

  try {
    const content = fs.readFileSync(metaPath, 'utf-8');
    const html = marked(content) as string;

    // For now, return HTML instead of PDF (PDF generation would require puppeteer)
    res.setHeader('Content-Type', 'text/html');
    res.setHeader('Content-Disposition', `attachment; filename="meta_${generation}.html"`);
    res.send(`
      <!DOCTYPE html>
      <html>
        <head>
          <meta charset="utf-8">
          <title>Meta Generation ${generation}</title>
          <style>
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 800px; margin: 40px auto; padding: 20px; }
            pre { background: #f5f5f5; padding: 15px; overflow-x: auto; }
            code { background: #f5f5f5; padding: 2px 6px; }
          </style>
        </head>
        <body>${html}</body>
      </html>
    `);
  } catch (error) {
    console.error('[SERVER] Error generating PDF:', error);
    res.status(500).json({ error: 'Failed to generate PDF' });
  }
});

// Serve static files in production
if (process.env.NODE_ENV === 'production') {
  const distPath = path.join(__dirname, '../dist');
  app.use(express.static(distPath));
  app.get('*', (req, res) => {
    res.sendFile(path.join(distPath, 'index.html'));
  });
}

// Start server
app.listen(PORT, () => {
  console.log(`
====================================
  Genesis API Server
====================================
  Port:        ${PORT}
  Search Root: ${SEARCH_ROOT}
  Genesis:     ${GENESIS_ROOT}
====================================
  `);
});
