# Class_up

这是一个纯软件项目工作区。

## 目录

- `src/`: 业务源码
- `tests/`: 自动化测试
- `docs/`: 需求、设计和接口文档
- `config/`: 配置模板与本地配置说明
- `scripts/`: 开发、构建、检查等脚本
- `examples/`: 最小示例或演示用例
- `tools/`: 项目辅助工具
- `.agents/`: 轻量治理真源与进展记录

## 当前命令

开发态从源码运行时先设置包路径：

```powershell
$env:PYTHONPATH='src'
```

一键视频转音频：

```powershell
python -m class_up.cli audio 输入视频.mp4 --output 输出音频.wav --overwrite
```

M1 转录流水线：

```powershell
python -m class_up.cli m1 输入视频.mp4 --config config\config.example.yaml --output-root outputs --course-title 课程名
```

旧式 M1 调用仍兼容：

```powershell
python -m class_up.cli 输入视频.mp4 --config config\config.example.yaml
```
