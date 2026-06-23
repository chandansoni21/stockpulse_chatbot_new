const VEGA_LITE_SCHEMA = 'https://vega.github.io/schema/vega-lite/v6.json';
const BRAND_BLUE = '#3b82f6';
const BRAND_LIGHT = '#93c5fd';
const MAX_CHART_ROWS = 20;
const LINE_TO_BAR_THRESHOLD = 6;

function resolveFieldName(field) {
  if (field == null) return null;
  if (typeof field === 'string') {
    const text = field.trim();
    if (!text) return null;

    const patterns = [
      /['"]name['"]\s*:\s*['"]([^'"]+)['"]/,
      /['"]Property['"]\s*:\s*['"]([^'"]+)['"]/,
      /['"]field['"]\s*:\s*['"]([^'"]+)['"]/,
    ];
    for (const pattern of patterns) {
      const match = text.match(pattern);
      if (match) return match[1];
    }
    return text.startsWith('{') ? null : text;
  }

  if (typeof field === 'object') {
    if (typeof field.text === 'string') {
      return sanitizeTextLabel(field.text);
    }
    for (const key of ['field', 'name', 'Property']) {
      const nested = field[key];
      if (typeof nested === 'string' && nested.trim()) return nested.trim();
      if (nested && typeof nested === 'object') {
        const resolved = resolveFieldName(nested);
        if (resolved) return resolved;
      }
    }
  }

  return null;
}

function humanizeFieldName(name) {
  return String(name).replace(/_/g, ' ').replace(/\s+/g, ' ').trim();
}

function sanitizeTextLabel(value) {
  if (value == null) return null;

  const resolved = resolveFieldName(value);
  if (resolved) return humanizeFieldName(resolved);

  if (typeof value === 'string') {
    const text = value.trim();
    if (!text || text.startsWith('{')) return null;
    return text.length > 80 ? null : text;
  }

  if (typeof value === 'object' && typeof value.text === 'string') {
    return sanitizeTextLabel(value.text);
  }

  return null;
}

function alignFieldToColumns(fieldName, columns) {
  if (!fieldName || !columns?.length) return fieldName;
  if (columns.includes(fieldName)) return fieldName;

  const lowered = fieldName.toLowerCase();
  const match = columns.find(
    (column) =>
      column.toLowerCase() === lowered
      || column.replace(/_/g, '').toLowerCase() === fieldName.replace(/_/g, '').toLowerCase(),
  );
  return match || fieldName;
}

function sanitizeEncodingChannel(channel, columns) {
  if (Array.isArray(channel)) {
    return channel.map((item) => sanitizeEncodingChannel(item, columns));
  }
  if (!channel || typeof channel !== 'object') return channel;

  const next = { ...channel };
  const resolved = resolveFieldName(next.field);
  if (resolved) {
    next.field = alignFieldToColumns(resolved, columns);
  } else {
    delete next.field;
  }

  const cleanTitle = sanitizeTextLabel(next.title);
  if (cleanTitle) next.title = cleanTitle;
  else delete next.title;

  if (next.axis && typeof next.axis === 'object') {
    next.axis = { ...next.axis };
    const axisTitle = sanitizeTextLabel(next.axis.title);
    if (axisTitle) next.axis.title = axisTitle;
    else delete next.axis.title;
  }

  if (next.legend && typeof next.legend === 'object') {
    next.legend = { ...next.legend };
    const legendTitle = sanitizeTextLabel(next.legend.title);
    if (legendTitle) next.legend.title = legendTitle;
    else delete next.legend.title;
  }

  return next;
}

function normalizeRows(rows) {
  if (!Array.isArray(rows)) return [];

  return rows
    .filter((row) => row && typeof row === 'object')
    .map((row) => {
      const next = {};
      Object.entries(row).forEach(([key, value]) => {
        const flatKey = resolveFieldName(key) || String(key);
        if (value && typeof value === 'object' && !Array.isArray(value)) {
          if (value.value != null) {
            next[flatKey] = value.value;
            return;
          }
          if (value.type && value.name) return;
        }
        next[flatKey] = value;
      });
      return next;
    });
}

function isNumericColumn(rows, column) {
  let checked = 0;
  let numeric = 0;

  rows.slice(0, 25).forEach((row) => {
    const value = row[column];
    if (value == null || value === '') return;
    checked += 1;
    if (typeof value === 'number') {
      numeric += 1;
      return;
    }
    const parsed = Number(String(value).replace(/,/g, ''));
    if (!Number.isNaN(parsed)) numeric += 1;
  });

  return checked > 0 && numeric === checked;
}

function isPercentColumn(column, rows) {
  if (/percent|pct|percentage|%/i.test(column)) return true;

  const numbers = rows
    .map((row) => Number(String(row[column]).replace(/,/g, '')))
    .filter((value) => !Number.isNaN(value));

  if (!numbers.length) return false;
  if (numbers.every((value) => value >= 0 && value <= 1)) return true;
  return numbers.every((value) => value >= 0 && value <= 100)
    && /rate|ratio|share|portion/i.test(column);
}

function getNumberFormat(column, rows) {
  if (!isNumericColumn(rows, column)) return undefined;

  const numbers = rows
    .map((row) => Number(String(row[column]).replace(/,/g, '')))
    .filter((value) => !Number.isNaN(value));

  if (isPercentColumn(column, rows)) {
    return numbers.every((value) => value >= 0 && value <= 1) ? '.1%' : '.2f';
  }

  return ',.0f';
}

function getMarkType(spec) {
  if (!spec?.mark) return null;
  return typeof spec.mark === 'string' ? spec.mark : spec.mark.type;
}

function getValueField(encoding) {
  if (!encoding) return null;
  return encoding.y?.field || encoding.theta?.field || encoding.size?.field || null;
}

function getCategoryField(encoding) {
  if (!encoding || typeof encoding !== 'object') return null;
  return encoding.x?.field || encoding.color?.field || encoding.y?.field || null;
}

function getCategoryCount(rows, encoding) {
  const field = encoding?.x?.field || encoding?.color?.field;
  if (!field || !rows?.length) return rows?.length || 0;
  return new Set(rows.map((row) => String(row[field] ?? ''))).size;
}

function getRowValue(row, field) {
  const raw = row?.[field];
  const parsed = Number(String(raw ?? '').replace(/,/g, ''));
  return Number.isNaN(parsed) ? 0 : parsed;
}

function limitRows(rows, encoding) {
  if (!rows?.length || rows.length <= MAX_CHART_ROWS) {
    return { rows, truncated: false, originalCount: rows?.length || 0 };
  }

  const valueField = getValueField(encoding);
  const sorted = valueField
    ? [...rows].sort((left, right) => getRowValue(right, valueField) - getRowValue(left, valueField))
    : [...rows];

  return {
    rows: sorted.slice(0, MAX_CHART_ROWS),
    truncated: true,
    originalCount: rows.length,
  };
}

function buildTooltipFields(columns, rows) {
  return columns.map((field) => {
    const numeric = isNumericColumn(rows, field);
    const tooltip = {
      field,
      type: numeric ? 'quantitative' : 'nominal',
      title: humanizeFieldName(field),
    };
    const format = getNumberFormat(field, rows);
    if (format) tooltip.format = format;
    return tooltip;
  });
}

function convertCrowdedLineToBar(spec) {
  const encoding = spec.encoding;
  const xField = encoding?.x?.field;
  const yField = encoding?.y?.field;
  if (!xField || !yField) return spec;

  spec.mark = {
    type: 'bar',
    cornerRadiusTopLeft: 4,
    cornerRadiusTopRight: 4,
    color: BRAND_BLUE,
  };

  spec.encoding = {
    tooltip: encoding.tooltip,
    x: {
      field: xField,
      type: encoding.x.type === 'temporal' ? 'temporal' : 'nominal',
      title: humanizeFieldName(xField),
      axis: {
        title: humanizeFieldName(xField),
        labels: false,
        ticks: false,
        grid: false,
      },
    },
    y: {
      field: yField,
      type: 'quantitative',
      title: humanizeFieldName(yField),
      aggregate: encoding.y.aggregate,
      axis: {
        grid: true,
        gridColor: '#e2e8f0',
        tickCount: 5,
        format: ',.0f',
      },
    },
  };

  return spec;
}

function applyChartTheme(spec) {
  const markType = getMarkType(spec);

  if (spec.mark && typeof spec.mark === 'object') {
    spec.mark = {
      ...spec.mark,
      tooltip: true,
      ...(markType === 'line'
        ? { color: BRAND_BLUE, strokeWidth: 2.5, point: true, interpolate: 'monotone' }
        : {}),
      ...(markType === 'bar' ? { color: BRAND_BLUE } : {}),
      ...(markType === 'arc' ? { stroke: '#fff', strokeWidth: 1.5 } : {}),
    };
  }

  if (markType === 'line' && spec.encoding?.point !== false) {
    spec.encoding = {
      ...spec.encoding,
      point: {
        filled: true,
        size: 70,
        color: BRAND_BLUE,
        stroke: '#fff',
        strokeWidth: 1.5,
      },
    };
  }

  spec.config = {
    ...(spec.config || {}),
    background: 'transparent',
    view: { stroke: null, ...(spec.config?.view || {}) },
    axis: {
      titleFontSize: 12,
      labelFontSize: 11,
      titleColor: '#64748b',
      labelColor: '#64748b',
      gridColor: '#e2e8f0',
      domainColor: '#cbd5e1',
      tickColor: '#cbd5e1',
      labelOverlap: true,
      ...(spec.config?.axis || {}),
    },
    legend: {
      labelLimit: 100,
      ...(spec.config?.legend || {}),
    },
    range: {
      category: [BRAND_BLUE, '#0ea5e9', '#6366f1', '#8b5cf6', BRAND_LIGHT],
      ...(spec.config?.range || {}),
    },
    tooltip: {
      theme: 'light',
      ...(spec.config?.tooltip || {}),
    },
  };

  return spec;
}

function enhanceChartForDisplay(spec) {
  const columns = spec.data?.values?.[0] ? Object.keys(spec.data.values[0]) : [];
  if (!columns.length || !spec.encoding) return { spec, truncated: false, originalCount: 0 };

  const markType = getMarkType(spec);
  const { rows, truncated, originalCount } = limitRows(spec.data.values, spec.encoding);
  spec.data.values = rows;

  const encoding = { ...spec.encoding };
  const categoryCount = getCategoryCount(rows, encoding);
  const rowCount = rows.length;
  const crowded = categoryCount > LINE_TO_BAR_THRESHOLD || rowCount > LINE_TO_BAR_THRESHOLD;

  if (markType === 'arc') {
    const colorField = encoding.color?.field;
    const valueField = encoding.theta?.field;
    const tooltip = colorField && valueField
      ? [
          { field: colorField, type: 'nominal', title: 'Name' },
          {
            field: valueField,
            type: 'quantitative',
            aggregate: encoding.theta?.aggregate || 'sum',
            title: humanizeFieldName(valueField),
            format: ',.0f',
          },
        ]
      : buildTooltipFields(columns, rows);

    spec.encoding = {
      ...encoding,
      tooltip,
      color: encoding.color
        ? {
            ...encoding.color,
            legend: rowCount > 6 ? { orient: 'none' } : { orient: 'right', labelLimit: 100 },
          }
        : encoding.color,
    };

    spec.mark = {
      ...(typeof spec.mark === 'object' ? spec.mark : { type: 'arc' }),
      type: 'arc',
      innerRadius: 50,
      outerRadius: 115,
      stroke: '#fff',
      strokeWidth: 1.5,
      tooltip: true,
    };

    applyChartTheme(spec);
    return { spec, truncated, originalCount };
  }

  encoding.tooltip = buildTooltipFields(columns, rows);

  if (
    markType === 'line'
    && (encoding.x?.type === 'nominal' || encoding.x?.type === 'ordinal')
    && crowded
  ) {
    spec.encoding = encoding;
    convertCrowdedLineToBar(spec);
    spec.encoding.tooltip = buildTooltipFields(columns, rows);
    applyChartTheme(spec);
    return { spec, truncated, originalCount };
  }

  if (encoding.x) {
    const hideXLabels = crowded || encoding.x.type === 'nominal' || encoding.x.type === 'ordinal';
    encoding.x = {
      ...encoding.x,
      axis: {
        ...(encoding.x.axis || {}),
        labels: hideXLabels ? false : encoding.x.axis?.labels,
        ticks: hideXLabels ? false : encoding.x.axis?.ticks,
        title: humanizeFieldName(encoding.x.field || encoding.x.axis?.title || ''),
        grid: markType === 'line',
        labelLimit: 72,
        labelAngle: hideXLabels ? 0 : -35,
      },
    };
  }

  if (encoding.y?.type === 'quantitative') {
    encoding.y = {
      ...encoding.y,
      axis: {
        ...(encoding.y.axis || {}),
        grid: true,
        tickCount: 5,
        format: encoding.y.axis?.format || ',.0f',
      },
    };
  }

  if (encoding.color) {
    encoding.color = {
      ...encoding.color,
      legend: crowded
        ? { orient: 'none' }
        : { orient: 'right', labelLimit: 100 },
    };
  }

  if (markType === 'arc' && encoding.color) {
    encoding.color = {
      ...encoding.color,
      legend: crowded ? { orient: 'none' } : { orient: 'right', labelLimit: 100 },
    };
  }

  spec.encoding = encoding;
  applyChartTheme(spec);

  return { spec, truncated, originalCount };
}

function shouldDropChartTitle(title) {
  if (!title) return true;
  const text = typeof title === 'string' ? title : title?.text;
  if (!text || typeof text !== 'string') return true;
  const lowered = text.toLowerCase();
  return lowered.startsWith('here is a') || lowered.startsWith('here is the') || text.length > 80;
}

export function sanitizeVegaSpec(spec) {
  if (!spec || typeof spec !== 'object') {
    return { spec, truncated: false, originalCount: 0 };
  }

  const next = JSON.parse(JSON.stringify(spec));
  next.$schema = VEGA_LITE_SCHEMA;
  next.autosize = { type: 'fit', contains: 'padding', resize: true };
  next.padding = { left: 8, right: 12, top: 12, bottom: 8 };

  if (next.data?.values) {
    next.data.values = normalizeRows(next.data.values);
  }

  const columns = next.data?.values?.[0] ? Object.keys(next.data.values[0]) : [];

  if (next.encoding && typeof next.encoding === 'object') {
    const encoding = {};
    Object.entries(next.encoding).forEach(([channelName, channelValue]) => {
      encoding[channelName] = sanitizeEncodingChannel(channelValue, columns);
    });
    next.encoding = encoding;
  }

  if (shouldDropChartTitle(next.title)) {
    delete next.title;
  } else if (typeof next.title === 'object') {
    const clean = sanitizeTextLabel(next.title.text);
    if (clean) next.title = clean;
    else delete next.title;
  }

  next.width = 'container';
  next.height = next.height && next.height >= 220 ? next.height : 280;

  return enhanceChartForDisplay(next);
}

export function shouldShowChartCaption(title) {
  if (!title || typeof title !== 'string') return false;
  const lowered = title.toLowerCase();
  return !lowered.startsWith('here is a') && !lowered.startsWith('here is the') && title.length <= 80;
}
