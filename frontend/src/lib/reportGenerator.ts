/**
 * 通用报告生成器
 *
 * 将 AI 对话中的所有产出（文字、图表、表格、通知）
 * 序列化为独立可分发的 HTML 文件，无需大模型参与。
 */
import type {
  ChatMessage,
  RenderChartArgs,
  RenderTableArgs,
  ShowNotificationArgs,
} from '../copilot/types';

// ─── 数据提取 ────────────────────────────────────────────────

export interface ReportSection {
  question?: string;
  content: string;
  notifications: ShowNotificationArgs[];
  charts: RenderChartArgs[];
  tables: RenderTableArgs[];
}

export function extractReportContent(messages: ChatMessage[]): ReportSection[] {
  const sections: ReportSection[] = [];
  let pendingQuestion: string | undefined;

  for (const msg of messages) {
    if (msg.role === 'user') {
      pendingQuestion = msg.content?.trim() || undefined;
      continue;
    }

    const section: ReportSection = {
      question: pendingQuestion,
      content: msg.content ?? '',
      notifications: [],
      charts: [],
      tables: [],
    };
    pendingQuestion = undefined;

    for (const tc of msg.toolCalls ?? []) {
      if (tc.name === 'render_chart')
        section.charts.push(tc.arguments as unknown as RenderChartArgs);
      else if (tc.name === 'render_table')
        section.tables.push(tc.arguments as unknown as RenderTableArgs);
      else if (tc.name === 'show_notification')
        section.notifications.push(tc.arguments as unknown as ShowNotificationArgs);
    }

    const hasContent =
      section.content.trim() ||
      section.charts.length ||
      section.tables.length ||
      section.notifications.length;

    if (hasContent) sections.push(section);
  }

  return sections;
}

// ─── 图表 Option 构建（复用 ChartAction 逻辑）────────────────

const CHART_COLORS = [
  '#5470c6', '#91cc75', '#fac858', '#ee6666',
  '#73c0de', '#3ba272', '#fc8452', '#9a60b4',
];

function buildEChartsOption(args: RenderChartArgs): Record<string, unknown> {
  const { title, chart_type, data, options } = args;

  const base: Record<string, unknown> = {
    backgroundColor: 'transparent',
    color: CHART_COLORS,
    title: {
      text: title,
      left: 'center',
      textStyle: { color: '#ffffff', fontSize: 16, fontWeight: 'normal' },
      top: 10,
    },
    tooltip: {
      trigger: chart_type === 'pie' ? 'item' : 'axis',
      backgroundColor: 'rgba(50,50,50,0.9)',
      borderColor: '#777',
      textStyle: { color: '#fff' },
      axisPointer: { type: 'shadow' },
    },
    legend: {
      show: options?.show_legend !== false,
      bottom: 5,
      textStyle: { color: 'rgba(255,255,255,0.7)' },
      itemGap: 15,
    },
    grid: {
      left: '5%', right: '5%', bottom: '15%', top: '20%',
      containLabel: true,
    },
  };

  if (chart_type === 'pie') {
    const pieData = data.datasets[0]?.values.map((v, i) => ({
      name: data.labels[i] || `项目${i + 1}`,
      value: v,
    })) ?? [];
    return {
      ...base,
      series: [{
        name: title, type: 'pie', radius: ['40%', '70%'],
        avoidLabelOverlap: true,
        itemStyle: { borderRadius: 10, borderColor: 'rgba(0,0,0,0)', borderWidth: 2 },
        label: { show: true, color: 'rgba(255,255,255,0.8)' },
        data: pieData,
        emphasis: { itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.5)' } },
      }],
    };
  }

  if (chart_type === 'radar') {
    const maxVal = Math.max(...data.datasets.flatMap(d => d.values)) * 1.2;
    const indicator = data.labels.map(label => ({ name: label, max: maxVal }));
    return {
      ...base,
      radar: {
        indicator,
        axisName: { color: 'rgba(255,255,255,0.7)' },
        splitArea: { areaStyle: { color: ['rgba(255,255,255,0.02)', 'rgba(255,255,255,0.05)'] } },
        splitLine: { lineStyle: { color: 'rgba(255,255,255,0.1)' } },
      },
      series: [{
        type: 'radar',
        data: data.datasets.map((ds, i) => ({
          name: ds.name, value: ds.values,
          areaStyle: { opacity: 0.3 },
          lineStyle: { color: ds.color || CHART_COLORS[i % CHART_COLORS.length] },
        })),
      }],
    };
  }

  const typeMap: Record<string, string> = {
    line: 'line', bar: 'bar', scatter: 'scatter', area: 'line',
  };
  const mappedType = typeMap[chart_type] || 'line';

  return {
    ...base,
    xAxis: {
      type: 'category', data: data.labels, name: options?.x_axis_label,
      axisLabel: { color: 'rgba(255,255,255,0.6)' },
      axisLine: { lineStyle: { color: 'rgba(255,255,255,0.2)' } },
    },
    yAxis: {
      type: 'value', name: options?.y_axis_label,
      axisLabel: { color: 'rgba(255,255,255,0.6)' },
      axisLine: { show: false },
      splitLine: { lineStyle: { color: 'rgba(255,255,255,0.05)' } },
    },
    series: data.datasets.map((ds, i) => ({
      name: ds.name, type: mappedType, data: ds.values, smooth: true,
      stack: options?.stacked ? 'total' : undefined,
      areaStyle: chart_type === 'area' ? { opacity: 0.3 } : undefined,
      itemStyle: {
        color: ds.color || CHART_COLORS[i % CHART_COLORS.length],
        borderRadius: chart_type === 'bar' ? [4, 4, 0, 0] : undefined,
      },
      label: {
        show: chart_type === 'bar', position: 'top',
        color: 'rgba(255,255,255,0.8)', fontSize: 10,
      },
    })),
  };
}

// ─── HTML 片段生成 ────────────────────────────────────────────

function htmlEscape(str: string): string {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function renderNotifications(items: ShowNotificationArgs[]): string {
  if (!items.length) return '';
  const icons: Record<string, string> = {
    info: 'ℹ️', success: '✅', warning: '⚠️', error: '❌',
  };
  return `
<div class="notifications">
  ${items.map(n => `
    <div class="notification ${n.type ?? 'info'}">
      <span class="notif-icon">${icons[n.type ?? 'info'] ?? 'ℹ️'}</span>
      <span>${htmlEscape(n.message)}</span>
    </div>`).join('')}
</div>`;
}

function renderTableHtml(table: RenderTableArgs): string {
  const header = table.columns.map(c => `<th>${htmlEscape(c.label)}</th>`).join('');
  const rows = table.rows.map(row =>
    `<tr>${table.columns.map(c => `<td>${htmlEscape(String(row[c.key] ?? '-'))}</td>`).join('')}</tr>`
  ).join('');
  return `
<div class="table-wrapper">
  <h3 class="block-title">${htmlEscape(table.title)}</h3>
  <div class="table-scroll">
    <table>
      <thead><tr>${header}</tr></thead>
      <tbody>${rows}</tbody>
    </table>
  </div>
  <div class="table-count">共 ${table.rows.length} 条记录</div>
</div>`;
}

// ─── 内联样式 ─────────────────────────────────────────────────

const STYLES = `
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Microsoft YaHei',
    'Segoe UI', Roboto, sans-serif;
  background: #12121f;
  color: #e2e2e8;
  line-height: 1.7;
  padding: 40px 20px 80px;
}

.report-wrap { max-width: 960px; margin: 0 auto; }

/* 标题栏 */
.report-header {
  text-align: center;
  margin-bottom: 48px;
  padding-bottom: 24px;
  border-bottom: 1px solid rgba(255,255,255,0.1);
}
.report-header h1 {
  font-size: 2rem; font-weight: 700; color: #fff;
  letter-spacing: -0.5px; margin-bottom: 8px;
}
.report-header .meta { color: #666; font-size: 13px; }

/* 用户问题 */
.user-question {
  display: flex; align-items: flex-start; gap: 12px;
  background: rgba(84,112,198,0.08);
  border: 1px solid rgba(84,112,198,0.18);
  border-radius: 12px;
  padding: 14px 20px;
  margin-bottom: 20px;
  font-size: 15px; color: #b0c4ef;
}
.user-question .q-icon {
  flex-shrink: 0; font-size: 15px; font-weight: 700;
  color: #5470c6; line-height: 1.7;
}
.user-question .q-text { line-height: 1.7; }

/* 分区分隔 */
.section-sep {
  border: none; border-top: 1px dashed rgba(255,255,255,0.08);
  margin: 40px 0;
}

/* 通知 */
.notifications { display: flex; flex-direction: column; gap: 10px; margin-bottom: 24px; }
.notification {
  display: flex; align-items: flex-start; gap: 10px;
  padding: 14px 18px; border-radius: 12px;
  border-left: 4px solid; font-size: 14px; line-height: 1.5;
}
.notification.info    { background: rgba(84,112,198,0.12); border-color: #5470c6; }
.notification.success { background: rgba(59,162,114,0.12); border-color: #3ba272; }
.notification.warning { background: rgba(250,200,88,0.12); border-color: #fac858; }
.notification.error   { background: rgba(238,102,102,0.12); border-color: #ee6666; }
.notif-icon { flex-shrink: 0; font-size: 16px; }

/* 文字内容（Markdown 渲染后） */
.content-block {
  background: rgba(255,255,255,0.03);
  border-radius: 16px;
  padding: 28px 32px;
  margin-bottom: 24px;
  border: 1px solid rgba(255,255,255,0.07);
}
.content-block h1, .content-block h2 { color: #fff; font-weight: 600; margin: 28px 0 12px; }
.content-block h1 { font-size: 1.5rem; border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 8px; }
.content-block h2 { font-size: 1.2rem; }
.content-block h3 { color: #c0c0d0; font-size: 1.05rem; font-weight: 600; margin: 20px 0 8px; }
.content-block h4 { color: #a0a0b8; font-size: 0.95rem; font-weight: 600; margin: 16px 0 6px; }
.content-block p  { margin-bottom: 12px; color: #c8c8d8; }
.content-block ul, .content-block ol { margin: 10px 0 14px 24px; }
.content-block li { margin-bottom: 6px; color: #c8c8d8; }
.content-block strong { color: #7eb8f7; font-weight: 600; }
.content-block em { color: #a0c8a0; }
.content-block code {
  background: rgba(255,255,255,0.08); padding: 2px 6px; border-radius: 4px;
  font-family: 'JetBrains Mono', 'Fira Code', Consolas, monospace; font-size: 0.88em;
  color: #f0c060;
}
.content-block pre {
  background: rgba(0,0,0,0.3); border-radius: 10px; padding: 16px 20px;
  overflow-x: auto; margin: 14px 0;
  border: 1px solid rgba(255,255,255,0.08);
}
.content-block pre code {
  background: none; padding: 0; color: #e0e0e0;
}
.content-block blockquote {
  border-left: 3px solid #5470c6; padding-left: 16px; margin: 14px 0;
  color: #a0a0b8;
}
.content-block hr { border: none; border-top: 1px solid rgba(255,255,255,0.1); margin: 20px 0; }
.content-block table { width: 100%; border-collapse: collapse; margin: 14px 0; }
.content-block table th { background: rgba(255,255,255,0.08); color: #c0c0d0; padding: 10px 14px; text-align: left; border: 1px solid rgba(255,255,255,0.1); }
.content-block table td { padding: 10px 14px; border: 1px solid rgba(255,255,255,0.08); color: #c8c8d8; }
.content-block table tr:nth-child(even) td { background: rgba(255,255,255,0.02); }

/* 图表 */
.chart-wrapper {
  background: rgba(255,255,255,0.03); border-radius: 16px;
  padding: 16px; margin-bottom: 20px;
  border: 1px solid rgba(255,255,255,0.07);
}
.chart-box { height: 380px; width: 100%; }

/* 表格 */
.table-wrapper {
  background: rgba(255,255,255,0.03); border-radius: 16px;
  padding: 20px 24px; margin-bottom: 20px;
  border: 1px solid rgba(255,255,255,0.07);
}
.block-title { font-size: 15px; font-weight: 600; color: #fff; margin-bottom: 14px; }
.table-scroll { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 14px; }
th {
  padding: 11px 16px; text-align: left;
  border-bottom: 1px solid rgba(255,255,255,0.12);
  color: #888; font-weight: 500; white-space: nowrap;
}
td {
  padding: 11px 16px;
  border-bottom: 1px solid rgba(255,255,255,0.06);
  color: rgba(255,255,255,0.85);
}
tr:last-child td { border-bottom: none; }
tr:hover td { background: rgba(255,255,255,0.03); }
.table-count { font-size: 12px; color: #555; margin-top: 10px; text-align: right; }

@media print {
  body { background: #fff; color: #222; padding: 0; }
  .content-block { background: #f9f9f9; border-color: #ddd; color: #333; }
  .content-block p, .content-block li { color: #444; }
  .content-block strong { color: #1a56db; }
  .notification.info    { background: #eff6ff; border-color: #3b82f6; color: #1e40af; }
  .notification.warning { background: #fffbeb; border-color: #f59e0b; color: #92400e; }
  .notification.error   { background: #fef2f2; border-color: #ef4444; color: #991b1b; }
  .notification.success { background: #f0fdf4; border-color: #22c55e; color: #166534; }
  .user-question { background: #eff6ff; border-color: #93b4e8; color: #1e3a5f; }
  .user-question .q-icon { color: #2563eb; }
  .chart-wrapper, .table-wrapper { background: #f9f9f9; border-color: #ddd; }
  th { color: #555; } td { color: #333; }
}
`;

// ─── 主入口 ───────────────────────────────────────────────────

export function generateReportHtml(
  sessionId: string,
  sections: ReportSection[],
): string {
  const timestamp = new Date().toLocaleString('zh-CN');

  // 收集所有需要初始化的图表
  const chartInits: string[] = [];
  let chartGlobalIdx = 0;

  // 渲染各 section
  const sectionsHtml = sections.map((section, sIdx) => {
    let html = '';

    if (section.question) {
      html += `
<div class="user-question">
  <span class="q-icon">用户：</span>
  <span class="q-text">${htmlEscape(section.question)}</span>
</div>`;
    }

    if (section.notifications.length) {
      html += renderNotifications(section.notifications);
    }

    if (section.content.trim()) {
      // Markdown 在报告页内用 marked 渲染（CDN），id 唯一
      const mdId = `md-${sIdx}`;
      // 内容存储在隐藏的 <script> 标签，由 marked 渲染
      html += `
<div class="content-block" id="${mdId}-target"></div>
<script type="text/markdown" id="${mdId}">${section.content.replace(/<\/script>/g, '<\\/script>')}</script>`;
    }

    for (const chart of section.charts) {
      const cid = `chart-${chartGlobalIdx}`;
      const option = buildEChartsOption(chart);
      chartInits.push(`
(function(){
  var el = document.getElementById('${cid}');
  if (!el) return;
  var c = echarts.init(el, 'dark');
  c.setOption(${JSON.stringify(option)});
  window.addEventListener('resize', function(){ c.resize(); });
})();`);
      html += `<div class="chart-wrapper"><div id="${cid}" class="chart-box"></div></div>`;
      chartGlobalIdx++;
    }

    for (const table of section.tables) {
      html += renderTableHtml(table);
    }

    return html;
  });

  const bodyContent = sectionsHtml
    .filter(Boolean)
    .join('<hr class="section-sep">');

  // marked 渲染脚本（遍历所有 text/markdown script 标签）
  const markdownRenderScript = `
(function(){
  if (typeof marked === 'undefined') return;
  marked.use({ gfm: true, breaks: false });
  document.querySelectorAll('script[type="text/markdown"]').forEach(function(el){
    var targetId = el.id + '-target';
    var target = document.getElementById(targetId);
    if (target) target.innerHTML = marked.parse(el.textContent || '');
  });
})();`;

  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Agent Studio 报告 · ${sessionId} · ${timestamp}</title>
  <style>${STYLES}</style>
</head>
<body>
  <div class="report-wrap">
    <header class="report-header">
      <h1>Agent Studio 报告</h1>
      <p class="meta">生成时间：${timestamp}&emsp;|&emsp;会话：${htmlEscape(sessionId)}</p>
    </header>
    ${bodyContent || '<p style="color:#666;text-align:center">暂无内容</p>'}
  </div>

  <script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/marked@9/marked.min.js"></script>
  <script>
    ${markdownRenderScript}
    ${chartInits.join('\n')}
  </script>
</body>
</html>`;
}

// ─── 下载触发 ─────────────────────────────────────────────────

export function downloadReport(sessionId: string, messages: ChatMessage[]): void {
  const sections = extractReportContent(messages);
  const html = generateReportHtml(sessionId, sections);

  const blob = new Blob([html], { type: 'text/html;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `agent-studio-report-${sessionId}-${Date.now()}.html`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
