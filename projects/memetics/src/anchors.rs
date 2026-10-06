//! Edit-stable code anchors: a tree-sitter symbol plus a blake3 hash of its normalised text.
//!
//! Normalisation drops comments and formatting (leaf tokens joined by one space) and masks the
//! definition's own name, so a pure rename or move keeps its hash.

use tree_sitter::{Language, Node, Parser};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Symbol {
    pub name: String,
    pub start_line: usize,
    pub end_line: usize,
    pub hash: String,
    pub text: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Resolution {
    /// Exact hash hit under the anchored symbol.
    Same {
        lines: (usize, usize),
    },
    /// Exact hash hit under another symbol or path: moved or renamed.
    Moved {
        path: String,
        symbol: Option<String>,
        lines: (usize, usize),
    },
    /// Symbol hit, hash miss: edited.
    Changed {
        lines: (usize, usize),
        hash: String,
    },
    Lost,
}

struct Grammar {
    language: Language,
    separator: &'static str,
    definitions: &'static [&'static str],
    containers: &'static [&'static str],
}

const RUST_DEFINITIONS: &[&str] = &[
    "function_item",
    "function_signature_item",
    "struct_item",
    "enum_item",
    "union_item",
    "trait_item",
    "type_item",
    "const_item",
    "static_item",
    "macro_definition",
    "mod_item",
];
const TS_DEFINITIONS: &[&str] = &[
    "function_declaration",
    "generator_function_declaration",
    "class_declaration",
    "abstract_class_declaration",
    "method_definition",
    "interface_declaration",
    "type_alias_declaration",
    "enum_declaration",
    "variable_declarator",
];

fn grammar(path: &str) -> Option<Grammar> {
    let extension = path.rsplit_once('.').map(|(_, e)| e).unwrap_or_default();
    Some(match extension {
        "rs" => Grammar {
            language: tree_sitter_rust::LANGUAGE.into(),
            separator: "::",
            definitions: RUST_DEFINITIONS,
            containers: &["impl_item", "trait_item", "mod_item"],
        },
        "py" | "pyi" => Grammar {
            language: tree_sitter_python::LANGUAGE.into(),
            separator: ".",
            definitions: &["function_definition", "class_definition"],
            containers: &["class_definition"],
        },
        "ts" | "mts" | "cts" => Grammar {
            language: tree_sitter_typescript::LANGUAGE_TYPESCRIPT.into(),
            separator: ".",
            definitions: TS_DEFINITIONS,
            containers: &["class_declaration", "abstract_class_declaration"],
        },
        "tsx" | "js" | "jsx" | "mjs" | "cjs" => Grammar {
            language: tree_sitter_typescript::LANGUAGE_TSX.into(),
            separator: ".",
            definitions: TS_DEFINITIONS,
            containers: &["class_declaration", "abstract_class_declaration"],
        },
        _ => return None,
    })
}

pub fn supported(path: &str) -> bool {
    grammar(path).is_some()
}

fn short_hash(text: &str) -> String {
    blake3::hash(text.as_bytes()).to_hex()[..16].to_string()
}

fn normalise(node: Node, source: &[u8], mask: Option<(usize, usize)>, out: &mut Vec<String>) {
    if node.kind().contains("comment") {
        return;
    }
    if Some((node.start_byte(), node.end_byte())) == mask && node.child_count() == 0 {
        out.push("_".into());
        return;
    }
    if node.child_count() == 0 {
        let token = node.utf8_text(source).unwrap_or_default().trim();
        if !token.is_empty() {
            out.push(token.to_string());
        }
        return;
    }
    if Some((node.start_byte(), node.end_byte())) == mask {
        out.push("_".into());
        return;
    }
    let mut cursor = node.walk();
    for child in node.children(&mut cursor) {
        normalise(child, source, mask, out);
    }
}

fn name_node<'a>(node: Node<'a>) -> Option<Node<'a>> {
    if node.kind() == "impl_item" {
        return node.child_by_field_name("type");
    }
    node.child_by_field_name("name")
}

fn display_name(node: Node, source: &[u8]) -> Option<String> {
    let text = name_node(node)?.utf8_text(source).ok()?;
    Some(text.split('<').next().unwrap_or(text).trim().to_string())
}

fn is_definition(node: Node, grammar: &Grammar) -> bool {
    if !grammar.definitions.contains(&node.kind()) {
        return false;
    }
    if node.kind() == "variable_declarator" {
        return node.child_by_field_name("value").is_some_and(|v| {
            matches!(
                v.kind(),
                "arrow_function" | "function_expression" | "function"
            )
        });
    }
    true
}

fn collect(
    node: Node,
    source: &[u8],
    grammar: &Grammar,
    scope: &mut Vec<String>,
    out: &mut Vec<Symbol>,
) {
    let definition = is_definition(node, grammar);
    let container = grammar.containers.contains(&node.kind());
    let name = if definition || container {
        display_name(node, source)
    } else {
        None
    };
    if definition && let Some(name) = &name {
        let mut qualified = scope.clone();
        qualified.push(name.clone());
        let mask = name_node(node).map(|n| (n.start_byte(), n.end_byte()));
        let mut tokens = Vec::new();
        normalise(node, source, mask, &mut tokens);
        out.push(Symbol {
            name: qualified.join(grammar.separator),
            start_line: node.start_position().row + 1,
            end_line: node.end_position().row + 1,
            hash: short_hash(&tokens.join(" ")),
            text: node.utf8_text(source).unwrap_or_default().to_string(),
        });
    }
    let pushed = container && name.is_some();
    if pushed {
        scope.push(name.unwrap());
    }
    let mut cursor = node.walk();
    for child in node.children(&mut cursor) {
        collect(child, source, grammar, scope, out);
    }
    if pushed {
        scope.pop();
    }
}

/// All definitions in a file, with qualified names (`Type::method` in Rust, `Class.method` otherwise).
pub fn symbols(path: &str, content: &str) -> Vec<Symbol> {
    let Some(grammar) = grammar(path) else {
        return vec![];
    };
    let mut parser = Parser::new();
    if parser.set_language(&grammar.language).is_err() {
        return vec![];
    }
    let Some(tree) = parser.parse(content, None) else {
        return vec![];
    };
    let mut out = Vec::new();
    collect(
        tree.root_node(),
        content.as_bytes(),
        &grammar,
        &mut Vec::new(),
        &mut out,
    );
    out
}

/// Hash of a whole file's normalised text, for anchors without a symbol.
pub fn file_hash(path: &str, content: &str) -> String {
    if let Some(grammar) = grammar(path) {
        let mut parser = Parser::new();
        if parser.set_language(&grammar.language).is_ok()
            && let Some(tree) = parser.parse(content, None)
        {
            let mut tokens = Vec::new();
            normalise(tree.root_node(), content.as_bytes(), None, &mut tokens);
            return short_hash(&tokens.join(" "));
        }
    }
    short_hash(&content.split_whitespace().collect::<Vec<_>>().join(" "))
}

pub fn find<'a>(symbols: &'a [Symbol], name: &str) -> Option<&'a Symbol> {
    symbols.iter().find(|s| s.name == name)
}

/// The current hash and line span of an anchor in one file's content.
pub fn current(
    path: &str,
    content: &str,
    symbol: Option<&str>,
) -> Option<(String, (usize, usize), String)> {
    match symbol {
        Some(name) => {
            let all = symbols(path, content);
            find(&all, name).map(|s| (s.hash.clone(), (s.start_line, s.end_line), s.text.clone()))
        }
        None => Some((
            file_hash(path, content),
            (1, content.lines().count().max(1)),
            content.to_string(),
        )),
    }
}

/// Re-find an anchor: in its own file first, then in `others` (path, content) by hash.
pub fn resolve(
    path: &str,
    symbol: Option<&str>,
    hash: &str,
    content: Option<&str>,
    others: &[(String, String)],
) -> Resolution {
    if let Some(content) = content {
        match symbol {
            None => {
                let current = file_hash(path, content);
                let lines = (1, content.lines().count().max(1));
                return if current == hash {
                    Resolution::Same { lines }
                } else {
                    Resolution::Changed {
                        lines,
                        hash: current,
                    }
                };
            }
            Some(name) => {
                let all = symbols(path, content);
                if let Some(s) = all.iter().find(|s| s.name == name && s.hash == hash) {
                    return Resolution::Same {
                        lines: (s.start_line, s.end_line),
                    };
                }
                if let Some(s) = all.iter().find(|s| s.hash == hash) {
                    return Resolution::Moved {
                        path: path.into(),
                        symbol: Some(s.name.clone()),
                        lines: (s.start_line, s.end_line),
                    };
                }
                if let Some(s) = find(&all, name) {
                    return Resolution::Changed {
                        lines: (s.start_line, s.end_line),
                        hash: s.hash.clone(),
                    };
                }
            }
        }
    }
    if symbol.is_some() {
        for (other, text) in others.iter().filter(|(p, _)| p != path) {
            if let Some(s) = symbols(other, text).into_iter().find(|s| s.hash == hash) {
                return Resolution::Moved {
                    path: other.clone(),
                    symbol: Some(s.name),
                    lines: (s.start_line, s.end_line),
                };
            }
        }
    }
    Resolution::Lost
}

#[cfg(test)]
mod tests {
    use super::*;

    const RUST: &str = "struct Cache;\n\nimpl Cache {\n    // evict oldest\n    fn evict(&mut self, n: usize) -> usize {\n        n * 2\n    }\n}\n\nfn helper() {}\n";

    #[test]
    fn rust_symbols_are_qualified() {
        let names: Vec<String> = symbols("a.rs", RUST).into_iter().map(|s| s.name).collect();
        assert_eq!(names, ["Cache", "Cache::evict", "helper"]);
        let evict = find(&symbols("a.rs", RUST), "Cache::evict")
            .unwrap()
            .clone();
        assert_eq!((evict.start_line, evict.end_line), (5, 7));
    }

    #[test]
    fn python_and_typescript_symbols() {
        let py = "class Pruner:\n    def prune(self, x):\n        return x[:10]\n\ndef top():\n    pass\n";
        let names: Vec<String> = symbols("p.py", py).into_iter().map(|s| s.name).collect();
        assert_eq!(names, ["Pruner", "Pruner.prune", "top"]);
        let ts = "export class ToolResultPruner {\n  pruneContent(x: string): string { return x; }\n}\nexport const helper = (a: number) => a + 1;\n";
        let names: Vec<String> = symbols("p.ts", ts).into_iter().map(|s| s.name).collect();
        assert_eq!(
            names,
            [
                "ToolResultPruner",
                "ToolResultPruner.pruneContent",
                "helper"
            ]
        );
    }

    #[test]
    fn hash_ignores_comments_formatting_and_own_name() {
        let a = find(&symbols("a.rs", RUST), "Cache::evict")
            .unwrap()
            .hash
            .clone();
        let reformatted = RUST
            .replace("// evict oldest\n", "")
            .replace("n * 2", "n  *\n 2");
        assert_eq!(
            find(&symbols("a.rs", &reformatted), "Cache::evict")
                .unwrap()
                .hash,
            a
        );
        let renamed = RUST.replace("fn evict", "fn drop_oldest");
        assert_eq!(
            find(&symbols("a.rs", &renamed), "Cache::drop_oldest")
                .unwrap()
                .hash,
            a
        );
        let edited = RUST.replace("n * 2", "n * 3");
        assert_ne!(
            find(&symbols("a.rs", &edited), "Cache::evict")
                .unwrap()
                .hash,
            a
        );
    }

    #[test]
    fn resolver_same_moved_edited_lost() {
        let anchor = find(&symbols("a.rs", RUST), "Cache::evict")
            .unwrap()
            .clone();
        let resolve_in = |content: &str, others: &[(String, String)]| {
            resolve(
                "a.rs",
                Some("Cache::evict"),
                &anchor.hash,
                Some(content),
                others,
            )
        };
        let shifted = format!("\n\n{RUST}");
        assert_eq!(
            resolve_in(&shifted, &[]),
            Resolution::Same { lines: (7, 9) }
        );
        let renamed = RUST.replace("fn evict", "fn drop_oldest");
        assert!(matches!(
            resolve_in(&renamed, &[]),
            Resolution::Moved { symbol: Some(ref s), .. } if s == "Cache::drop_oldest"
        ));
        let elsewhere = vec![("b.rs".to_string(), RUST.to_string())];
        assert!(matches!(
            resolve("a.rs", Some("Cache::evict"), &anchor.hash, Some("fn other() {}"), &elsewhere),
            Resolution::Moved { ref path, .. } if path == "b.rs"
        ));
        let edited = RUST.replace("n * 2", "n * 3");
        assert!(matches!(
            resolve_in(&edited, &[]),
            Resolution::Changed { lines: (5, 7), .. }
        ));
        assert_eq!(resolve_in("fn unrelated() {}", &[]), Resolution::Lost);
        assert_eq!(
            resolve("a.rs", Some("Cache::evict"), &anchor.hash, None, &[]),
            Resolution::Lost
        );
    }
}
