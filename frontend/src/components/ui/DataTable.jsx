import EmptyState from './EmptyState';
import { Database } from 'lucide-react';

export default function DataTable({ columns, data, emptyMessage = 'No data available' }) {
  if (!data || data.length === 0) {
    return <EmptyState icon={Database} title={emptyMessage} />;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm text-left">
        <thead>
          <tr className="border-b border-dark-border">
            {columns.map((col, ci) => (
              <th
                key={col.id || col.label || ci}
                className="px-4 py-3 text-xs font-semibold text-text-secondary uppercase tracking-wider whitespace-nowrap"
              >
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row, i) => (
            <tr
              key={row.id || i}
              className="border-b border-dark-border/50 hover:bg-dark-hover"
            >
              {columns.map((col, ci) => (
                <td key={col.id || col.label || ci} className="px-4 py-3 text-text-primary whitespace-nowrap">
                  {col.render ? col.render(row[col.key], row) : row[col.key] ?? '—'}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
