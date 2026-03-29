# Genesis WebUI Guide 🎨

The Genesis WebUI provides an interactive, real-time visualization of the evolutionary process, allowing you to monitor experiments, explore solution genealogies, and analyze performance metrics.

## Table of Contents

1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [Setup and Launch](#setup-and-launch)
4. [WebUI Features](#webui-features)
5. [Remote Access](#remote-access)
6. [Troubleshooting](#troubleshooting)
7. [Advanced Usage](#advanced-usage)

## Overview

The WebUI serves as a dashboard for monitoring Genesis evolution experiments, providing:

- **Real-time Updates**: Live monitoring of ongoing experiments
- **Evolution Tree**: Interactive visualization of solution genealogies
- **Performance Metrics**: Charts and graphs of fitness over generations
- **Code Diff Viewer**: Side-by-side comparison of evolved solutions
- **Island Visualization**: Multi-island evolution monitoring
- **Database Browser**: Explore archived solutions and metadata

![WebUI Screenshot](webui.png)

## Quick Start

### Local Experiment

Launch the WebUI alongside your evolution experiment:

```bash
# Start your evolution experiment
genesis_launch variant=circle_packing_example

# In another terminal, start the frontend
cd genesis/webui/frontend
npm install
npm run dev

# Open browser to http://localhost:5173 (or port shown by vite)
```

## Setup and Launch

### Prerequisites

- Node.js 18+ and npm
- Python 3.12+ (for backend)
- Access to the experiment's database

### Launch Options

The frontend is a modern React application. Use standard npm commands:

```bash
cd genesis/webui/frontend
npm install
npm run dev
```

## WebUI Features

### 1. Evolution Tree Visualization

The evolution tree shows the genealogical relationships between solutions:

- **Nodes**: Individual solutions with fitness scores
- **Edges**: Parent-child relationships
- **Colors**: Performance-based color coding
- **Interactive**: Click nodes to view details
- **Filtering**: Filter by generation, island, or fitness

### 2. Performance Metrics Dashboard

Track evolution progress with various metrics:

- **Fitness Over Time**: Line charts showing best/average fitness
- **Generation Statistics**: Distribution plots for each generation
- **Island Comparison**: Performance across different islands

### 3. Code Diff Viewer

Compare solutions to understand evolutionary changes:

- **Side-by-Side View**: Parent vs child code comparison
- **Syntax Highlighting**: Language-specific highlighting
- **Change Highlighting**: Added, removed, and modified lines

### 4. Solution Browser

Explore the archive of evolved solutions:

- **Search and Filter**: Find solutions by criteria
- **Sort Options**: By fitness, generation, or date
- **Metadata View**: Detailed solution information

## Remote Access

### SSH Tunneling

For experiments running on remote machines:

```bash
# Create SSH tunnel (local port 5173 -> remote port 5173)
ssh -L 5173:localhost:5173 username@remote-host
```

## Troubleshooting

### Common Issues

#### 1. Port Already in Use
Vite usually defaults to port 5173. If used, it will try 5174, etc. Check the terminal output for the actual port.

#### 2. No Data Displayed
Ensure the backend API (if running separately) or database connection is configured correctly in the frontend settings.

## WebUI Architecture

The WebUI consists of:

- **Frontend**: React + TypeScript application (`genesis/webui/frontend`)
- **Backend**: Python API (MCP Server or ClickHouse direct access)
- **Database**: ClickHouse (operational store)
- **Assets**: Icons, stylesheets, and images

For customization and development details, see the source code in `genesis/webui/frontend/`.
