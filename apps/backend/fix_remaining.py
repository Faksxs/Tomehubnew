import os, re

files_to_fix = [
    'services/epistemic_distribution_service.py',
    'services/firestore_sync_service.py',
    'services/report_service.py',
    'services/smart_search_service.py'
]

for path in files_to_fix:
    with open(path, 'r', encoding='utf-8') as f:
        text = f.read()

    # Generic replace
    text = re.sub(r'\bTOMEHUB_CONTENT\b(?!_V2|_TAGS|_CATEGORIES)', 'TOMEHUB_CONTENT_V2', text)
    text = text.replace('source_type =', 'content_type =')
    text = text.replace('source_type IN', 'content_type IN')
    text = text.replace('source_type,', 'content_type,')
    
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)

print('Remaining isolated files fixed.')
