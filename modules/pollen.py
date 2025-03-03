import matplotlib.pyplot as plt
import datetime
import os

DATA_DIR = "modules/pollen_data"
DATA_FILE = os.path.join(DATA_DIR, "pollen_counts.csv")

def ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, "w") as f:
            f.write("date,pollen_count\n")

def read_pollen_data():
    ensure_data_dir()
    data = {}
    with open(DATA_FILE, "r") as f:
        next(f)  # Skip header
        for line in f:
            date, count = line.strip().split(",")
            data[date] = int(count)
    return data

def write_pollen_data(date, count):
    ensure_data_dir()
    with open(DATA_FILE, "a") as f:
        f.write(f"{date},{count}\n")

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
    plot_pollen_counts("2024-01-01", "2024-12-31")
else:
    from modules import webscraper as ws