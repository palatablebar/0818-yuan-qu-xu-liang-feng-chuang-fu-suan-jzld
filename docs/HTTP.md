# 阶段接口

`POST /api/stages/<stage>` 接收 `multipart/form-data`。字段 `sample=dirty`、`sample=clean` 或 `file=<CSV>` 三选一。阶段为 `intake`、`prepare`、`calculate`、`policy`、`balance`。预览不入库。

`POST /api/runs` 接收同样的输入，执行全批并返回运行报告。`GET /api/runs` 返回最近 50 批。`GET /api/runs/<id>` 查询一批和当前复核状态。

`PATCH /api/runs/<id>` 接收 `revision`、`status` 和 `note`。状态使用 `APPROVED` 或 `HELD`。冲突返回 409，客户端读取新版本后重试。

`GET /api/runs/<id>/evidence` 下载内含运行清单、行号隔离、业务证据和复核信息的 JSON。

## 修订裁决

`POST /api/runs/<id>/revisions` 接收与签发批次同范围的迟到修订文件（`file=<CSV>`），只在批次 `APPROVED` 后受理。修订行按记录键覆盖原有效行，逐组比较峰值与判定：

- 峰值读数或分组判定变化（含分组增减、记录迁移到其他业务组）：生成一个 `PENDING` 后继批次（`kind=REVISION`，`base_id` 指向原批次），原签发批次与其证据不变。返回 `outcome=SUCCESSOR` 与后继 `id`。
- 仅隔离行、备注或未改变结论的读数变化：登记 `outcome=NO_IMPACT` 与原因码（`NOTE_ONLY`、`ISOLATED_ONLY`、`NO_CONCLUSION_CHANGE`、`NO_EFFECTIVE_CHANGE`），不产生后继批次。

同一文件（按 `sha256`）对同一批次重复提交返回首次记录，不新增后继批次，也不改写已有差异记录或原批次关系。`GET /api/runs/<id>/revisions` 返回该批次的修订影响记录。
