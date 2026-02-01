#!/usr/bin/env python3
import json
with open('model_test_output/test_results_gpt-oss_20b.json') as f:
    d = json.load(f)
for t in d['comparison_v3']['tests']:
    if 'separator' in t['description'].lower():
        print('GPT-OSS V3 on separator:')
        print(t['raw_response'])
        print()
for t in d['comparison_v4']['tests']:
    if 'separator' in t['description'].lower():
        print('GPT-OSS V4 on separator:')
        print(t['raw_response'])
