# Releasing stampede

[VERSION](VERSION) is the one source of truth. `stampede --version` prints it, and the daily update check compares it with the latest GitHub release.

1. **Bump the version:** set `VERSION` to the new `X.Y.Z`, and the same version in the `version` line of [herdr-plugin.toml](herdr-plugin.toml), the README's version badge and `stampede --version` line, and the install prompt in `site/assets/site.js` (none of them can read VERSION; `tests/test_version.py` fails when any differs).
2. **Move the changelog:** in [CHANGELOG.md](CHANGELOG.md), move the entries under `## Unreleased` to a new `## X.Y.Z (D Mon YYYY)` heading below it, and leave `## Unreleased` empty above. `tests/test_version.py` checks that the heading exists.
3. **Test:** `python3 -m unittest discover tests` passes.
4. **Merge to main**, then tag that commit: `git tag vX.Y.Z && git push origin vX.Y.Z`.
5. **Create the GitHub Release** from the tag, with the changelog section as its notes: `gh release create vX.Y.Z --title "stampede X.Y.Z" --notes-file <notes.md>`. A draft or a pre-release is not "latest", so the update check ignores it until it is published as a full release.

Tags are `v` plus the version; the update check compares them as numbers, so `v0.10.0` is newer than `v0.9.0`. Within a day of the release, every `stampede --version`, `stampede update --check` and `herdr-doctor` behind it prints one line naming the update command.
