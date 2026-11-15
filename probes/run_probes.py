#!/usr/bin/env python3
"""列级血缘验收探针。

契约（与 SELECT 现有行为保持一致）：
  下游节点 name 形如 "<表名或别名>.<列名>"，source.sql() 是该节点的来源关系原文。
  对 DML 语句，lineage(<列名>, <sql>) 必须能穿到真正的源表列，而不是抛 "Cannot find column"。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlglot.errors import SqlglotError  # noqa: E402
from sqlglot.lineage import lineage  # noqa: E402


def facts(col, sql):
    node = lineage(col, sql, schema=None)
    out = []
    stack = [node]
    seen = set()
    while stack:
        cur = stack.pop()
        if id(cur) in seen:
            continue
        seen.add(id(cur))
        try:
            src_sql = cur.source.sql()
        except Exception:
            src_sql = ""
        out.append((cur.name or "", src_sql))
        stack.extend(cur.downstream)
    return out


def reaches(col, sql, table, column):
    for name, src_sql in facts(col, sql):
        tail = name.split(".")[-1].strip('"`[]').lower()
        if tail != column.lower():
            continue
        if table.lower() in (name + " " + src_sql).lower():
            return True
    return False


CASES = [
    # (编号, 说明, 目标列, SQL, 期望源表, 期望源列)
    ("P1", "INSERT 列清单按位置映射投影", "b",
     "INSERT INTO t2 (b, a) SELECT c, a FROM t1", "t1", "c"),
    ("P2", "INSERT 投影带别名与表别名", "b",
     "INSERT INTO t2 (b) SELECT t.c + 1 AS c FROM t1 AS t", "t1", "c"),
    ("P3", "UPDATE ... FROM 取外部源表", "b",
     "UPDATE t2 SET b = s.x FROM src AS s WHERE t2.id = s.id", "src", "x"),
    ("P4", "UPDATE 标量子查询作为来源", "b",
     "UPDATE t2 SET b = (SELECT MAX(v) FROM t3)", "t3", "v"),
    ("P5", "MERGE 匹配分支 SET 的来源", "b",
     "MERGE INTO tgt USING src ON tgt.id = src.id "
     "WHEN MATCHED THEN UPDATE SET b = src.x", "src", "x"),
    ("P6", "MERGE 未匹配分支 INSERT VALUES 的来源", "b",
     "MERGE INTO tgt USING src ON tgt.id = src.id "
     "WHEN NOT MATCHED THEN INSERT (a, b) VALUES (src.a, src.y)", "src", "y"),
    ("P7", "回归：SELECT + CTE 现有行为不变", "b",
     "WITH x AS (SELECT a FROM t1) SELECT a AS b FROM x", "t1", "a"),
]


def main():
    passed = 0
    failed = 0
    for code, desc, col, sql, table, column in CASES:
        try:
            ok = reaches(col, sql, table, column)
            expect = f"{table}.{column}"
        except SqlglotError as exc:
            ok = False
            expect = f"{table}.{column}（实际抛出 SqlglotError: {exc}）"
        except Exception as exc:  # noqa: BLE001
            ok = False
            expect = f"{table}.{column}（实际抛出 {type(exc).__name__}: {exc}）"

        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {code} {desc}")
        print(f"        目标列 {col} → 期望到达 {expect}")
        if not ok:
            failed += 1
            try:
                for name, src_sql in facts(col, sql)[:6]:
                    print(f"        实际节点 {name!r} | {src_sql[:70]}")
            except Exception:
                pass
        else:
            passed += 1

    # 负例：列不存在必须仍然抛错，不能静默返回空结果
    neg_ok = False
    try:
        lineage("zzz", "INSERT INTO t2 (a) SELECT a FROM t1", schema=None)
    except SqlglotError:
        neg_ok = True
    except Exception:
        neg_ok = False
    print(f"[{'PASS' if neg_ok else 'FAIL'}] P8 负例：不存在的列仍须抛 SqlglotError")
    passed += int(neg_ok)
    failed += int(not neg_ok)

    total = len(CASES) + 1
    print("-" * 60)
    print(f"探针汇总：{passed}/{total} 通过")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
