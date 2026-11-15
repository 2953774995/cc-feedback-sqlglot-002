#!/bin/bash
# 验收入口：探针 + lineage 回归 + 全量测试。
# 在仓库根目录运行：./test.sh
cd "$(dirname "$0")"

PY=.venv/bin/python
if [ ! -x "$PY" ]; then
    PY=python3
fi

echo "============================================================"
echo "第一部分：列级血缘验收探针（DML 语句）"
echo "============================================================"
$PY probes/run_probes.py
PROBE_RC=$?
echo

echo "============================================================"
echo "第二部分：lineage 回归测试（原有 SELECT/CTE 行为不得破坏）"
echo "============================================================"
$PY -m pytest -q tests/test_lineage.py 2>&1 | tail -6
PYTEST_RC=${PIPESTATUS[0]}
echo

echo "============================================================"
echo "第三部分：全量测试"
echo "（排除依赖 duckdb 的 test_executor/test_optimizer，"
echo "  以及基线在 pytz/时区环境下本就失败 6 例的 dialects/test_postgres）"
echo "============================================================"
$PY -m pytest -q tests/ --ignore=tests/test_executor.py \
    --ignore=tests/test_optimizer.py \
    --ignore=tests/dialects/test_postgres.py 2>&1 | tail -8
FULL_RC=${PIPESTATUS[0]}
echo

echo "############################################################"
echo "# 汇总"
echo "############################################################"
[ $PROBE_RC -eq 0 ] && echo "验收探针：PASS" || echo "验收探针：FAIL"
[ $PYTEST_RC -eq 0 ] && echo "lineage 回归：PASS" || echo "lineage 回归：FAIL"
[ $FULL_RC -eq 0 ] && echo "全量测试：PASS" || echo "全量测试：FAIL"

if [ $PROBE_RC -eq 0 ] && [ $PYTEST_RC -eq 0 ] && [ $FULL_RC -eq 0 ]; then
    echo
    echo "总体结果：全部通过"
    exit 0
fi
echo
echo "总体结果：存在未通过项"
exit 1
