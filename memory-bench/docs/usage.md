# 使用说明（中文）

## 安装

```bash
cd memory-bench
python3 -m pip install -e .[dev]
```

## 生成数据

```bash
memory-bench generate --config configs/benchmark.yaml --output-dir data/benchmark_sets
```

## 运行评测

```bash
memory-bench eval --strategy full_context --adapter mock --config configs/benchmark.yaml
```

可选在线适配器：

```bash
export OPENAI_API_KEY=***
memory-bench eval --strategy structured_memory --adapter openai --config configs/benchmark.yaml
```

## 生成报告

```bash
memory-bench report --run outputs/runs/<run_id>.jsonl --config configs/benchmark.yaml
memory-bench compare --runs outputs/runs/run_a.jsonl outputs/runs/run_b.jsonl --name baseline_compare
```

## 测试

```bash
pytest
```

覆盖率门槛默认内置为 `>=80%`。
