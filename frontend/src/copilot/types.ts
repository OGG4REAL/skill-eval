/**
 * CopilotKit 相关类型定义
 */

// 图表数据格式（后端 render_chart 工具的格式）
export interface ChartDataset {
  name: string;
  values: number[];
  color?: string;
}

export interface ChartData {
  labels: string[];
  datasets: ChartDataset[];
}

export interface ChartOptions {
  x_axis_label?: string;
  y_axis_label?: string;
  show_legend?: boolean;
  stacked?: boolean;
}

export interface RenderChartArgs {
  title: string;
  chart_type: 'line' | 'bar' | 'pie' | 'scatter' | 'area' | 'radar' | 'heatmap';
  data: ChartData;
  options?: ChartOptions;
}

// 表格数据格式
export interface TableColumn {
  key: string;
  label: string;
  type?: 'string' | 'number' | 'date' | 'currency' | 'percentage';
  sortable?: boolean;
}

export interface TableOptions {
  page_size?: number;
  show_pagination?: boolean;
  highlight_max?: boolean;
}

export interface RenderTableArgs {
  title: string;
  columns: TableColumn[];
  rows: Record<string, unknown>[];
  options?: TableOptions;
}

// 通知数据格式
export interface ShowNotificationArgs {
  message: string;
  type?: 'info' | 'success' | 'warning' | 'error';
  duration?: number;
}

// SSE 事件类型
export interface SSETextEvent {
  type: 'thinking' | 'tool_call' | 'tool_result' | 'response' | 'client_side_tool';
  content: string;
  iterations?: number;
}

export interface SSEToolCallEvent {
  name: string;
  arguments: Record<string, unknown>;
}

export interface SSEErrorEvent {
  message: string;
  traceback?: string;
}

export interface SSEDoneEvent {
  session_id: string;
}

// 思考过程条目
export interface ThinkingStep {
  id: string;
  type: 'thinking' | 'tool_call' | 'tool_result';
  content: string;
  timestamp: number;
}

// 消息类型
export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  thinking?: ThinkingStep[];
  toolCalls?: SSEToolCallEvent[];
  suggestedQuestions?: string[];
  timestamp: number;
}
