#!/usr/bin/env python3
# stdlib-only; requires GitHub CLI installed and authenticated (gh auth status)
import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, UTC
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR_DEFAULT = ROOT / "docs/codex/reviews"


def sh(*args, capture=True, text=True):
    res = subprocess.run(args, check=True, capture_output=capture, text=text)
    return (res.stdout or "").strip()


def try_sh(*args):
    try:
        return sh(*args)
    except subprocess.CalledProcessError:
        return ""


def repo_slug():
    # Prefer gh’s view (respects gh default repo); fallback to parsing git remote.
    slug = try_sh("gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner")
    if slug:
        return slug
    url = try_sh("git", "remote", "get-url", "origin")
    m = re.match(r"^git@github\.com:(.+)\.git$", url) or re.match(r"^https://github\.com/(.+)\.git$", url)
    if not m:
        print("error: cannot determine repo slug (owner/repo); set gh default repo or origin remote.", file=sys.stderr)
        sys.exit(2)
    return m.group(1)


def gh_api(path, accept="application/vnd.github+json"):
    # Uses :owner/:repo notation so `gh` injects current repo automatically.
    out = try_sh("gh", "api", "-H", f"Accept: {accept}", "--paginate", path)
    return json.loads(out or "[]")


def gh_pr_view(pr):
    fields = "title,number,author,url,createdAt,updatedAt,headRefName,baseRefName"
    out = sh("gh", "pr", "view", str(pr), "--json", fields)
    return json.loads(out)


def normalize_review(r):
    return {
        "type": "review",
        "id": r.get("id"),
        "state": r.get("state"),
        "author": (r.get("user") or {}).get("login"),
        "submitted_at": r.get("submitted_at"),
        "body": r.get("body") or "",
        "html_url": r.get("html_url"),
        "commit_id": r.get("commit_id"),
    }


def normalize_review_comment(c):
    return {
        "type": "review_comment",
        "id": c.get("id"),
        "review_id": c.get("pull_request_review_id"),
        "in_reply_to_id": c.get("in_reply_to_id"),
        "author": (c.get("user") or {}).get("login"),
        "created_at": c.get("created_at"),
        "updated_at": c.get("updated_at"),
        "path": c.get("path"),
        "diff_hunk": c.get("diff_hunk"),
        "position": c.get("position"),
        "original_position": c.get("original_position"),
        "line": c.get("line"),
        "side": c.get("side"),
        "body": c.get("body") or "",
        "html_url": c.get("html_url"),
        "commit_id": c.get("commit_id"),
    }


def normalize_issue_comment(c):
    return {
        "type": "issue_comment",
        "id": c.get("id"),
        "author": (c.get("user") or {}).get("login"),
        "created_at": c.get("created_at"),
        "updated_at": c.get("updated_at"),
        "body": c.get("body") or "",
        "html_url": c.get("html_url"),
    }


def ts(entry):
    # Sort key across types
    return entry.get("submitted_at") or entry.get("created_at") or entry.get("updated_at") or ""


def main():
    ap = argparse.ArgumentParser(description="Export reviews/comments for PRs into JSON + NDJSON.")
    ap.add_argument("prs", nargs="+", type=int, help="PR numbers (e.g., 12 34 56)")
    ap.add_argument("--out-dir", default=str(OUT_DIR_DEFAULT), help="Output directory for per-PR JSON files")
    ap.add_argument("--aggregate", default="", help="Optional path to write an aggregate NDJSON")
    args = ap.parse_args()

    slug = repo_slug()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    agg_fp = None
    if args.aggregate:
        agg_fp = Path(args.aggregate)
        agg_fp.parent.mkdir(parents=True, exist_ok=True)
        agg_f = agg_fp.open("w", encoding="utf-8")

    for pr in args.prs:
        try:
            meta = gh_pr_view(pr)
            reviews = gh_api(f"repos/:owner/:repo/pulls/{pr}/reviews")
            rev_comments = gh_api(f"repos/:owner/:repo/pulls/{pr}/comments")
            issue_comments = gh_api(f"repos/:owner/:repo/issues/{pr}/comments")
        except Exception as e:
            print(f"[warn] PR {pr}: fetch failed: {e}", file=sys.stderr)
            continue

        entries = (
            [normalize_review(r) for r in reviews]
            + [normalize_review_comment(c) for c in rev_comments]
            + [normalize_issue_comment(c) for c in issue_comments]
        )
        entries.sort(key=ts)

        data = {
            "repo": slug,
            "pr": pr,
            "meta": {
                "title": meta.get("title"),
                "number": meta.get("number"),
                "author": (meta.get("author") or {}).get("login"),
                "url": meta.get("url"),
                "createdAt": meta.get("createdAt"),
                "updatedAt": meta.get("updatedAt"),
                "head": meta.get("headRefName"),
                "base": meta.get("baseRefName"),
                "exportedAt": datetime.now(UTC).isoformat(timespec="seconds"),
            },
            "entries": entries,
        }

        out_path = out_dir / f"PR-{pr}.json"
        out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        try:
            rel = out_path.resolve().relative_to(ROOT)
        except Exception:
            rel = out_path
        print(f"Wrote {rel}")

        if agg_f:
            for e in entries:
                row = {"repo": slug, "pr": pr, **e}
                agg_f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    if agg_f:
        agg_f.flush()
        try:
            print(f"Wrote {Path(agg_f.name).resolve().relative_to(ROOT)}")
        except Exception:
            print(f"Wrote {agg_f.name}")


if __name__ == "__main__":
    main()
