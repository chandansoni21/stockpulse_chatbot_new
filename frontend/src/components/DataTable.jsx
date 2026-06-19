import { exportTableToExcel } from '../utils/exportTableToExcel';

function getColumnStyle(header, rows, cellIndex) {
  const headerText = String(header ?? '');
  const values = rows.map((row) => String(row[cellIndex] ?? ''));
  const maxLen = Math.max(headerText.length, ...values.map((v) => v.length), 0);
  const headerLower = headerText.toLowerCase();

  if (
    headerLower.includes('sku') ||
    headerLower.includes('stock') ||
    headerLower.includes('qty') ||
    headerLower.includes('id') ||
    maxLen <= 14
  ) {
    return 'whitespace-nowrap';
  }

  if (maxLen > 28) {
    return 'min-w-[120px] max-w-[min(280px,72vw)] [overflow-wrap:anywhere]';
  }

  return 'whitespace-nowrap';
}

const cellBorder = 'border border-slate-200';

const DataTable = ({ headers, rows }) => {
  if (!headers?.length || !rows?.length) return null;

  const handleDownload = () => {
    exportTableToExcel(headers, rows, `data-export-${Date.now()}`);
  };

  return (
    <div className="data-table-wrap my-2 w-full min-w-0 overflow-hidden rounded-lg border border-slate-200 bg-white">
      <div className="flex items-center justify-end border-b border-slate-200 bg-slate-50 px-2 py-1.5 sm:px-3">
        <button
          type="button"
          onClick={handleDownload}
          className="rounded-md px-2.5 py-1 text-[11px] font-medium text-emerald-600 transition hover:bg-emerald-50 sm:text-xs"
        >
          Download Excel
        </button>
      </div>
      <div className="scroll-area max-h-[min(320px,50vh)] overflow-auto sm:max-h-[min(400px,55vh)]">
        <table className="w-max min-w-full border-collapse text-left text-xs sm:text-sm">
          <thead className="sticky top-0 z-10 bg-slate-100">
            <tr>
              {headers.map((header, cellIndex) => (
                <th
                  key={header}
                  className={`${cellBorder} bg-slate-100 px-3 py-2.5 font-semibold text-slate-800 sm:px-4 sm:py-3 ${getColumnStyle(header, rows, cellIndex)}`}
                >
                  {header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, rowIndex) => (
              <tr
                key={`row-${rowIndex}`}
                className={rowIndex % 2 === 0 ? 'bg-white' : 'bg-slate-50/80'}
              >
                {headers.map((header, cellIndex) => (
                  <td
                    key={`${header}-${cellIndex}`}
                    className={`${cellBorder} px-3 py-2 align-top text-slate-700 sm:px-4 sm:py-2.5 ${getColumnStyle(header, rows, cellIndex)}`}
                  >
                    {row[cellIndex] ?? ''}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default DataTable;
