/**
 * 表格渲染 Action
 * 
 * 将后端 render_table 工具的调用转换为交互式表格
 */
import { useState, useMemo } from 'react';
import type { RenderTableArgs, TableColumn } from '../types';

interface TableActionProps {
  args: RenderTableArgs;
}

const EMPTY_COLUMNS: TableColumn[] = [];
const EMPTY_ROWS: Record<string, unknown>[] = [];

// 格式化单元格值
function formatCellValue(value: unknown, type?: TableColumn['type']): string {
  if (value === null || value === undefined) return '-';
  
  switch (type) {
    case 'number':
      return typeof value === 'number' ? value.toLocaleString() : String(value);
    case 'currency':
      return typeof value === 'number' 
        ? `¥${value.toLocaleString(undefined, { minimumFractionDigits: 2 })}` 
        : String(value);
    case 'percentage':
      return typeof value === 'number' ? `${value.toFixed(2)}%` : String(value);
    case 'date':
      return value instanceof Date ? value.toLocaleDateString() : String(value);
    default:
      return String(value);
  }
}

export function TableAction({ args }: TableActionProps) {
  const { title, columns, rows, options } = args;

  const hasValidTableData = Array.isArray(columns) && Array.isArray(rows);
  const safeColumns = hasValidTableData ? columns : EMPTY_COLUMNS;
  const safeRows = hasValidTableData ? rows : EMPTY_ROWS;

  const pageSize = options?.page_size || 10;
  const showPagination = options?.show_pagination !== false;
  
  const [currentPage, setCurrentPage] = useState(1);
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('asc');

  // 排序数据
  const sortedRows = useMemo(() => {
    if (!sortKey) return safeRows;
    
    return [...safeRows].sort((a, b) => {
      const aVal = a[sortKey];
      const bVal = b[sortKey];
      
      if (aVal === bVal) return 0;
      if (aVal === null || aVal === undefined) return 1;
      if (bVal === null || bVal === undefined) return -1;
      
      const compare = aVal < bVal ? -1 : 1;
      return sortOrder === 'asc' ? compare : -compare;
    });
  }, [safeRows, sortKey, sortOrder]);

  // 分页数据
  const totalPages = Math.ceil(sortedRows.length / pageSize);
  const paginatedRows = showPagination 
    ? sortedRows.slice((currentPage - 1) * pageSize, currentPage * pageSize)
    : sortedRows;

  // 找出数值列的最大值（用于高亮）
  const maxValues = useMemo(() => {
    if (!options?.highlight_max) return {};
    
    const result: Record<string, number> = {};
    safeColumns.forEach(col => {
      if (col.type === 'number' || col.type === 'currency') {
        const values = safeRows.map(r => r[col.key]).filter(v => typeof v === 'number') as number[];
        if (values.length > 0) {
          result[col.key] = Math.max(...values);
        }
      }
    });
    return result;
  }, [safeRows, safeColumns, options?.highlight_max]);

  if (!hasValidTableData) {
    return (
      <div style={{
        background: 'rgba(255, 255, 255, 0.03)',
        borderRadius: '16px',
        padding: '16px',
        margin: '8px 0',
        border: '1px solid rgba(255, 80, 80, 0.2)',
        color: 'rgba(255, 120, 120, 0.8)',
        fontSize: '13px',
      }}>
        表格数据格式异常（模型返回了不标准的参数结构）
      </div>
    );
  }

  const handleSort = (key: string) => {
    if (sortKey === key) {
      setSortOrder(prev => prev === 'asc' ? 'desc' : 'asc');
    } else {
      setSortKey(key);
      setSortOrder('asc');
    }
  };

  return (
    <div className="table-action-container" style={{
      background: 'rgba(255, 255, 255, 0.03)',
      borderRadius: '16px',
      padding: '16px',
      margin: '8px 0',
      border: '1px solid rgba(255, 255, 255, 0.08)',
      overflow: 'hidden',
    }}>
      <h3 style={{
        margin: '0 0 16px',
        fontSize: '16px',
        fontWeight: 500,
        color: '#fff',
      }}>
        {title}
      </h3>
      
      <div style={{ overflowX: 'auto' }}>
        <table style={{
          width: '100%',
          borderCollapse: 'collapse',
          fontSize: '14px',
        }}>
          <thead>
            <tr>
              {safeColumns.map(col => (
                <th
                  key={col.key}
                  onClick={() => col.sortable !== false && handleSort(col.key)}
                  style={{
                    padding: '12px 16px',
                    textAlign: 'left',
                    borderBottom: '1px solid rgba(255, 255, 255, 0.1)',
                    color: 'rgba(255, 255, 255, 0.7)',
                    fontWeight: 500,
                    cursor: col.sortable !== false ? 'pointer' : 'default',
                    userSelect: 'none',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {col.label}
                  {sortKey === col.key && (
                    <span style={{ marginLeft: '4px' }}>
                      {sortOrder === 'asc' ? '↑' : '↓'}
                    </span>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {paginatedRows.map((row, rowIndex) => (
              <tr
                key={rowIndex}
                style={{
                  background: rowIndex % 2 === 0 ? 'transparent' : 'rgba(255, 255, 255, 0.02)',
                }}
              >
                {safeColumns.map(col => {
                  const value = row[col.key];
                  const isMax = options?.highlight_max && 
                    maxValues[col.key] !== undefined && 
                    value === maxValues[col.key];
                  
                  return (
                    <td
                      key={col.key}
                      style={{
                        padding: '12px 16px',
                        borderBottom: '1px solid rgba(255, 255, 255, 0.05)',
                        color: isMax ? '#91cc75' : 'rgba(255, 255, 255, 0.9)',
                        fontWeight: isMax ? 600 : 400,
                      }}
                    >
                      {formatCellValue(value, col.type)}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {showPagination && totalPages > 1 && (
        <div style={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          gap: '8px',
          marginTop: '16px',
        }}>
          <button
            onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
            disabled={currentPage === 1}
            style={{
              padding: '6px 12px',
              borderRadius: '8px',
              border: '1px solid rgba(255, 255, 255, 0.2)',
              background: 'transparent',
              color: currentPage === 1 ? 'rgba(255, 255, 255, 0.3)' : '#fff',
              cursor: currentPage === 1 ? 'not-allowed' : 'pointer',
            }}
          >
            上一页
          </button>
          <span style={{ color: 'rgba(255, 255, 255, 0.7)' }}>
            {currentPage} / {totalPages}
          </span>
          <button
            onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
            disabled={currentPage === totalPages}
            style={{
              padding: '6px 12px',
              borderRadius: '8px',
              border: '1px solid rgba(255, 255, 255, 0.2)',
              background: 'transparent',
              color: currentPage === totalPages ? 'rgba(255, 255, 255, 0.3)' : '#fff',
              cursor: currentPage === totalPages ? 'not-allowed' : 'pointer',
            }}
          >
            下一页
          </button>
        </div>
      )}
      
      <div style={{
        marginTop: '12px',
        fontSize: '12px',
        color: 'rgba(255, 255, 255, 0.5)',
        textAlign: 'right',
      }}>
        共 {safeRows.length} 条记录
      </div>
    </div>
  );
}

export default TableAction;
