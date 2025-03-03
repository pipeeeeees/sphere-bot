import matplotlib.pyplot as plt
import datetime
import os

def get_atl_pollen_count():
    mylist = ws.chunk_parser(ws.scrape('https://www.atlantaallergy.com/pollen_counts'),
                                       'class="pollen-num"').split(' ')
    if len(mylist) > 0:
        for i in mylist:
            try:
                j = int(i)
                return j
            except:
                continue
    if mylist == ['']:
        print(mylist)
        return None
    else:
        return 'HTML Failure'

def result_handler():
    result = get_atl_pollen_count()
    if type(result) == int:
        return f"The pollen count in Atlanta for the day is {result}"
    elif result == None:
        return "The pollen count in Atlanta has not been reported yet. Please try again later.\n\nNote: Atlanta's pollen count is not reported on the weekends (outside of pollen season).\nhttps://www.atlantaallergy.com/pollen_counts"
    elif result == 'HTML Failure':
        return "HTML Parsing Error"
    else:
        return "something broke lol"
    




def get_atl_pollen_count_by_date(date: str):
    url = f'https://www.atlantaallergy.com/pollen_counts/index/{date}'
    mylist = ws.chunk_parser(ws.scrape(url), 'class="pollen-num"').split(' ')
    
    if mylist:
        for i in mylist:
            try:
                return int(i)
            except ValueError:
                continue
    
    return None if mylist == [''] else 'HTML Failure'

def plot_pollen_counts(start_date: str, end_date: str):
    start_date = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
    end_date = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()
    dates = []
    counts = []
    
    for n in range((end_date - start_date).days + 1):
        date_str = (start_date + datetime.timedelta(n)).strftime("%Y/%m/%d")
        count = get_atl_pollen_count_by_date(date_str)
        if isinstance(count, int):
            dates.append(start_date + datetime.timedelta(n))
            counts.append(count)
    
    if dates and counts:
        os.makedirs("plots", exist_ok=True)
        plt.figure(figsize=(10, 5))
        plt.plot(dates, counts, marker='o', linestyle='-')
        plt.xlabel("Date")
        plt.ylabel("Pollen Count")
        plt.title("Atlanta Pollen Count")
        plt.xticks(rotation=45)
        plt.grid()
        plt.tight_layout()
        plt.savefig("plots/plot.png")
        plt.close()


    
if __name__ == '__main__':
    import webscraper as ws

    #print(get_atl_pollen_count_by_date("2025/02/27"))
    plot_pollen_counts("2024-01-01", "2024-12-31")

else:
    from modules import webscraper as ws