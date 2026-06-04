import pandas as pd

df = pd.read_csv("stock_rankings.csv")

# normalize scores into weights
df["Weight"] = df["Score"] / df["Score"].sum()

print(df[["Ticker", "Score", "Weight"]])