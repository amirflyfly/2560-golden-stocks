import { EmptyState } from './EmptyState';

export function DataTable({ columns, rows, getKey, emptyText = '暂无数据', className = 'compact-table' }) {
  return (
    <div className={`table ${className}`.trim()}>
      <div className="table-row table-head">
        {columns.map((column) => <span key={column.key || column.label}>{column.label}</span>)}
      </div>
      {rows.map((row, index) => (
        <div className="table-row" key={getKey ? getKey(row, index) : row.id || index}>
          {columns.map((column) => <span key={column.key || column.label}>{column.render ? column.render(row, index) : row[column.key]}</span>)}
        </div>
      ))}
      {rows.length ? null : <EmptyState>{emptyText}</EmptyState>}
    </div>
  );
}
