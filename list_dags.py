#!/usr/bin/env python
"""List all TomeHub DAGs with details"""

import re
import os

dags_dir = "dags"
print("\n" + "=" * 80)
print("TOMEHUB DAG LISTESI")
print("=" * 80)
print()

dag_files = [f for f in os.listdir(dags_dir) if f.endswith('.py') and not f.startswith('_')]

if not dag_files:
    print("⚠️  DAG bulunamadı")
else:
    print(f"📋 Mevcut DAG'lar: {len(dag_files)}\n")
    
    for i, dag_file in enumerate(dag_files, 1):
        filepath = os.path.join(dags_dir, dag_file)
        
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Extract DAG info
        dag_id_match = re.search(r'"dag_id":\s*["\']([^"\']+)["\']', content)
        schedule_match = re.search(r'"schedule_interval":\s*["\']([^"\']+)["\']', content)
        desc_match = re.search(r'"description":\s*["\']([^"\']+)["\']', content)
        owner_match = re.search(r'"owner":\s*["\']([^"\']+)["\']', content)
        tags_match = re.search(r'"tags":\s*\[([^\]]+)\]', content)
        
        # Count tasks
        task_count = len(re.findall(r'@task', content))
        
        dag_id = dag_id_match.group(1) if dag_id_match else dag_file.replace('.py', '')
        
        print(f"┌─ {i}. {dag_id}")
        print(f"│")
        print(f"├─ Dosya:           {filepath}")
        print(f"├─ Status:         ✅ Ready")
        
        if desc_match:
            print(f"├─ Açıklama:        {desc_match.group(1)[:50]}")
        
        if schedule_match:
            sched = schedule_match.group(1)
            if sched == "0 2 * * *":
                print(f"├─ Schedule:        Her gün 02:00 UTC (Cron: {sched})")
            else:
                print(f"├─ Schedule:        {sched}")
        
        if tags_match:
            tags = [t.strip().strip("'\"") for t in tags_match.group(1).split(',')]
            print(f"├─ Tags:            {', '.join(tags)}")
        
        if owner_match:
            print(f"├─ Owner:           {owner_match.group(1)}")
        
        if task_count > 0:
            print(f"├─ Tasks:           {task_count}")
        
        print(f"└─")
        print()

print("=" * 80)
print(f"✅ Toplam DAG Sayısı: {len(dag_files)}")
print("=" * 80)
print()

# Show next scheduled runs
if dag_files:
    print("\n📅 SONRAKI ÇALIŞMA SAATLERİ:")
    print("-" * 80)
    for dag_file in dag_files:
        filepath = os.path.join(dags_dir, dag_file)
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        dag_id_match = re.search(r'"dag_id":\s*["\']([^"\']+)["\']', content)
        schedule_match = re.search(r'"schedule_interval":\s*["\']([^"\']+)["\']', content)
        
        dag_id = dag_id_match.group(1) if dag_id_match else dag_file.replace('.py', '')
        schedule = schedule_match.group(1) if schedule_match else "N/A"
        
        if schedule == "0 2 * * *":
            print(f"  • {dag_id:40} → Her gün 02:00 UTC")
        else:
            print(f"  • {dag_id:40} → {schedule}")
    print()
