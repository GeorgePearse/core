import { useMemo, useCallback, useState } from 'react';
import hljs from 'highlight.js/lib/core';
import python from 'highlight.js/lib/languages/python';
import rust from 'highlight.js/lib/languages/rust';
import cpp from 'highlight.js/lib/languages/cpp';
import javascript from 'highlight.js/lib/languages/javascript';
import json from 'highlight.js/lib/languages/json';
import cuda from 'highlight.js/lib/languages/cpp'; // CUDA uses C++ syntax
import 'highlight.js/styles/github-dark.css';
import { useGenesis } from '../../context/GenesisContext';
import './CodeViewerPanel.css';

// Register languages
hljs.registerLanguage('python', python);
hljs.registerLanguage('rust', rust);
hljs.registerLanguage('cpp', cpp);
hljs.registerLanguage('javascript', javascript);
hljs.registerLanguage('json', json);
hljs.registerLanguage('cuda', cuda);
hljs.registerLanguage('cu', cuda);

export default function CodeViewerPanel() {
  const { state } = useGenesis();
  const { selectedProgram } = state;
  const [copied, setCopied] = useState(false);

  // Compute highlighted HTML using hljs.highlight() for proper React integration
  const highlightedCode = useMemo(() => {
    if (!selectedProgram?.code) return null;

    const language = selectedProgram.language || 'python';
    // Map language names to highlight.js language identifiers
    const langMap: Record<string, string> = {
      python: 'python',
      rust: 'rust',
      cpp: 'cpp',
      cuda: 'cuda',
      cu: 'cuda',
      javascript: 'javascript',
      js: 'javascript',
      json: 'json',
      json5: 'json',
    };
    const hljsLang = langMap[language] || 'python';

    try {
      const result = hljs.highlight(selectedProgram.code, {
        language: hljsLang,
        ignoreIllegals: true,
      });
      return result.value;
    } catch {
      // Fallback to plain text if highlighting fails
      return selectedProgram.code
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
    }
  }, [selectedProgram?.code, selectedProgram?.language]);

  const handleCopy = useCallback(async () => {
    if (selectedProgram?.code) {
      try {
        await navigator.clipboard.writeText(selectedProgram.code);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      } catch (err) {
        console.error('Failed to copy:', err);
      }
    }
  }, [selectedProgram?.code]);

  const handleDownload = useCallback(() => {
    if (selectedProgram?.code) {
      const language = selectedProgram.language || 'python';
      const extensionMap: Record<string, string> = {
        python: 'py',
        rust: 'rs',
        cpp: 'cpp',
        cuda: 'cu',
        javascript: 'js',
        json: 'json',
        json5: 'json',
      };
      const extension = extensionMap[language] || 'txt';

      const filename = `${selectedProgram.metadata.patch_name || 'code'}_gen${selectedProgram.generation}.${extension}`;
      const blob = new Blob([selectedProgram.code], { type: 'text/plain' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    }
  }, [selectedProgram]);

  if (!selectedProgram) {
    return (
      <div className="code-viewer-panel empty">
        <p>Select a program from the table to view its code.</p>
      </div>
    );
  }

  if (!selectedProgram.code) {
    return (
      <div className="code-viewer-panel empty">
        <p>No code available for this program.</p>
      </div>
    );
  }

  const language = selectedProgram.language || 'python';
  const lines = selectedProgram.code.split('\n');
  const lineCount = lines.length;

  return (
    <div className="code-viewer-panel">
      <div className="code-controls">
        <button
          onClick={handleCopy}
          title="Copy code to clipboard"
          className={copied ? 'copied' : ''}
        >
          {copied ? 'Copied!' : 'Copy'}
        </button>
        <button onClick={handleDownload} title="Download code as file">
          Download
        </button>
        <span className="language-badge">{language}</span>
        <span className="line-count">{lineCount} lines</span>
      </div>

      <div className="code-container">
        <div className="line-numbers" aria-hidden="true">
          {lines.map((_, i) => (
            <span key={i}>{i + 1}</span>
          ))}
        </div>
        <pre className="code-content">
          <code
            className={`hljs language-${language}`}
            dangerouslySetInnerHTML={{ __html: highlightedCode || '' }}
          />
        </pre>
      </div>
    </div>
  );
}
