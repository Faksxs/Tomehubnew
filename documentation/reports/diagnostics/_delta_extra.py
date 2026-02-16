import re
from pathlib import Path
root = Path('documentation/reports/diagnostics')
base = sorted(root.glob('l3_metrics_baseline_*.prom'))[-1]
curr = sorted(root.glob('l3_metrics_current_*.prom'))[-1]
pat = re.compile(r'^(?P<name>[a-zA-Z0-9_]+)\{(?P<labels>[^}]*)\}\s+(?P<val>[-+0-9.eE]+)$')

def parse_labels(s):
    out={}
    for p in s.split(','):
        p=p.strip()
        if '=' not in p:
            continue
        k,v=p.split('=',1)
        out[k.strip()]=v.strip().strip('"')
    return out

def load(path):
    d={}
    for ln in path.read_text(encoding='utf-8', errors='ignore').splitlines():
        m=pat.match(ln.strip())
        if not m: continue
        key=(m.group('name'), tuple(sorted(parse_labels(m.group('labels')).items())))
        d[key]=float(m.group('val'))
    return d
b=load(base); c=load(curr)

def delta(name, labels):
    key=(name, tuple(sorted(labels.items())))
    return c.get(key,0.0)-b.get(key,0.0)

cnt = delta('tomehub_ai_service_duration_seconds_count', {'operation':'generate','service':'gemini_flash'})
sumv = delta('tomehub_ai_service_duration_seconds_sum', {'operation':'generate','service':'gemini_flash'})
print(f'gemini_generate_delta_count={cnt}')
print(f'gemini_generate_delta_sum_s={sumv}')
print(f'gemini_generate_avg_s={(sumv/cnt) if cnt>0 else "N/A"}')

pc = delta('tomehub_llm_tokens_total', {'direction':'prompt','model_tier':'flash','task':'work_ai_answer'})
oc = delta('tomehub_llm_tokens_total', {'direction':'output','model_tier':'flash','task':'work_ai_answer'})
print(f'work_ai_answer_prompt_tokens_delta={pc}')
print(f'work_ai_answer_output_tokens_delta={oc}')
