import requests

def get_ap_top25():
    url = "https://ncaa-api.henrygd.me/rankings/football/fbs/associated-press"
    resp = requests.get(url, timeout=10)
    data = resp.json()

    rankings = data.get("data", [])
    if not rankings:
        return "No rankings found in API response."

    lines = []
    lines.append(f"{data.get('title', 'AP Top 25')}")
    lines.append(f"{data.get('updated', '')}")
    lines.append("-" * 40)

    for team in rankings:
        rank = team.get("RANK")
        school = team.get("SCHOOL")
        record = team.get("RECORD")
        prev = team.get("PREVIOUS")
        lines.append(f"{rank}. {school} ({record}), Prev: {prev}")

    return "\n".join(lines)

# Example usage:
if __name__ == "__main__":
    rankings_text = get_ap_top25()
    print(rankings_text)
