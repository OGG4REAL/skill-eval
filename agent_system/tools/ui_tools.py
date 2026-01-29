"""
UI 工具模块
定义前端渲染相关的客户端工具
"""
from typing import Dict, Any, List, Optional
from .base import BaseTool


class RenderChartTool(BaseTool):
    """
    图表渲染工具（客户端执行）
    
    此工具不在后端执行，而是将渲染指令传递给前端，
    由 CopilotKit Action 触发 Generative UI 组件进行渲染。
    """
    
    # 标记为客户端工具
    client_side = True
    
    @property
    def name(self) -> str:
        return "render_chart"
    
    @property
    def description(self) -> str:
        return """在前端渲染交互式图表（客户端工具，不在后端执行）。

使用场景：
- 趋势/时间序列 → line/area
- 对比/排名 → bar
- 占比/构成 → pie
- 多维/相关性 → radar/scatter

重要说明：
- 此工具为客户端渲染，调用后无需等待结果
- 图表类型必须与数据表达目标一致
- 禁止使用 matplotlib/seaborn 生成图片，必须使用此工具"""
    
    @property
    def parameters(self) -> Dict:
        return {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "图表标题"
                },
                "chart_type": {
                    "type": "string",
                    "enum": ["line", "bar", "pie", "scatter", "area", "radar", "heatmap"],
                    "description": "图表类型：line(折线图), bar(柱状图), pie(饼图), scatter(散点图), area(面积图), radar(雷达图), heatmap(热力图)"
                },
                "data": {
                    "type": "object",
                    "description": "图表数据，格式取决于图表类型",
                    "properties": {
                        "labels": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "X 轴标签或类别名称"
                        },
                        "datasets": {
                            "type": "array",
                            "description": "数据集列表",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {
                                        "type": "string",
                                        "description": "数据集名称（用于图例）"
                                    },
                                    "values": {
                                        "type": "array",
                                        "items": {"type": "number"},
                                        "description": "数据值列表"
                                    },
                                    "color": {
                                        "type": "string",
                                        "description": "可选：数据集颜色（如 #3B82F6）"
                                    }
                                },
                                "required": ["name", "values"]
                            }
                        }
                    },
                    "required": ["labels", "datasets"]
                },
                "options": {
                    "type": "object",
                    "description": "可选：图表配置选项",
                    "properties": {
                        "x_axis_label": {
                            "type": "string",
                            "description": "X 轴标签"
                        },
                        "y_axis_label": {
                            "type": "string",
                            "description": "Y 轴标签"
                        },
                        "show_legend": {
                            "type": "boolean",
                            "description": "是否显示图例",
                            "default": True
                        },
                        "stacked": {
                            "type": "boolean",
                            "description": "是否堆叠显示（仅 bar/area）",
                            "default": False
                        }
                    }
                }
            },
            "required": ["title", "chart_type", "data"]
        }
    
    def execute(self, **kwargs) -> Any:
        """
        客户端工具不需要真正执行，此方法仅作为占位符。
        实际执行由 Agent Core 拦截并返回 ClientSideToolResult。
        """
        # 此方法不会被调用，但保留以满足抽象类要求
        return f"[图表 '{kwargs.get('title', '未命名')}' 已发送到前端渲染]"


class RenderTableTool(BaseTool):
    """
    表格渲染工具（客户端执行）
    
    在前端渲染交互式数据表格，支持排序、筛选等功能。
    """
    
    client_side = True
    
    @property
    def name(self) -> str:
        return "render_table"
    
    @property
    def description(self) -> str:
        return """在前端渲染交互式数据表格（客户端工具，不在后端执行）。

使用场景：
- 结构化结果需要完整展示
- 行数 > 3 或需要排序/筛选

重要说明：
- 此工具为客户端渲染，调用后无需等待结果
- 禁止输出原始 ASCII 表格或 JSON dumps"""
    
    @property
    def parameters(self) -> Dict:
        return {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "表格标题"
                },
                "columns": {
                    "type": "array",
                    "description": "列定义",
                    "items": {
                        "type": "object",
                        "properties": {
                            "key": {
                                "type": "string",
                                "description": "列的字段名"
                            },
                            "label": {
                                "type": "string",
                                "description": "列的显示名称"
                            },
                            "type": {
                                "type": "string",
                                "enum": ["string", "number", "date", "currency", "percentage"],
                                "description": "数据类型，用于格式化显示"
                            },
                            "sortable": {
                                "type": "boolean",
                                "description": "是否可排序",
                                "default": True
                            }
                        },
                        "required": ["key", "label"]
                    }
                },
                "rows": {
                    "type": "array",
                    "description": "数据行（对象数组）",
                    "items": {
                        "type": "object"
                    }
                },
                "options": {
                    "type": "object",
                    "description": "可选配置",
                    "properties": {
                        "page_size": {
                            "type": "integer",
                            "description": "每页行数",
                            "default": 10
                        },
                        "show_pagination": {
                            "type": "boolean",
                            "default": True
                        },
                        "highlight_max": {
                            "type": "boolean",
                            "description": "是否高亮最大值",
                            "default": False
                        }
                    }
                }
            },
            "required": ["title", "columns", "rows"]
        }
    
    def execute(self, **kwargs) -> Any:
        return f"[表格 '{kwargs.get('title', '未命名')}' 已发送到前端渲染]"


class ShowNotificationTool(BaseTool):
    """
    通知提示工具（客户端执行）
    
    在前端显示临时通知消息。
    """
    
    client_side = True
    
    @property
    def name(self) -> str:
        return "show_notification"
    
    @property
    def description(self) -> str:
        return """在前端显示通知提示（客户端工具，不在后端执行）。

使用场景：
- 成功/警告/错误等重要提醒
- 需要吸引用户注意的关键信息

重要说明：
- 此工具为客户端渲染，调用后无需等待结果"""
    
    @property
    def parameters(self) -> Dict:
        return {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "通知消息内容"
                },
                "type": {
                    "type": "string",
                    "enum": ["info", "success", "warning", "error"],
                    "description": "通知类型",
                    "default": "info"
                },
                "duration": {
                    "type": "integer",
                    "description": "显示时长（毫秒），0 表示不自动关闭",
                    "default": 5000
                }
            },
            "required": ["message"]
        }
    
    def execute(self, **kwargs) -> Any:
        return f"[通知已发送: {kwargs.get('message', '')}]"


# 导出所有 UI 工具
UI_TOOLS = [
    RenderChartTool(),
    RenderTableTool(),
    ShowNotificationTool(),
]


def register_ui_tools(registry) -> None:
    """
    注册所有 UI 工具到工具注册表
    
    Args:
        registry: ToolRegistry 实例
    """
    for tool in UI_TOOLS:
        registry.register(tool)
