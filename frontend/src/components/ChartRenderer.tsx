import React from 'react';
import ReactECharts from 'echarts-for-react';

interface ChartData {
  type: string;
  title: string;
  xAxis?: {
    categories?: string[];
    label?: string;
  };
  yAxis?: {
    label?: string;
  };
  series: Array<{
    name: string;
    data: number[] | Array<{ name: string; value: number }>;
  }>;
  data?: Array<{ name: string; value: number }>; // For pie charts
}

interface Props {
  charts: ChartData[];
}

export const ChartRenderer: React.FC<Props> = ({ charts }) => {
  if (!charts || charts.length === 0) return null;

  const getOption = (chart: ChartData) => {
    // 定义一套现代化的深色主题颜色
    const colors = ['#5470c6', '#91cc75', '#fac858', '#ee6666', '#73c0de', '#3ba272', '#fc8452', '#9a60b4'];

    const commonOption: any = {
      backgroundColor: 'transparent',
      color: colors,
      title: {
        text: chart.title,
        left: 'center',
        textStyle: { 
          color: '#ffffff', // 标题白色
          fontSize: 16,
          fontWeight: 'normal'
        },
        top: 10
      },
      tooltip: {
        trigger: chart.type === 'pie' ? 'item' : 'axis',
        backgroundColor: 'rgba(50, 50, 50, 0.9)',
        borderColor: '#777',
        textStyle: { color: '#fff' },
        axisPointer: { type: 'shadow' }
      },
      legend: {
        bottom: 5,
        textStyle: { color: 'rgba(255, 255, 255, 0.7)' }, // Legend 浅灰色
        itemGap: 15
      },
      grid: {
        left: '5%',
        right: '5%',
        bottom: '15%',
        top: '20%',
        containLabel: true
      }
    };

    if (chart.type === 'pie') {
      return {
        ...commonOption,
        series: [
          {
            name: chart.title,
            type: 'pie',
            radius: ['40%', '70%'], // 环形图更现代
            avoidLabelOverlap: true,
            itemStyle: {
              borderRadius: 10,
              borderColor: 'rgba(0,0,0,0)',
              borderWidth: 2
            },
            label: {
              show: true,
              color: 'rgba(255, 255, 255, 0.8)'
            },
            data: chart.data || chart.series?.[0]?.data,
            emphasis: {
              itemStyle: {
                shadowBlur: 10,
                shadowOffsetX: 0,
                shadowColor: 'rgba(0, 0, 0, 0.5)'
              }
            }
          }
        ]
      };
    }

    // Bar and Line charts
    return {
      ...commonOption,
      xAxis: {
        type: 'category',
        data: chart.xAxis?.categories || [],
        axisLabel: { color: 'rgba(255, 255, 255, 0.6)' },
        axisLine: { lineStyle: { color: 'rgba(255, 255, 255, 0.2)' } }
      },
      yAxis: {
        type: 'value',
        axisLabel: { color: 'rgba(255, 255, 255, 0.6)' },
        axisLine: { show: false },
        splitLine: { lineStyle: { color: 'rgba(255, 255, 255, 0.05)' } } // 极弱的网格线
      },
      series: chart.series.map(s => ({
        name: s.name,
        type: chart.type,
        data: s.data,
        smooth: true, // 如果是折线图，更平滑
        itemStyle: {
          borderRadius: [4, 4, 0, 0] // 柱状图圆角
        },
        label: {
          show: true,
          position: 'top',
          color: 'rgba(255, 255, 255, 0.8)',
          fontSize: 10
        }
      }))
    };
  };

  return (
    <div className="charts-container" style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {charts.map((chart, index) => (
        <div 
          key={`chart-${index}-${chart.title}`} 
          className="chart-card glass-card" 
          style={{ 
            padding: '24px', 
            background: 'rgba(255, 255, 255, 0.03)',
            width: '100%',
            boxSizing: 'border-box',
            position: 'relative',
            minHeight: '450px',
            borderRadius: '20px'
          }}
        >
          <ReactECharts 
            option={getOption(chart)} 
            style={{ height: '400px', width: '100%' }}
            theme="light"
            notMerge={true}
            lazyUpdate={true}
            opts={{ renderer: 'canvas' }}
            autoResize={true}
          />
        </div>
      ))}
    </div>
  );
};
