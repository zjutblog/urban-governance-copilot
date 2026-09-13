import pandas as pd


def load_complaints(path: str):
    df = pd.read_csv(path, encoding="utf-8-sig", dtype=str).fillna("")
    return df.to_dict(orient="records")
