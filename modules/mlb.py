import statsapi

def get_nl_east_standings():
    standings = statsapi.standings_data(leagueId='104')  # National League
    nl_east = standings.get(204)  # NL East division

    if not nl_east:
        return "NL East standings not found."

    # Header
    lines = ["```", "2025 NL East Standings",
             f"{'Team':<25} {'W':>2} {'L':>2}  {'PCT':>5}  {'GB':>4}"]
    
    for team in nl_east['teams']:
        name = team['name']
        w = int(team['w'])
        l = int(team['l'])
        pct = f"{w / (w + l):.3f}"
        gb = team['gb']
        lines.append(f"{name:<25} {w:>2} {l:>2}  {pct:>5}  {gb:>4}")

    lines.append("```")
    return "\n".join(lines)

if __name__ == "__main__":
    print(get_nl_east_standings())