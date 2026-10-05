"""用法：python3 -m etf build [--full] [--limit N]

--full   全部重抓完整歷史（預設只抓最近一個月並與既有資料合併；每週六自動全抓）
--limit  只處理前 N 檔（本機測試用）
"""
import sys

from . import build


def main(argv):
    if not argv or argv[0] != "build":
        print(__doc__)
        return 2
    full = "--full" in argv
    limit = None
    if "--limit" in argv:
        limit = int(argv[argv.index("--limit") + 1])
    return build.run(full=full, limit=limit)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]) or 0)
