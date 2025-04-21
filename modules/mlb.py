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

def get_nl_west_standings():
    standings = statsapi.standings_data(leagueId='104')  # National League
    nl_west = standings.get(205)  # NL West division

    if not nl_west:
        return "NL West standings not found."

    # Header
    lines = ["```", "2025 NL West Standings",
             f"{'Team':<25} {'W':>2} {'L':>2}  {'PCT':>5}  {'GB':>4}"]
    
    for team in nl_west['teams']:
        name = team['name']
        w = int(team['w'])
        l = int(team['l'])
        pct = f"{w / (w + l):.3f}"
        gb = team['gb']
        lines.append(f"{name:<25} {w:>2} {l:>2}  {pct:>5}  {gb:>4}")

    lines.append("```")
    return "\n".join(lines)

def get_nl_central_standings():
    standings = statsapi.standings_data(leagueId='104')  # National League
    nl_central = standings.get(203)  # NL Central division

    if not nl_central:
        return "NL Central standings not found."

    # Header
    lines = ["```", "2025 NL Central Standings",
             f"{'Team':<25} {'W':>2} {'L':>2}  {'PCT':>5}  {'GB':>4}"]
    
    for team in nl_central['teams']:
        name = team['name']
        w = int(team['w'])
        l = int(team['l'])
        pct = f"{w / (w + l):.3f}"
        gb = team['gb']
        lines.append(f"{name:<25} {w:>2} {l:>2}  {pct:>5}  {gb:>4}")

    lines.append("```")
    return "\n".join(lines)

def get_al_east_standings():
    standings = statsapi.standings_data(leagueId='103')  # American League
    al_east = standings.get(201)  # AL East division

    if not al_east:
        return "AL East standings not found."

    # Header
    lines = ["```", "2025 AL East Standings",
             f"{'Team':<25} {'W':>2} {'L':>2}  {'PCT':>5}  {'GB':>4}"]
    
    for team in al_east['teams']:
        name = team['name']
        w = int(team['w'])
        l = int(team['l'])
        pct = f"{w / (w + l):.3f}"
        gb = team['gb']
        lines.append(f"{name:<25} {w:>2} {l:>2}  {pct:>5}  {gb:>4}")

    lines.append("```")
    return "\n".join(lines)

def get_al_west_standings():
    standings = statsapi.standings_data(leagueId='103')  # American League
    al_west = standings.get(202)  # AL West division

    if not al_west:
        return "AL West standings not found."

    # Header
    lines = ["```", "2025 AL West Standings",
             f"{'Team':<25} {'W':>2} {'L':>2}  {'PCT':>5}  {'GB':>4}"]
    
    for team in al_west['teams']:
        name = team['name']
        w = int(team['w'])
        l = int(team['l'])
        pct = f"{w / (w + l):.3f}"
        gb = team['gb']
        lines.append(f"{name:<25} {w:>2} {l:>2}  {pct:>5}  {gb:>4}")

    lines.append("```")
    return "\n".join(lines)

def get_al_central_standings():
    standings = statsapi.standings_data(leagueId='103')  # American League
    al_central = standings.get(200)  # AL Central division

    if not al_central:
        return "AL Central standings not found."

    # Header
    lines = ["```", "2025 AL Central Standings",
             f"{'Team':<25} {'W':>2} {'L':>2}  {'PCT':>5}  {'GB':>4}"]
    
    for team in al_central['teams']:
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
    print(get_nl_west_standings())
    print(get_nl_central_standings())
    print(get_al_east_standings())
    print(get_al_west_standings())
    print(get_al_central_standings())