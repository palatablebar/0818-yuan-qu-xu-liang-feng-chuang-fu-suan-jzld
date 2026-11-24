# 园区需量峰窗复算

园区能源数据专员可在工作台上传来源 CSV，对照规则判断差异，签发合格批次或记录暂缓意见。

按固定窗口对齐分表读数，缺表窗口隔离后再计算同时峰值。

已签发批次可接收上游同范围修订文件：改变峰值或分组判定时生成待复核后继批次，原签发记录继续可查；其余修订登记为无影响。

## 启动

```sh
docker compose up --build -d --wait
```

打开 <http://localhost:18312>。页面预览带异常样例。选中阶段查看计算证据，选择可签发样例并执行批次，然后提交复核意见。

## 核验

```sh
docker compose exec -T app pytest -q
```

[输入字段](docs/DATA-DICTIONARY.md) · [阶段接口](docs/HTTP.md) · [操作步骤](docs/OPERATIONS.md) · [规则与测试](docs/DEPTH.md)
