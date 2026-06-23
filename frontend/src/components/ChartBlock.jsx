import { useEffect, useMemo, useRef, useState } from 'react';
import { VegaEmbed } from 'react-vega';
import { useIsMobile } from '../hooks/useIsMobile';
import { sanitizeVegaSpec, shouldShowChartCaption } from '../utils/sanitizeVegaSpec';

const MAX_CHART_ROWS = 20;

const ChartBlock = ({ chart }) => {
  const isMobile = useIsMobile();
  const containerRef = useRef(null);
  const [containerWidth, setContainerWidth] = useState(0);
  const [renderError, setRenderError] = useState(null);

  const { spec, truncated, originalCount } = useMemo(() => {
    if (!chart?.spec) return { spec: null, truncated: false, originalCount: 0 };
    return sanitizeVegaSpec(chart.spec);
  }, [chart]);

  useEffect(() => {
    const node = containerRef.current;
    if (!node) return undefined;

    const updateWidth = () => {
      setContainerWidth(Math.max(240, Math.floor(node.clientWidth)));
    };

    updateWidth();
    const observer = new ResizeObserver(updateWidth);
    observer.observe(node);
    return () => observer.disconnect();
  }, [chart]);

  useEffect(() => {
    setRenderError(null);
  }, [chart]);

  const isPieChart = spec?.mark?.type === 'arc' || Boolean(spec?.encoding?.theta);
  const chartHeight = isPieChart ? (isMobile ? 280 : 340) : (isMobile ? 240 : 300);

  const renderSpec = useMemo(() => {
    if (!spec) return null;
    const next = {
      ...spec,
      width: containerWidth > 0 ? containerWidth - 4 : 'container',
      height: chartHeight,
      autosize: { type: 'fit', contains: 'padding', resize: true },
    };
    delete next.title;
    return next;
  }, [chartHeight, containerWidth, spec]);

  if (!chart) return null;

  if (chart.kind === 'image' && chart.image_url) {
    return (
      <figure className="chart-card m-0 w-full">
        <div className="chart-card-body overflow-x-auto">
          <img
            src={chart.image_url}
            alt={chart.title || 'Chart'}
            className="block h-auto max-h-[280px] w-full rounded-lg object-contain"
            loading="lazy"
          />
        </div>
        {shouldShowChartCaption(chart.title) ? (
          <figcaption className="chart-card-foot">{chart.title}</figcaption>
        ) : null}
      </figure>
    );
  }

  if (chart.kind === 'vega-lite' && spec) {
    return (
      <figure className="chart-card m-0 w-full">
        <div className="chart-card-head">
          <div className="flex items-center gap-2">
            <span className="chart-card-icon" aria-hidden="true">
              <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                <path d="M2 16h16v2H2v-2zm2-3V7h3v6H4zm4 0V4h3v9H8zm4 0V9h3v4h-3z" />
              </svg>
            </span>
            <span className="text-sm font-semibold text-slate-700">Chart</span>
          </div>
          <span className="text-[11px] text-slate-400 sm:text-xs">Hover or tap for details</span>
        </div>

        <div ref={containerRef} className="chart-card-body">
          {renderSpec ? (
            <VegaEmbed
              spec={renderSpec}
              options={{ actions: false, renderer: 'svg', tooltip: { theme: 'light' } }}
              onError={(error) => {
                console.error('[ChartBlock] Vega render failed:', error);
                setRenderError('Could not render this chart.');
              }}
            />
          ) : null}
        </div>

        {renderError ? (
          <p className="px-3 pb-3 text-xs text-rose-600">{renderError}</p>
        ) : null}

        {truncated ? (
          <p className="chart-card-foot">
            Showing top {spec?.data?.values?.length || MAX_CHART_ROWS} of {originalCount} items. Hover for full names and values.
          </p>
        ) : shouldShowChartCaption(chart.title) ? (
          <figcaption className="chart-card-foot">{chart.title}</figcaption>
        ) : null}
      </figure>
    );
  }

  return null;
};

export default ChartBlock;
