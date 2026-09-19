import subprocess, json, sys
r = subprocess.run(['anticheatd/build/bin/Release/anticheatd.exe', '--mode', 'selfcheck', '--json'], capture_output=True, timeout=10)
print('Return code:', r.returncode)
stdout_text = r.stdout.decode('utf-8', errors='replace')
print('STDOUT length:', len(stdout_text))
s = stdout_text.find('{')
e = stdout_text.rfind('}') + 1
print(f'JSON range: {s} to {e}')
if s >= 0 and e > s:
    try:
        jd = json.loads(stdout_text[s:e])
        print('SUCCESS! Parsed', len(jd.get('checks', [])), 'checks')
        for c in jd.get('checks', []):
            status = 'PASS' if c['passed'] else 'FAIL'
            print(f"  {c['layer']}: {status}")
    except Exception as ex:
        print(f'Error: {ex}')
        print('STDOUT content:')
        print(stdout_text[:500])
else:
    print('No JSON found in output')
    print('STDOUT content:')
    print(stdout_text[:500])
