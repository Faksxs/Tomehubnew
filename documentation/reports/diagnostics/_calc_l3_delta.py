import re
from pathlib import Path
from datetime import datetime
root = Path('documentation/reports/diagnostics')
base_candidates = sorted(root.glob('l3_metrics_baseline_*.txt'))
curr_candidates = sorted(root.glob('l3_metrics_current_*.txt'))
if not base_candidates:
    raise SystemExit('no baseline file found')
if not curr_candidates:
    raise SystemExit('no current file found')
base_path = base_candidates[-1]
curr_path = curr_candidates[-1]

pat = re.compile(r'^(?P<name>[a-zA-Z0-9_]+)\{(?P<labels>[^}]*)\}\s+(?P<val>[-+0-9.eE]+)$')

def parse_labels(s):
    out = {}
    for part in s.split(','):
        part = part.strip()
        if not part or '=' not in part:
            continue
        k,v = part.split('=',1)
        out[k.strip()] = v.strip().strip('"')
    return out

def load(path):
    d = {}
    for ln in path.read_text(encoding='utf-8', errors='ignore').splitlines():
        ln = ln.strip()
        if not ln or ln.startswith('#'):
            continue
        m = pat.match(ln)
        if not m:
            continue
        name = m.group('name')
        labels = parse_labels(m.group('labels'))
        key = (name, tuple(sorted(labels.items())))
        d[key] = float(m.group('val'))
    return d

base = load(base_path)
curr = load(curr_path)

def get(name, labels):
    key = (name, tuple(sorted(labels.items())))
    return base.get(key, 0.0), curr.get(key, 0.0)

rows = []
for handler in ['/api/search', '/api/chat']:
    bcnt, ccnt = get('http_request_duration_seconds_count', {'handler':handler,'method':'POST'})
    bsum, csum = get('http_request_duration_seconds_sum', {'handler':handler,'method':'POST'})
    dcnt = ccnt - bcnt
    dsum = csum - bsum
    avg = (dsum / dcnt) if dcnt > 0 else None
    rows.append((f'endpoint:{handler}', dcnt, dsum, avg))

for phase in ['retrieval','prompt_build','llm_generate']:
    bcnt, ccnt = get('tomehub_l3_phase_latency_seconds_count', {'phase':phase})
    bsum, csum = get('tomehub_l3_phase_latency_seconds_sum', {'phase':phase})
    dcnt = ccnt - bcnt
    dsum = csum - bsum
    avg = (dsum / dcnt) if dcnt > 0 else None
    rows.append((f'phase:{phase}', dcnt, dsum, avg))

report_lines = []
report_lines.append(f'baseline={base_path.as_posix()}')
report_lines.append(f'current={curr_path.as_posix()}')
report_lines.append(f'generated_at={datetime.utcnow().isoformat()}Z')
report_lines.append('')
for name, dcnt, dsum, avg in rows:
    if avg is None:
        report_lines.append(f'{name}: delta_count=0 delta_sum_s=0 avg_s=N/A')
    else:
        report_lines.append(f'{name}: delta_count={dcnt:.0f} delta_sum_s={dsum:.6f} avg_s={avg:.6f}')

out_path = root / f'l3_metrics_delta_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.txt'
out_path.write_text('\n'.join(report_lines), encoding='utf-8')
print('\n'.join(report_lines))
print(f'out={out_path.as_posix()}')
