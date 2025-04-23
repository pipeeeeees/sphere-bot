import statsapi
from datetime import datetime

def get_standings(league_id, division_id, title):
    today = datetime.today().strftime("%m-%d-%Y")
    full_title = f"{title} - {today}"

    standings = statsapi.standings_data(leagueId=league_id)
    division = standings.get(division_id)

    if not division:
        return f"{full_title} standings not found."

    lines = ["```", full_title, f"{'Team':<25} {'W':>2} {'L':>2}  {'GB':>4}"]
    for team in division['teams']:
        name = team['name']
        w = int(team['w'])
        l = int(team['l'])
        gb = team['gb']
        lines.append(f"{name:<25} {w:>2} {l:>2}  {gb:>4}")
    lines.append("```")

    return "\n".join(lines)

if __name__ == "__main__":
    print(get_standings(104, 204, "NL East Standings"))
    print(get_standings(104, 205, "NL West Standings"))
    print(get_standings(104, 203, "NL Central Standings"))
    print(get_standings(103, 201, "AL East Standings"))
    print(get_standings(103, 202, "AL West Standings"))
    print(get_standings(103, 200, "AL Central Standings"))
