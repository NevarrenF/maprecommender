import os
import sys
import requests
import random
import re

# === CONFIGURATION ===
USER_FAVORITES_LIMIT = 10
USER_NOMINATIONS_LIMIT = 10
MAPPER_RANKED_LIMIT = 3
MAPPER_NOMINATIONS_LIMIT = 3
MAPPER_FAVORITES_LIMIT = 3
FINAL_RANDOM_RECOMMENDATIONS = 10
GROUP_TOP_NOMINATIONS = 3
GROUPS_FILE = "sds.txt"
ENABLE_GROUP_RECOMMENDATIONS = False

api_call_counter = 0  # Global API call counter

def api_get(url, token):
    global api_call_counter
    api_call_counter += 1
    return requests.get(url, headers={'Authorization': f'Bearer {token}'})

def load_env(filepath='.env'):
    if not os.path.exists(filepath):
        print(f"Warning: {filepath} not found.")
        return
    with open(filepath, 'r') as f:
        for line in f:
            if '=' in line and not line.startswith('#'):
                key, value = line.strip().split('=', 1)
                os.environ[key] = value

load_env()

CLIENT_ID = os.getenv('OSU_CLIENT_ID')
CLIENT_SECRET = os.getenv('OSU_CLIENT_SECRET')

def get_token():
    url = 'https://osu.ppy.sh/oauth/token'
    data = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'grant_type': 'client_credentials',
        'scope': 'public'
    }
    response = requests.post(url, json=data)
    if response.status_code == 200:
        return response.json()['access_token']
    else:
        print("[!] Failed to get token.")
        sys.exit(1)

def get_user_favorites(user_id, token, limit):
    response = api_get(f'https://osu.ppy.sh/api/v2/users/{user_id}/beatmapsets/favourite?limit={limit}', token)
    return response.json() if response.status_code == 200 else []

def get_user_nominations(user_id, token, limit):
    response = api_get(f'https://osu.ppy.sh/api/v2/users/{user_id}/beatmapsets/nominated?limit={limit}', token)
    if response.status_code == 200:
        return response.json()
    elif response.status_code == 404:
        return []
    else:
        return []

def get_mapper_nominations(mapper_id, token):
    response = api_get(f'https://osu.ppy.sh/api/v2/users/{mapper_id}/beatmapsets/nominated?limit=100', token)
    if response.status_code == 200:
        return response.json()
    elif response.status_code == 404:
        return []
    else:
        return []

def resolve_username(username, token):
    response = api_get(f'https://osu.ppy.sh/api/v2/users/{username}', token)
    if response.status_code == 200:
        data = response.json()
        return data['id'], data['username']
    else:
        print(f"[!] Failed to resolve user {username}")
        return None, None

def parse_groups_file(filepath):
    groups = {}
    current_group = None
    skip_group = False
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line.startswith('//'):
                current_group = None
                skip_group = True
                continue
            if re.match(r'^[a-zA-Z0-9_]+$', line):
                current_group = line
                skip_group = False
                groups[current_group] = []
            elif not skip_group and current_group:
                groups[current_group].extend(line.split())
    return groups

def get_all_group_nominations(groups, token):
    map_nominations = {}
    print(f"\n=== Collecting nominations for all groups ===")
    for group, members in groups.items():
        for name in members:
            user_id, display_name = resolve_username(name.strip("'\""), token)
            if not user_id:
                continue
            nominations = get_mapper_nominations(user_id, token)
            for mapset in nominations:
                if mapset.get('ranked_date'):
                    mid = mapset.get('id')
                    if mid not in map_nominations:
                        map_nominations[mid] = {
                            "mapset_id": mid,
                            "title": mapset.get('title'),
                            "artist": mapset.get('artist'),
                            "creator": mapset.get('creator'),
                            "ranked_date": mapset.get('ranked_date'),
                            "nominators": set(),
                            "groups": set()
                        }
                    map_nominations[mid]["nominators"].add(display_name)
                    map_nominations[mid]["groups"].add(group)
    print(f"Collected {len(map_nominations)} unique group maps (API Calls: {api_call_counter})")
    return map_nominations

def get_recommendations(user_id):
    global api_call_counter
    token = get_token()

    favorites = get_user_favorites(user_id, token, USER_FAVORITES_LIMIT)
    print(f"\n=== User Favorites ({len(favorites)}) (API Calls: {api_call_counter}) ===")
    for mapset in favorites:
        print(f"{mapset['artist']} - {mapset['title']} by {mapset['creator']} | {mapset['id']}")

    nominations = get_user_nominations(user_id, token, USER_NOMINATIONS_LIMIT)
    print(f"\n=== User Nominations ({len(nominations)}) (API Calls: {api_call_counter}) ===")
    for mapset in nominations:
        print(f"{mapset['artist']} - {mapset['title']} by {mapset['creator']} | {mapset['id']}")

    mappers = [mapset['user_id'] for mapset in favorites + nominations]
    all_recs = []
    print(f"\n=== Collecting Nominations from user's favorite & nominated mappers ===")
    for mapper_id in set(mappers):
        recs = get_mapper_nominations(mapper_id, token)
        for mapset in recs:
            if mapset.get('ranked_date'):
                print(f"{mapset['artist']} - {mapset['title']} by {mapset['creator']} | {mapset['id']} ({mapset['ranked_date']})")
                all_recs.append(mapset)
    print(f"Collected {len(all_recs)} maps from mappers (API Calls: {api_call_counter})")

    unique_recs = {rec.get('id'): rec for rec in all_recs if rec.get('ranked_date')}.values()
    final_user_recs = random.sample(list(unique_recs), min(FINAL_RANDOM_RECOMMENDATIONS, len(unique_recs)))

    output_file = f"recommendations_{user_id}.txt"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(f"=== {FINAL_RANDOM_RECOMMENDATIONS} Personalized Recommendations ===\n\n")
        for rec in final_user_recs:
            f.write(f"{rec['artist']} - {rec['title']} by {rec['creator']} | https://osu.ppy.sh/beatmapsets/{rec['id']}\n")

        if ENABLE_GROUP_RECOMMENDATIONS:
            groups = parse_groups_file(GROUPS_FILE)
            print(f"\nLoaded groups from {GROUPS_FILE}: {list(groups.keys())}")
            map_nominations = get_all_group_nominations(groups, token)

            group_recommendations = {}
            for group in groups:
                maps_in_group = [
                    m for m in map_nominations.values() if group in m['groups']
                ]
                sorted_maps = sorted(maps_in_group, key=lambda x: x['ranked_date'], reverse=True)
                group_recommendations[group] = sorted_maps[:GROUP_TOP_NOMINATIONS]

            for group, recs in group_recommendations.items():
                f.write(f"\n=== Group: {group} ===\n\n")
                for rec in recs:
                    f.write(f"{rec['artist']} - {rec['title']} by {rec['creator']} | https://osu.ppy.sh/beatmapsets/{rec['mapset_id']}\n")
        else:
            print("\n[!] Group recommendations are disabled by configuration.")

    print(f"\nAll recommendations written to {output_file}")
    print(f"Total API calls made: {api_call_counter}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python main.py <osu_user_id>")
        sys.exit(1)

    user_id = sys.argv[1]
    get_recommendations(user_id)
