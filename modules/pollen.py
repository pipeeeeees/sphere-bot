import pandas as pd
import matplotlib.pyplot as plt
import datetime
import os
import asyncio

DATA_DIR = "modules/pollen_data"
DATA_FILE = os.path.join(DATA_DIR, "pollen_counts.csv")

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

def ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(DATA_FILE):
        pd.DataFrame(columns=["date", "pollen_count"]).to_csv(DATA_FILE, index=False)

def read_pollen_data():
    ensure_data_dir()
    try:
        df = pd.read_csv(DATA_FILE, dtype={"date": str, "pollen_count": "Int64"})
        return df.set_index("date")["pollen_count"].to_dict()
    except FileNotFoundError:
        return {}

def write_pollen_data(date, count):
    ensure_data_dir()
    df = pd.read_csv(DATA_FILE, dtype={"date": str, "pollen_count": "Int64"})
    new_entry = pd.DataFrame([[date, count]], columns=["date", "pollen_count"])
    df = pd.concat([df, new_entry], ignore_index=True)
    df.to_csv(DATA_FILE, index=False)

def get_atl_pollen_count_by_date(date: str):
    data = read_pollen_data()
    if date in data:
        return data[date]
    
    url = f'https://www.atlantaallergy.com/pollen_counts/index/{date}'
    mylist = ws.chunk_parser(ws.scrape(url), 'class="pollen-num"').split(' ')
    
    for i in mylist:
        try:
            count = int(i)
            write_pollen_data(date, count)
            return count
        except ValueError:
            continue
    
    write_pollen_data(date, None)
    return None

async def plot_pollen_counts(start_date: str, end_date: str):
    start_date = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
    end_date = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()
    
    data = read_pollen_data()
    dates, counts = [], []
    
    for n in range((end_date - start_date).days + 1):
        date_str = (start_date + datetime.timedelta(n)).strftime("%Y/%m/%d")
        count = data.get(date_str, get_atl_pollen_count_by_date(date_str))
        if pd.notna(count):
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
    asyncio.run(plot_pollen_counts("1991-06-18", "2024-12-31"))
else:
    from modules import webscraper as ws