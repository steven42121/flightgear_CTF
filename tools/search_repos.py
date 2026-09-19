import requests
import json
import base64

def search(name):
    print(f"\n=== {name} ===")
    try:
        r = requests.get(
            f'https://api.github.com/search/repositories?q={name}&sort=stars&per_page=3',
            timeout=10
        )
        items = r.json().get('items', [])
        for i in items:
            print(f"  {i['full_name']} ({i['stargazers_count']}★) {i['language']}")
            print(f"  {i.get('description', '')}")
            print(f"  {i['html_url']}")
    except Exception as e:
        print(f"  Error: {e}")

search("UltimateAntiCheat")
search("VMAware")
