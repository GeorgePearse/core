//! Dead code analysis reporting and visualization
//!
//! Provides functionality to export dead code analysis results in various formats:
//! - JSON: Machine-readable format for tool integration
//! - HTML: Human-readable report with styling
//! - Graphviz DOT: Call graph visualization

use serde::{Deserialize, Serialize};

/// Dead code analysis report
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeadCodeReport {
    /// Package name
    pub package: String,
    /// Total functions analyzed
    pub total_functions: usize,
    /// Dead functions found
    pub dead_functions: Vec<DeadFunction>,
    /// Live functions (reachable from entry points)
    pub live_functions: Vec<String>,
    /// Entry points (functions with code execution)
    pub entry_points: Vec<String>,
    /// Public exports (from `__all__`)
    pub public_exports: Vec<String>,
}

/// A dead code function
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeadFunction {
    /// Function name
    pub name: String,
    /// Why it's considered dead
    pub reason: String,
}

impl DeadCodeReport {
    /// Create a new dead code report
    #[must_use]
    pub fn new(
        package: String,
        total_functions: usize,
        dead_functions: Vec<(String, String)>,
        live_functions: Vec<String>,
        entry_points: Vec<String>,
        public_exports: Vec<String>,
    ) -> Self {
        let dead = dead_functions
            .into_iter()
            .map(|(name, reason)| DeadFunction { name, reason })
            .collect();

        Self {
            package,
            total_functions,
            dead_functions: dead,
            live_functions,
            entry_points,
            public_exports,
        }
    }

    /// Export as JSON
    #[must_use]
    pub fn to_json(&self) -> String {
        serde_json::to_string_pretty(self).unwrap_or_default()
    }

    /// Export as HTML report
    #[must_use]
    pub fn to_html(&self) -> String {
        let dead_count = self.dead_functions.len();
        let live_count = self.live_functions.len();
        let coverage = if self.total_functions > 0 {
            ((live_count as f64 / self.total_functions as f64) * 100.0) as u32
        } else {
            0
        };

        let dead_rows = self
            .dead_functions
            .iter()
            .map(|f| {
                format!(
                    "    <tr><td>{}</td><td>{}</td></tr>\n",
                    escape_html(&f.name),
                    escape_html(&f.reason)
                )
            })
            .collect::<String>();

        let entry_points = self
            .entry_points
            .iter()
            .map(|f| format!("      <li>{}</li>\n", escape_html(f)))
            .collect::<String>();

        let exports = self
            .public_exports
            .iter()
            .map(|f| format!("      <li>{}</li>\n", escape_html(f)))
            .collect::<String>();

        format!(
            r#"<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Dead Code Report - {}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 20px; }}
        .header {{ background: #f5f5f5; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}
        .stats {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin: 20px 0; }}
        .stat {{ background: #f0f0f0; padding: 15px; border-radius: 8px; text-align: center; }}
        .stat-label {{ font-size: 12px; color: #666; margin-bottom: 5px; }}
        .stat-value {{ font-size: 32px; font-weight: bold; color: #333; }}
        .stat.dead {{ background: #ffe6e6; color: #d32f2f; }}
        .stat.live {{ background: #e8f5e9; color: #388e3c; }}
        .stat.coverage {{ background: #e3f2fd; color: #1976d2; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ text-align: left; padding: 12px; border-bottom: 1px solid #ddd; }}
        th {{ background: #f5f5f5; font-weight: 600; }}
        .section {{ margin: 30px 0; }}
        .section h2 {{ border-bottom: 2px solid #1976d2; padding-bottom: 10px; }}
        ul {{ list-style-type: none; padding: 0; }}
        li {{ padding: 8px 0; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Dead Code Analysis Report</h1>
        <p><strong>Package:</strong> {}</p>
    </div>

    <div class="stats">
        <div class="stat live">
            <div class="stat-label">Live Functions</div>
            <div class="stat-value">{}</div>
        </div>
        <div class="stat dead">
            <div class="stat-label">Dead Functions</div>
            <div class="stat-value">{}</div>
        </div>
        <div class="stat coverage">
            <div class="stat-label">Code Coverage</div>
            <div class="stat-value">{}%</div>
        </div>
        <div class="stat">
            <div class="stat-label">Total Functions</div>
            <div class="stat-value">{}</div>
        </div>
    </div>

    <div class="section">
        <h2>Dead Code Functions</h2>
        <table>
            <thead>
                <tr>
                    <th>Function Name</th>
                    <th>Reason</th>
                </tr>
            </thead>
            <tbody>
{}            </tbody>
        </table>
    </div>

    <div class="section">
        <h2>Entry Points (Live Code)</h2>
        <ul>
{}        </ul>
    </div>

    <div class="section">
        <h2>Public Exports (__all__)</h2>
        <ul>
{}        </ul>
    </div>
</body>
</html>"#,
            escape_html(&self.package),
            escape_html(&self.package),
            live_count,
            dead_count,
            coverage,
            self.total_functions,
            dead_rows,
            entry_points,
            exports
        )
    }

    /// Export as Graphviz DOT format
    #[must_use]
    pub fn to_dot(&self, call_graph: Option<&CallGraphDot>) -> String {
        let mut dot = String::from("digraph CallGraph {\n");
        dot.push_str("  rankdir=LR;\n");
        dot.push_str("  node [shape=box, style=filled];\n\n");

        // Add entry points in green
        if !self.entry_points.is_empty() {
            dot.push_str("  // Entry Points\n");
            for entry in &self.entry_points {
                dot.push_str(&format!(
                    "  \"{}\" [fillcolor=\"#90EE90\", label=\"{}\"];\n",
                    escape_dot(entry),
                    escape_dot(entry)
                ));
            }
            dot.push('\n');
        }

        // Add live functions in blue
        if !self.live_functions.is_empty() {
            dot.push_str("  // Live Functions\n");
            for live in &self.live_functions {
                if !self.entry_points.contains(live) {
                    dot.push_str(&format!(
                        "  \"{}\" [fillcolor=\"#ADD8E6\", label=\"{}\"];\n",
                        escape_dot(live),
                        escape_dot(live)
                    ));
                }
            }
            dot.push('\n');
        }

        // Add dead functions in red
        if !self.dead_functions.is_empty() {
            dot.push_str("  // Dead Functions\n");
            for dead in &self.dead_functions {
                dot.push_str(&format!(
                    "  \"{}\" [fillcolor=\"#FFB6C6\", label=\"{}\"];\n",
                    escape_dot(&dead.name),
                    escape_dot(&dead.name)
                ));
            }
            dot.push('\n');
        }

        // Add edges if call graph provided
        if let Some(graph) = call_graph {
            dot.push_str("  // Call Graph Edges\n");
            for (from, to) in &graph.edges {
                dot.push_str(&format!(
                    "  \"{}\" -> \"{}\";\n",
                    escape_dot(from),
                    escape_dot(to)
                ));
            }
        }

        dot.push_str("}\n");
        dot
    }
}

/// Call graph representation for visualization
#[derive(Debug, Clone)]
pub struct CallGraphDot {
    /// Edges as (caller, callee) pairs
    pub edges: Vec<(String, String)>,
}

impl CallGraphDot {
    /// Create a new call graph
    #[must_use]
    pub fn new(edges: Vec<(String, String)>) -> Self {
        Self { edges }
    }
}

/// Escape HTML special characters
fn escape_html(s: &str) -> String {
    s.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&#39;")
}

/// Escape Graphviz special characters
fn escape_dot(s: &str) -> String {
    s.replace('"', "\\\"").replace('\n', "\\n")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_dead_code_report_json() {
        let report = DeadCodeReport::new(
            "test_package".to_string(),
            5,
            vec![(
                "unused_func".to_string(),
                "Unreachable from entry points".to_string(),
            )],
            vec!["helper".to_string(), "process".to_string()],
            vec!["test_main".to_string()],
            vec!["public_api".to_string()],
        );

        let json = report.to_json();
        assert!(json.contains("test_package"));
        assert!(json.contains("unused_func"));
        assert!(json.contains("5"));
    }

    #[test]
    fn test_dead_code_report_html() {
        let report = DeadCodeReport::new(
            "test_package".to_string(),
            5,
            vec![(
                "unused_func".to_string(),
                "Unreachable from entry points".to_string(),
            )],
            vec!["helper".to_string()],
            vec!["test_main".to_string()],
            vec!["public_api".to_string()],
        );

        let html = report.to_html();
        assert!(html.contains("<!DOCTYPE html>"));
        assert!(html.contains("test_package"));
        assert!(html.contains("unused_func"));
        assert!(html.contains("Dead Code Analysis Report"));
    }

    #[test]
    fn test_dead_code_report_dot() {
        let report = DeadCodeReport::new(
            "test_package".to_string(),
            5,
            vec![(
                "unused_func".to_string(),
                "Unreachable from entry points".to_string(),
            )],
            vec!["helper".to_string()],
            vec!["test_main".to_string()],
            vec!["public_api".to_string()],
        );

        let graph = CallGraphDot::new(vec![
            ("test_main".to_string(), "helper".to_string()),
            ("helper".to_string(), "process".to_string()),
        ]);

        let dot = report.to_dot(Some(&graph));
        assert!(dot.contains("digraph CallGraph"));
        assert!(dot.contains("test_main"));
        assert!(dot.contains("unused_func"));
    }
}
