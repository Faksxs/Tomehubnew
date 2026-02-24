import os, re
path = 'services/flow_service.py'
with open(path, 'r', encoding='utf-8') as f:
    text = f.read()

# Replace TOMEHUB_CONTENT where it is not already TOMEHUB_CONTENT_V2
text = re.sub(r'\bTOMEHUB_CONTENT\b(?!_V2|_TAGS|_CATEGORIES)', 'TOMEHUB_CONTENT_V2', text)
text = text.replace('alias = "TOMEHUB_CONTENT_V2"', 'alias = "TOMEHUB_CONTENT_V2"')

# Replace remaining 'source_type' targeting TOMEHUB_CONTENT queries
text = text.replace('source_type =', 'content_type =')
text = text.replace('source_type IN', 'content_type IN')
text = text.replace('ct.source_type', 'ct.content_type')
text = text.replace('t.source_type', 't.content_type')
text = text.replace('source_type,', 'content_type AS source_type,')

with open(path, 'w', encoding='utf-8') as f:
    f.write(text)
print('flow_service.py remaining TOMEHUB_CONTENT fixed.')
