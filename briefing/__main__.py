"""用法：
  python -m briefing build              抓資料、產生網站資料（docs/data）
  python -m briefing notify             依 docs/data/latest.json 發送晨報
  python -m briefing notify --dry-run   只印出訊息內容，不發送
  python -m briefing all                build + notify
"""
import argparse
import os
import sys

from . import build as build_mod
from . import notify


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    p = argparse.ArgumentParser(prog="briefing", description="每日財經晨報")
    p.add_argument("command", choices=["build", "notify", "all"])
    p.add_argument("--dry-run", action="store_true", help="只印出推播內容，不實際發送")
    args = p.parse_args(argv)
    site_url = os.environ.get("SITE_URL", "").strip()

    if args.command in ("build", "all"):
        data = build_mod.build(site_url)
        print(f"完成 {data['generated_at']}：日曆 {len(data['events'])} 筆、"
              f"已公布數據 {len(data['released'])} 筆、新聞 {len(data['news'])} 則、"
              f"行情 {len(data['markets'])} 項")
        for e in data["errors"]:
            print("  ⚠", e)

    if args.command in ("notify", "all"):
        data = build_mod.load_latest()
        if site_url:
            data["site_url"] = site_url
        if not notify.send(data, build_mod.load_config(), dry_run=args.dry_run):
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
