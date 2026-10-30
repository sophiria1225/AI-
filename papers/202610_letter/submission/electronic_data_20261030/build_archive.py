#!/usr/bin/env python3
"""Pack the listed manuscript/figure sources; enforce the user's 10 MB limit."""
from pathlib import Path
import hashlib
import io
import json
import zipfile

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'electronic_data'
LIMIT = 10_000_000
FILES = (
    'README.txt', 'manuscript.docx', 'main.tex', 'abstracts.tex', 'tables.tex',
    'references.tex', 'references.bib', 'results_tables.xlsx', 'results_data.json',
    'create_results_tables.py', 'build.sh', 'figures/control_points.png',
    'figures/control_points.pdf', 'figures/control_points.eps',
    'figures/control_points.svg', 'figures/render_control_points.py',
)


def main():
    sources = {}
    for name in FILES:
        path = DATA / name
        if not path.is_file() or path.is_symlink():
            raise SystemExit(f'Missing or symlinked source: {name}')
        sources[name] = path.read_bytes()
    expanded_size = sum(len(data) for data in sources.values())
    if expanded_size >= LIMIT:
        raise SystemExit(f'Expanded data exceeds the {LIMIT:,}-byte limit: {expanded_size:,}')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(sources):
            item = zipfile.ZipInfo('electronic_data/' + name, date_time=(2026, 10, 30, 0, 0, 0))
            item.compress_type = zipfile.ZIP_DEFLATED
            item.external_attr = (0o100755 if name == 'build.sh' else 0o100644) << 16
            archive.writestr(item, sources[name], compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    payload = buf.getvalue()
    if len(payload) >= LIMIT:
        raise SystemExit(f'ZIP exceeds the {LIMIT:,}-byte limit: {len(payload):,}')
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        if archive.testzip() is not None:
            raise SystemExit('ZIP integrity check failed')
        for name, data in sources.items():
            if archive.read('electronic_data/' + name) != data:
                raise SystemExit(f'Archive/source mismatch: {name}')
    output = ROOT / 'submission_electronic_data.zip'
    output.write_bytes(payload)
    report = {
        'purpose': 'Submission item 2: editable manuscript and figure/table source data',
        'status': 'preparation_snapshot; manuscript is still being adjusted',
        'initial_source_version': 'v26',
        'initial_source_commit': 'd45cb6cf9fb9367ab983576b69b67a03a08a9a5b',
        'final_manuscript_matches_submission_PDF_verified': False,
        'archive': output.name,
        'archive_sha256': hashlib.sha256(payload).hexdigest(),
        'archive_bytes': len(payload),
        'uncompressed_bytes': expanded_size,
        'decimal_limit_bytes': LIMIT,
        'archive_below_limit': True,
        'uncompressed_below_limit': True,
        'members': len(FILES),
        'manuscript_PDF_included': False,
        'figure_PDF_included': True,
        'files': {
            name: {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
            for name, data in sorted(sources.items())
        },
    }
    (ROOT / 'package_manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ('archive', 'archive_bytes', 'uncompressed_bytes', 'members', 'archive_sha256')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
