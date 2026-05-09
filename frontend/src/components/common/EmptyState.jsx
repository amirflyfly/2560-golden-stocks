export function EmptyState({ children = '暂无数据' }) {
  return <div className="empty">{children}</div>;
}
