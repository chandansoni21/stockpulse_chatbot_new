function isTableRow(line) {
  const trimmed = line.trim();
  return trimmed.includes('|') && trimmed.split('|').length >= 2;
}

function isSeparatorRow(line) {
  const trimmed = line.trim();
  if (!trimmed.includes('|')) return false;
  return /^[\|\s\-:]+$/.test(trimmed);
}

function isListItem(line) {
  const trimmed = line.trim();
  return /^([-*•●◦▪–—]|\d+[.)])\s+/.test(trimmed);
}

function parseListItem(line) {
  return line.trim().replace(/^([-*•●◦▪–—]|\d+[.)])\s+/, '').trim();
}

function isOrderedListItem(line) {
  return /^\d+[.)]\s+/.test(line.trim());
}

function parseTableLine(line) {
  return line
    .trim()
    .replace(/^\|/, '')
    .replace(/\|$/, '')
    .split('|')
    .map((cell) => cell.trim());
}

function parseHeading(line) {
  const match = line.trim().match(/^(#{1,3})\s+(.+)$/);
  if (!match) return null;
  return { level: match[1].length, content: match[2].trim() };
}

function parseTableLines(lines) {
  const dataLines = lines.filter((line) => !isSeparatorRow(line));
  if (dataLines.length < 1) return null;

  const rows = dataLines.map(parseTableLine).filter((row) => row.some((cell) => cell.length > 0));
  if (rows.length < 1) return null;

  return {
    headers: rows[0],
    rows: rows.slice(1),
  };
}

export function parseMessageBlocks(text) {
  if (!text) return [];

  const lines = String(text).split('\n');
  const blocks = [];
  let textBuffer = [];
  let tableBuffer = [];
  let listBuffer = [];

  const flushText = () => {
    const content = textBuffer.join('\n').trim();
    if (content) {
      blocks.push({ type: 'text', content });
    }
    textBuffer = [];
  };

  const flushList = () => {
    if (listBuffer.length === 0) return;

    const items = listBuffer.map(parseListItem).filter(Boolean);
    if (items.length === 0) {
      textBuffer.push(...listBuffer);
      listBuffer = [];
      return;
    }

    const ordered = isOrderedListItem(listBuffer[0]);
    blocks.push({ type: 'list', ordered, items });
    listBuffer = [];
  };

  const flushTable = () => {
    if (tableBuffer.length === 0) return;

    const parsed = parseTableLines(tableBuffer);
    if (parsed && parsed.rows.length > 0) {
      blocks.push({ type: 'table', ...parsed });
    } else {
      textBuffer.push(...tableBuffer);
    }
    tableBuffer = [];
  };

  for (const line of lines) {
    const heading = parseHeading(line);
    if (heading) {
      flushText();
      flushTable();
      flushList();
      blocks.push({ type: 'heading', level: heading.level, content: heading.content });
    } else if (isTableRow(line)) {
      flushText();
      flushList();
      tableBuffer.push(line);
    } else if (isListItem(line)) {
      flushText();
      flushTable();
      listBuffer.push(line);
    } else if (line.trim() === '' && listBuffer.length > 0) {
      flushList();
    } else {
      flushTable();
      flushList();
      textBuffer.push(line);
    }
  }

  flushTable();
  flushList();
  flushText();

  return blocks.length ? blocks : [{ type: 'text', content: String(text) }];
}
