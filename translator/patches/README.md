# Upstream dependency

Repository: https://github.com/zyddnys/manga-image-translator.git

Pinned commit: `95227a2bb0fd306cd4f0c104d57284026f991b3a`

The upstream checkout is excluded from the parent repository. `local-fixes.patch`
preserves our two modified files (CLI and rendering). From the project root on
a fresh checkout, restore it before running `translator/setup_env.ps1`:

```powershell
git clone https://github.com/zyddnys/manga-image-translator.git translator/manga-image-translator
git -C translator/manga-image-translator checkout 95227a2bb0fd306cd4f0c104d57284026f991b3a
git -C translator/manga-image-translator apply --check ../patches/local-fixes.patch
git -C translator/manga-image-translator apply ../patches/local-fixes.patch
```

Do not reapply to the existing patched checkout. After intentional upstream code
changes, refresh the tracked patch from the project root:

```powershell
git -C translator/manga-image-translator diff --binary --output=../patches/local-fixes.patch HEAD
```

New untracked upstream files are not included by `git diff`; review upstream
`git status --short` before refreshing the patch. Updating the upstream commit
also requires updating this pin and checking the patch against the new version.
