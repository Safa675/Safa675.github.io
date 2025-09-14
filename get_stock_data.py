import yfinance as yf
import pandas as pd

tickers = ["AAPL","JNJ","KO","XOM","JPM","SPY","QQQ"]

# Download monthly data, auto_adjust=True ensures adjusted close
data = yf.download(tickers, start="2020-10-01", end="2025-09-01", interval="1mo", group_by='ticker', auto_adjust=True)

# Create a DataFrame with only Adjusted Close (auto_adjust=True makes Close adjusted)
adj_close = pd.DataFrame({ticker: data[ticker]['Close'] if ticker in data else data['Close'][ticker] for ticker in tickers})

# Save to Excel
adj_close.to_excel("C:\\Users\\safa_\\Documents\\monthly_prices.xlsx")
print("Excel file saved successfully!")
