from nba_api.stats.endpoints import leaguestandings

def get_nba_standings(title, conf_filter):
    # Fetch current standings
    response = leaguestandings.LeagueStandings()
    data = response.get_data_frames()[0]

    # Filter by conference
    filtered_teams = data[data['Conference'] == conf_filter]

    # Sort by win percentage descending
    filtered_teams = filtered_teams.sort_values(by='WinPCT', ascending=False)

    # Format output
    lines = ["```", title, f"{'Team':<25} {'W':>2} {'L':>2}  {'GB':>4}"]
    for _, team in filtered_teams.iterrows():
        name = team['TeamName']
        w = int(team['WINS'])
        l = int(team['LOSSES'])
        gb = team.get('ConferenceGamesBack', '-')  # Use ConferenceGamesBack for GB
        gb_display = "-" if gb == '-' else f"{gb:.1f}"
        lines.append(f"{name:<25} {w:>2} {l:>2}  {gb_display:>4}")
    lines.append("```")

    return "\n".join(lines)

if __name__ == "__main__":
    print(get_nba_standings("Eastern Conference Standings", "East"))
    print(get_nba_standings("Western Conference Standings", "West"))
