/**
 * 图表渲染 Action
 * 
 * 将后端 render_chart 工具的调用转换为 ECharts 图表
 */
import ReactECharts from 'echarts-for-react';
import type { RenderChartArgs } from '../types';

interface ChartActionProps {
  args: RenderChartArgs;
}

// 默认颜色方案
const CHART_COLORS = [
  '#5470c6', '#91cc75', '#fac858', '#ee6666', 
  '#73c0de', '#3ba272', '#fc8452', '#9a60b4'
];

/**
 * 将后端数据格式转换为 ECharts 配置
 */
function convertToEChartsOption(args: RenderChartArgs) {
  const { title, chart_type, data, options } = args;
  
  // 通用配置
  const baseOption: Record<string, unknown> = {
    backgroundColor: 'transparent',
    color: CHART_COLORS,
    title: {
      text: title,
      left: 'center',
      textStyle: {
        color: '#ffffff',
        fontSize: 16,
        fontWeight: 'normal',
      },
      top: 10,
    },
    tooltip: {
      trigger: chart_type === 'pie' ? 'item' : 'axis',
      backgroundColor: 'rgba(50, 50, 50, 0.9)',
      borderColor: '#777',
      textStyle: { color: '#fff' },
      axisPointer: { type: 'shadow' },
    },
    legend: {
      show: options?.show_legend !== false,
      bottom: 5,
      textStyle: { color: 'rgba(255, 255, 255, 0.7)' },
      itemGap: 15,
    },
    grid: {
      left: '5%',
      right: '5%',
      bottom: '15%',
      top: '20%',
      containLabel: true,
    },
  };

  // 饼图特殊处理
  if (chart_type === 'pie') {
    const pieData = data.datasets[0]?.values.map((value, index) => ({
      name: data.labels[index] || `项目${index + 1}`,
      value,
    })) || [];

    return {
      ...baseOption,
      series: [
        {
          name: title,
          type: 'pie',
          radius: ['40%', '70%'],
          avoidLabelOverlap: true,
          itemStyle: {
            borderRadius: 10,
            borderColor: 'rgba(0,0,0,0)',
            borderWidth: 2,
          },
          label: {
            show: true,
            color: 'rgba(255, 255, 255, 0.8)',
          },
          data: pieData,
          emphasis: {
            itemStyle: {
              shadowBlur: 10,
              shadowOffsetX: 0,
              shadowColor: 'rgba(0, 0, 0, 0.5)',
            },
          },
        },
      ],
    };
  }

  // 雷达图特殊处理
  if (chart_type === 'radar') {
    const indicator = data.labels.map((label) => ({
      name: label,
      max: Math.max(...data.datasets.flatMap(d => d.values)) * 1.2,
    }));

    return {
      ...baseOption,
      radar: {
        indicator,
        axisName: {
          color: 'rgba(255, 255, 255, 0.7)',
        },
        splitArea: {
          areaStyle: {
            color: ['rgba(255, 255, 255, 0.02)', 'rgba(255, 255, 255, 0.05)'],
          },
        },
        splitLine: {
          lineStyle: {
            color: 'rgba(255, 255, 255, 0.1)',
          },
        },
      },
      series: [
        {
          type: 'radar',
          data: data.datasets.map((dataset, index) => ({
            name: dataset.name,
            value: dataset.values,
            areaStyle: {
              opacity: 0.3,
            },
            lineStyle: {
              color: dataset.color || CHART_COLORS[index % CHART_COLORS.length],
            },
          })),
        },
      ],
    };
  }

  // 其他图表类型（line, bar, scatter, area）
  const chartTypeMapping: Record<string, string> = {
    line: 'line',
    bar: 'bar',
    scatter: 'scatter',
    area: 'line',
  };

  const mappedType = chartTypeMapping[chart_type] || 'line';

  return {
    ...baseOption,
    xAxis: {
      type: 'category',
      data: data.labels,
      name: options?.x_axis_label,
      axisLabel: { color: 'rgba(255, 255, 255, 0.6)' },
      axisLine: { lineStyle: { color: 'rgba(255, 255, 255, 0.2)' } },
    },
    yAxis: {
      type: 'value',
      name: options?.y_axis_label,
      axisLabel: { color: 'rgba(255, 255, 255, 0.6)' },
      axisLine: { show: false },
      splitLine: { lineStyle: { color: 'rgba(255, 255, 255, 0.05)' } },
    },
    series: data.datasets.map((dataset, index) => ({
      name: dataset.name,
      type: mappedType,
      data: dataset.values,
      smooth: true,
      stack: options?.stacked ? 'total' : undefined,
      areaStyle: chart_type === 'area' ? { opacity: 0.3 } : undefined,
      itemStyle: {
        color: dataset.color || CHART_COLORS[index % CHART_COLORS.length],
        borderRadius: chart_type === 'bar' ? [4, 4, 0, 0] : undefined,
      },
      label: {
        show: chart_type === 'bar',
        position: 'top',
        color: 'rgba(255, 255, 255, 0.8)',
        fontSize: 10,
      },
    })),
  };
}

export function ChartAction({ args }: ChartActionProps) {
  const option = convertToEChartsOption(args);

  return (
    <div className="chart-action-container" style={{
      background: 'rgba(255, 255, 255, 0.03)',
      borderRadius: '16px',
      padding: '16px',
      margin: '8px 0',
      border: '1px solid rgba(255, 255, 255, 0.08)',
    }}>
      <ReactECharts
        option={option}
        style={{ height: '350px', width: '100%' }}
        theme="dark"
        notMerge={true}
        lazyUpdate={true}
        opts={{ renderer: 'canvas' }}
      />
    </div>
  );
}

export default ChartAction;
