import requests

def get_latest_free_game():
    url = 'https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions?locale=en-US&country=US&allowCountries=US'

    try:
        response = requests.get(url)
        response.raise_for_status()
    except requests.RequestException as e:
        return f"Error fetching data: {e}"

    data = response.json()

    try:
        games = data['data']['Catalog']['searchStore']['elements']
        for game in games:
            promotions = game.get('promotions')
            if promotions:
                current_promos = promotions.get('promotionalOffers')
                if current_promos:
                    title = game['title']
                    return title
        return "No free games found."
    except (KeyError, IndexError) as e:
        return f"Error parsing data: {e}"

if __name__ == '__main__':
    latest_game = get_latest_free_game()
    print(f"Latest free game of the week: {latest_game}")
