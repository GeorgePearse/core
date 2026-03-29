import { useState, useEffect, useCallback } from 'react';
import { marked } from 'marked';
import { useGenesis } from '../../context/GenesisContext';
import { getMetaFiles, getMetaContent, getMetaPdfUrl } from '../../services/api';
import type { MetaFile, MetaContent } from '../../types';
import './ScratchpadPanel.css';

const SUB_TABS = [
  { id: 'individual-programs', label: 'Individual Programs' },
  { id: 'global-insights', label: 'Global Insights' },
  { id: 'meta-recommendations', label: 'Meta Recommendations' },
];

interface ParsedSections {
  individualPrograms: string;
  globalInsights: string;
  metaRecommendations: string;
}

export default function ScratchpadPanel() {
  const { state } = useGenesis();
  const { currentDbPath } = state;

  const [metaFiles, setMetaFiles] = useState<MetaFile[]>([]);
  const [selectedGeneration, setSelectedGeneration] = useState<number | null>(
    null
  );
  const [content, setContent] = useState<MetaContent | null>(null);
  const [parsedSections, setParsedSections] = useState<ParsedSections | null>(
    null
  );
  const [activeSubTab, setActiveSubTab] = useState('individual-programs');
  const [isLoading, setIsLoading] = useState(false);

  // Load meta files when database changes
  useEffect(() => {
    if (!currentDbPath) {
      setMetaFiles([]);
      setContent(null);
      return;
    }

    setIsLoading(true);
    getMetaFiles(currentDbPath)
      .then((files) => {
        setMetaFiles(files);
        if (files.length > 0) {
          // Select highest generation by default
          const maxGen = Math.max(...files.map((f) => f.generation));
          setSelectedGeneration(maxGen);
        }
      })
      .catch(console.error)
      .finally(() => setIsLoading(false));
  }, [currentDbPath]);

  // Load content when generation changes
  useEffect(() => {
    if (!currentDbPath || selectedGeneration === null) {
      setContent(null);
      return;
    }

    setIsLoading(true);
    getMetaContent(currentDbPath, selectedGeneration)
      .then((data) => {
        setContent(data);
        // Parse content into sections
        const sections = parseMetaIntoSections(data.content);
        setParsedSections(sections);
      })
      .catch(console.error)
      .finally(() => setIsLoading(false));
  }, [currentDbPath, selectedGeneration]);

  const handleRefresh = useCallback(() => {
    if (currentDbPath) {
      setIsLoading(true);
      getMetaFiles(currentDbPath)
        .then(setMetaFiles)
        .catch(console.error)
        .finally(() => setIsLoading(false));
    }
  }, [currentDbPath]);

  const handleDownloadPdf = useCallback(() => {
    if (currentDbPath && selectedGeneration !== null) {
      window.open(getMetaPdfUrl(currentDbPath, selectedGeneration), '_blank');
    }
  }, [currentDbPath, selectedGeneration]);

  if (!currentDbPath) {
    return (
      <div className="scratchpad-panel empty">
        <p>Select a database to view scratchpad.</p>
      </div>
    );
  }

  if (metaFiles.length === 0 && !isLoading) {
    return (
      <div className="scratchpad-panel empty">
        <p>No meta analysis files found for this database.</p>
      </div>
    );
  }

  const minGen = metaFiles.length > 0 ? Math.min(...metaFiles.map((f) => f.generation)) : 0;
  const maxGen = metaFiles.length > 0 ? Math.max(...metaFiles.map((f) => f.generation)) : 0;

  const renderSectionContent = () => {
    if (!parsedSections) return null;

    let html = '';
    switch (activeSubTab) {
      case 'individual-programs':
        html = parsedSections.individualPrograms || '<p>No content available.</p>';
        break;
      case 'global-insights':
        html = parsedSections.globalInsights || '<p>No content available.</p>';
        break;
      case 'meta-recommendations':
        html = parsedSections.metaRecommendations || '<p>No content available.</p>';
        break;
    }

    return <div className="meta-content-body" dangerouslySetInnerHTML={{ __html: html }} />;
  };

  return (
    <div className="scratchpad-panel">
      <div className="scratchpad-controls">
        <div className="generation-control">
          <label>Generation:</label>
          <input
            type="range"
            min={minGen}
            max={maxGen}
            value={selectedGeneration || minGen}
            onChange={(e) => setSelectedGeneration(Number(e.target.value))}
            disabled={metaFiles.length === 0}
          />
          <span className="gen-value">{selectedGeneration}</span>
        </div>

        <button onClick={handleRefresh} disabled={isLoading}>
          🔄 Refresh
        </button>
        <button onClick={handleDownloadPdf} disabled={!content}>
          📄 Download PDF
        </button>
      </div>

      <div className="sub-tabs">
        {SUB_TABS.map((tab) => (
          <button
            key={tab.id}
            className={`sub-tab ${activeSubTab === tab.id ? 'active' : ''}`}
            onClick={() => setActiveSubTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="scratchpad-content">
        {isLoading ? (
          <p className="loading">Loading...</p>
        ) : content ? (
          <>
            <div className="content-header">
              <h5>
                Scratchpad - Generation {content.generation}
              </h5>
              <span className="filename">{content.filename}</span>
            </div>
            {renderSectionContent()}
          </>
        ) : (
          <p>No content available.</p>
        )}
      </div>
    </div>
  );
}

function parseMetaIntoSections(content: string): ParsedSections {
  const sections: ParsedSections = {
    individualPrograms: '',
    globalInsights: '',
    metaRecommendations: '',
  };

  const parts = content.split(
    /^#\s*(INDIVIDUAL PROGRAM SUMMARIES|GLOBAL INSIGHTS SCRATCHPAD|META RECOMMENDATIONS)$/m
  );

  for (let i = 1; i < parts.length; i += 2) {
    const sectionTitle = parts[i]?.trim();
    const sectionContent = parts[i + 1] || '';

    if (sectionTitle === 'INDIVIDUAL PROGRAM SUMMARIES') {
      sections.individualPrograms = marked.parse(sectionContent.trim()) as string;
    } else if (sectionTitle === 'GLOBAL INSIGHTS SCRATCHPAD') {
      sections.globalInsights = marked.parse(sectionContent.trim()) as string;
    } else if (sectionTitle === 'META RECOMMENDATIONS') {
      sections.metaRecommendations = marked.parse(sectionContent.trim()) as string;
    }
  }

  return sections;
}
