#!/usr/bin/env bash
# Draft-only IEICE Japanese letter build; no class download or modification.
set -euo pipefail

paper_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ -n "${TEX_BIN:-}" && -n "${IEICEJ_DIR:-}" ]]; then
    tex_bin="$TEX_BIN"
    class_dir="$IEICEJ_DIR"
else
    git_common="$(git -C "$paper_dir" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)" || {
        echo 'Outside the research repository, set both TEX_BIN and IEICEJ_DIR; see README.md.' >&2
        exit 1
    }
    repo_storage="$(dirname -- "$git_common")"
    tex_bin="${TEX_BIN:-$repo_storage/.runtime/letter_tex/v2026.10/portable/TinyTeX/bin/universal-darwin}"
    class_dir="${IEICEJ_DIR:-$repo_storage/.runtime/letter_tex/mirror_09affdda}"
fi
class_sha="${IEICEJ_SHA256:-36b2731a97ecbb86f02b1aff50cf38d10ae57c6f1a6448f5fc9956226412a56a}"
source_file="${1:-main.tex}"
output_dir="${2:-build}"
cd "$paper_dir"

for program in uplatex dvipdfmx kpsewhich extractbb; do
    [[ -x "$tex_bin/$program" ]] || { echo "Missing TeX program: $program" >&2; exit 1; }
done
[[ -f "$source_file" ]] || { echo "Missing manuscript source: $source_file" >&2; exit 1; }
[[ -f "$class_dir/ieicej.cls" ]] || { echo "Missing external ieicej.cls; see FORMAT.md" >&2; exit 1; }
actual_sha="$(shasum -a 256 "$class_dir/ieicej.cls" | cut -d ' ' -f 1)"
[[ "$actual_sha" == "$class_sha" ]] || { echo "IEICE class digest differs; verify the class explicitly." >&2; exit 1; }

export PATH="$tex_bin:$PATH"
export TEXINPUTS="$paper_dir:$class_dir:${TEXINPUTS:-}"
export BIBINPUTS="$paper_dir:${BIBINPUTS:-}"
export BSTINPUTS="$paper_dir:${BSTINPUTS:-}"
mkdir -p "$output_dir"
output_dir="$(cd "$output_dir" && pwd)"
job_name="$(basename "$source_file" .tex)"

# graphicx/dvipdfmx otherwise tries a shell-escape pipe for PDF dimensions.
# Extract only this manuscript's local PDF figures, before running TeX.
for figure in "$paper_dir"/figures/*.pdf; do
    [[ -f "$figure" ]] || continue
    "$tex_bin/extractbb" -x -O "$figure" >"${figure%.pdf}.xbb.tmp"
    mv -- "${figure%.pdf}.xbb.tmp" "${figure%.pdf}.xbb"
done

tex_pass() {
    "$tex_bin/uplatex" -kanji=utf8 -no-shell-escape -interaction=nonstopmode \
        -halt-on-error -file-line-error -recorder "-output-directory=$output_dir" \
        "$source_file" >"$output_dir/uplatex-$1.stdout.log" 2>&1 || {
        tail -n 45 "$output_dir/uplatex-$1.stdout.log" >&2; return 1;
    }
}

tex_pass 1
if grep -q '\\bibdata{' "$output_dir/$job_name.aux"; then
    [[ -x "$tex_bin/upbibtex" ]] || { echo 'Missing upbibtex.' >&2; exit 1; }
    (cd "$output_dir" && "$tex_bin/upbibtex" "$job_name") \
        >"$output_dir/upbibtex.stdout.log" 2>&1 || {
        tail -n 45 "$output_dir/upbibtex.stdout.log" >&2; exit 1;
    }
fi
tex_pass 2
tex_pass 3
"$tex_bin/dvipdfmx" -o "$output_dir/$job_name.pdf" "$output_dir/$job_name.dvi" \
    >"$output_dir/dvipdfmx.stdout.log" 2>&1 || {
    tail -n 45 "$output_dir/dvipdfmx.stdout.log" >&2; exit 1;
}
if grep -Eq 'Citation .* undefined|Reference .* undefined|There were undefined references' "$output_dir/$job_name.log"; then
    echo 'PDF created, but unresolved citations/references remain; inspect the log.' >&2
    exit 1
fi
if [[ "$source_file" == "main.tex" ]]; then
    cp -- "$output_dir/$job_name.pdf" "$paper_dir/manuscript_tex.pdf"
    echo "TeX PDF: $paper_dir/manuscript_tex.pdf"
else
    echo "PDF: $output_dir/$job_name.pdf"
fi
echo 'Review every page, total/body page counts, and overfull/underfull warnings before delivery.'
echo 'Default class: pinned v3.4a mirror; current official v3.4b has NOT been authenticated.'
