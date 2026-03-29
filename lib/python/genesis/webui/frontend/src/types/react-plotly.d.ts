declare module 'react-plotly.js' {
  import { Component } from 'react';
  import Plotly from 'plotly.js';

  export interface PlotParams {
    data: Plotly.Data[];
    layout?: Partial<Plotly.Layout>;
    config?: Partial<Plotly.Config>;
    frames?: Plotly.Frame[];
    style?: React.CSSProperties;
    className?: string;
    useResizeHandler?: boolean;
    divId?: string;
    revision?: number;
    onInitialized?: (
      figure: Readonly<{ data: Plotly.Data[]; layout: Partial<Plotly.Layout> }>,
      graphDiv: HTMLElement
    ) => void;
    onUpdate?: (
      figure: Readonly<{ data: Plotly.Data[]; layout: Partial<Plotly.Layout> }>,
      graphDiv: HTMLElement
    ) => void;
    onPurge?: (
      figure: Readonly<{ data: Plotly.Data[]; layout: Partial<Plotly.Layout> }>,
      graphDiv: HTMLElement
    ) => void;
    onError?: (err: Error) => void;
    onClick?: (event: Plotly.PlotMouseEvent) => void;
    onHover?: (event: Plotly.PlotHoverEvent) => void;
    onUnhover?: (event: Plotly.PlotMouseEvent) => void;
    onSelected?: (event: Plotly.PlotSelectionEvent) => void;
    onDeselect?: () => void;
    onRelayout?: (event: Plotly.PlotRelayoutEvent) => void;
    onRestyle?: (event: Plotly.PlotRestyleEvent) => void;
    onRedraw?: () => void;
    onClickAnnotation?: (event: Plotly.ClickAnnotationEvent) => void;
    onLegendClick?: (event: Plotly.LegendClickEvent) => boolean;
    onLegendDoubleClick?: (event: Plotly.LegendClickEvent) => boolean;
  }

  export default class Plot extends Component<PlotParams> {}
}
