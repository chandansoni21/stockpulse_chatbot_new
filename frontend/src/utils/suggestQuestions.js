const DEFAULT_SUGGESTIONS = [
  'What data is available in the lakehouse?',
  'Show top 10 SKUs by available stock',
  'How many unique SKUs are there in total?',
  'List stock by store for a specific SKU',
];

export function getLastTwoExchanges(messages) {
  if (!Array.isArray(messages) || messages.length === 0) {
    return [];
  }

  const exchanges = [];

  for (let i = messages.length - 1; i >= 0 && exchanges.length < 2; i -= 1) {
    if (messages[i].role !== 'assistant') continue;

    let question = '';
    for (let j = i - 1; j >= 0; j -= 1) {
      if (messages[j].role === 'user') {
        question = messages[j].text;
        break;
      }
    }

    exchanges.unshift({
      question,
      answer: messages[i].text,
    });
  }

  return exchanges;
}

export function suggestQuestionsFromContext(exchanges) {
  if (!exchanges.length) {
    return DEFAULT_SUGGESTIONS.slice(0, 4);
  }

  const latest = exchanges[exchanges.length - 1];
  const previous = exchanges.length > 1 ? exchanges[exchanges.length - 2] : null;

  const combined = exchanges
    .map(({ question, answer }) => `${question} ${answer}`)
    .join(' ')
    .toLowerCase();

  const lastQuestion = (latest.question || '').toLowerCase();
  const lastAnswer = (latest.answer || '').toLowerCase();
  const suggestions = [];

  const add = (question) => {
    if (question && suggestions.length < 4 && !suggestions.includes(question)) {
      suggestions.push(question);
    }
  };

  if (lastQuestion.includes('barcode') || lastAnswer.includes('barcode')) {
    add('Show barcode count for SKU CL00004');
    add('Which SKU has the most barcodes linked?');
    add('List all barcodes for one specific SKU');
  }

  if (lastQuestion.includes('sku') || lastAnswer.includes('sku')) {
    add('Which SKU has the highest stock across all stores?');
    add('Show SKUs with zero or negative stock');
    add('How many unique SKUs are there in total?');
  }

  if (lastQuestion.includes('store') || lastAnswer.includes('store') || combined.includes('store name')) {
    add('Which store has the lowest inventory?');
    add('Show stock breakdown by store for one SKU');
    add('List total stock per store');
  }

  if (lastQuestion.includes('stock') || lastAnswer.includes('stock') || combined.includes('available stock')) {
    add('Show items that need restocking urgently');
    add('What is total available stock across all stores?');
    add('Show top 10 SKUs by available stock');
  }

  if (lastQuestion.includes('sales') || lastAnswer.includes('sales') || (previous?.question || '').toLowerCase().includes('sales')) {
    add('Show top selling SKUs this month');
    add('Compare sales by store or region');
    add('Which SKU had the highest sales last quarter?');
  }

  if (lastAnswer.includes('|') || lastAnswer.includes('row') || lastAnswer.includes('table')) {
    add('Can I get the full list for all stores?');
    add('Show only the top 20 rows from this data');
    add('Summarize totals from this table');
  }

  if (lastAnswer.includes('2,222') || lastAnswer.includes('total')) {
    add('Break down this total by store');
    add('Show a sample of 10 records from this data');
    add('Which category contributes most to this total?');
  }

  if (previous?.question && previous.question.length > 12 && !previous.question.startsWith('📷')) {
    add(`Can you break down the answer to: ${previous.question.slice(0, 55)}${previous.question.length > 55 ? '...' : ''}`);
  }

  if (latest.question && latest.question.length > 12 && !latest.question.startsWith('📷')) {
    add(`Give more detail about: ${latest.question.slice(0, 55)}${latest.question.length > 55 ? '...' : ''}`);
  }

  for (const fallback of DEFAULT_SUGGESTIONS) {
    add(fallback);
  }

  return suggestions.slice(0, 4);
}

// Backward compatible helper
export function suggestQuestions(answerText) {
  return suggestQuestionsFromContext([{ question: '', answer: answerText }]);
}
