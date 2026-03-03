#!/bin/bash
echo "🚀 正在构建 2560 战法选股系统 Docker 镜像..."
docker build -t 2560-strategy .

if [ $? -eq 0 ]; then
    echo "✅ 镜像构建成功！"
    echo "🔄 正在启动容器..."
    docker run -d --name 2560-runner -v $(pwd)/data:/app/data 2560-strategy
    echo "✅ 容器已启动！"
    echo "📊 查看日志命令：docker logs -f 2560-runner"
    echo "🛑 停止命令：docker stop 2560-runner"
else
    echo "❌ 镜像构建失败，请检查 Docker 环境"
fi
