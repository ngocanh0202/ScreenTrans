#!/usr/bin/env bash
# Upload build outputs to the rolling pre-release "nightly" and move its tag to this commit.
# Usage: publish-nightly.sh <file>...   (needs GH_TOKEN, GITHUB_REPOSITORY, GITHUB_SHA, GITHUB_REF_NAME)
set -euo pipefail
TAG=nightly
REPO="$GITHUB_REPOSITORY"
if gh api "repos/$REPO/git/refs/tags/$TAG" >/dev/null 2>&1; then
  gh api -X PATCH "repos/$REPO/git/refs/tags/$TAG" -f sha="$GITHUB_SHA" -F force=true >/dev/null
else
  gh api -X POST "repos/$REPO/git/refs" -f ref="refs/tags/$TAG" -f sha="$GITHUB_SHA" >/dev/null
fi
NOTES="Bản build mới nhất, tự động cập nhật mỗi lần push (nhánh ${GITHUB_REF_NAME}, commit ${GITHUB_SHA:0:7}).
Android: cài ScreenTrans-android.apk (đã kèm model). Windows: giải nén ScreenTrans-windows.zip, chạy ScreenTrans.exe.
Đây là bản thử nghiệm; bản ổn định có tag v*."
if gh release view "$TAG" --repo "$REPO" >/dev/null 2>&1; then
  gh release edit "$TAG" --repo "$REPO" --prerelease --title "ScreenTrans nightly" --notes "$NOTES"
else
  gh release create "$TAG" --repo "$REPO" --prerelease --title "ScreenTrans nightly" --notes "$NOTES"
fi
gh release upload "$TAG" "$@" --repo "$REPO" --clobber
echo "Published to https://github.com/$REPO/releases/tag/$TAG"
