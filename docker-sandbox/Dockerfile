# Claude Skills Agent - Docker MCP Sandbox
# 有状态的 Python REPL + Bash 命令执行

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    MPLCONFIGDIR=/tmp/matplotlib

# 使用阿里云镜像源（解决国内网络问题）
RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    fonts-noto-cjk \
    fonts-wqy-zenhei \
    fontconfig \
    tree \
    && fc-cache -fv \
    && rm -rf /var/lib/apt/lists/*

# 配置中文字体
RUN mkdir -p /etc/fonts/conf.d && \
    printf '<fontconfig>\n <alias>\n  <family>SimHei</family>\n  <prefer>\n   <family>Noto Sans CJK SC</family>\n   <family>WenQuanYi Zen Hei</family>\n  </prefer>\n </alias>\n</fontconfig>\n' > /etc/fonts/conf.d/99-simhei.conf

# 配置 matplotlib 使用中文字体
RUN mkdir -p /etc/matplotlib && \
    printf 'font.family : sans-serif\nfont.sans-serif : Noto Sans CJK SC, WenQuanYi Zen Hei, DejaVu Sans\naxes.unicode_minus : False\nbackend : Agg\n' > /etc/matplotlib/matplotlibrc

# 安装 Python 依赖（使用清华镜像）
COPY requirements.txt /app/
RUN pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r /app/requirements.txt

# 复制 MCP Server
COPY server.py /app/

WORKDIR /workspace

# 启动 MCP Server（通过 stdio 通信）
CMD ["python", "/app/server.py"]
