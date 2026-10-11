"""Market data: futures settlements by contract month + the physical pricing index.

Free public sources (no API key):
  * EIA "NYMEX Futures Prices" daily, contracts 1-4 by position (CL crude, HO ULSD);
    EIA stopped publishing these after 2024-04-05.
  * EIA spot assessments: WTI Cushing (RWTC), Brent (RBRTE), US Gulf Coast ULSD, NYH ULSD.
EIA publishes futures by *position* (contract 1 = nearest); we map positions to real
contract months with the exchange LTD rule so that hedges are held in specific
contracts and rolled exactly as a desk would.

All derived features are trailing (value at row j uses rows <= j only).
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

from .calendar import LTD_RULES, TradingCalendar, ym_add, ym_of

BBL_PER_GAL = 42.0

EIA_FILES = {  # series key -> EIA hist_xls file stem
    "CL1": "RCLC1d", "CL2": "RCLC2d", "CL3": "RCLC3d", "CL4": "RCLC4d",
    "HO1": "EER_EPD2F_PE1_Y35NY_DPGd", "HO2": "EER_EPD2F_PE2_Y35NY_DPGd",
    "HO3": "EER_EPD2F_PE3_Y35NY_DPGd", "HO4": "EER_EPD2F_PE4_Y35NY_DPGd",
    "WTI_SPOT": "RWTCd", "BRENT_SPOT": "RBRTEd",
    "ULSD_GC": "EER_EPD2DXL0_PF4_RGC_DPGd", "ULSD_NYH": "EER_EPD2DXL0_PF4_Y35NY_DPGd",
}
RAW_NAMES = {"CL1": "RCLC1", "CL2": "RCLC2", "CL3": "RCLC3", "CL4": "RCLC4",
             "WTI_SPOT": "RWTC", "BRENT_SPOT": "RBRTE"}


def eia_url(key: str) -> str:
    return f"https://www.eia.gov/dnav/pet/hist_xls/{EIA_FILES[key]}.xls"


def load_eia_series(key: str, raw_dir: str = "data/eia", cache_dir: str = "data/cache") -> pd.Series:
    os.makedirs(cache_dir, exist_ok=True)
    cache = os.path.join(cache_dir, f"{key}.csv")
    if os.path.exists(cache):
        s = pd.read_csv(cache, index_col=0, parse_dates=True).iloc[:, 0]
        return s.rename(key)
    path = os.path.join(raw_dir, f"{RAW_NAMES.get(key, key)}.xls")
    if not os.path.exists(path):
        raise FileNotFoundError(f"{path} missing; run scripts/fetch_data.py or download {eia_url(key)}")
    df = pd.read_excel(path, sheet_name="Data 1", skiprows=2, engine="xlrd")
    s = pd.Series(df.iloc[:, 1].astype(float).values, index=pd.to_datetime(df.iloc[:, 0]), name=key)
    s = s[~s.index.duplicated()].dropna().sort_index()
    s.to_csv(cache)
    return s


class MarketData:
    """Daily futures panel (dates x contract months) plus physical index, in $/bbl."""

    def __init__(self, name: str, root: str, fut: pd.DataFrame, index: pd.Series,
                 cal: TradingCalendar | None = None, lot_bbl: float = 1000.0,
                 rate: float = 0.04, rate_series: pd.Series | None = None, unit: str = "bbl"):
        dates = fut.index.sort_values()   # exchange days; index may be missing on some (NaN)
        self.name, self.root, self.lot, self.rate, self.unit = name, root, lot_bbl, rate, unit
        self.cal = cal or TradingCalendar(dates)
        self._ltd_fn = LTD_RULES[root]
        self._ltd: dict[int, pd.Timestamp] = {}
        self.dates = pd.DatetimeIndex(dates)
        self.months = np.array(sorted(int(c) for c in fut.columns))
        self.col = {int(k): i for i, k in enumerate(self.months)}
        F = fut.reindex(index=self.dates, columns=self.months).ffill(limit=5)
        for k in self.months:  # no stale prices after a contract expires
            F.loc[F.index > self.ltd(k), k] = np.nan
        self.F = F.to_numpy(float)
        self.I = index.reindex(self.dates).to_numpy(float)
        self.front = np.array([self.front_month(d) for d in self.dates])
        # short-term USD rate known on each date (decimal), for point-in-time financing
        self.r = (None if rate_series is None else
                  rate_series.reindex(self.dates.union(rate_series.index)).ffill().reindex(self.dates).to_numpy())
        self._features()

    # ---- contract rules -------------------------------------------------------
    def ltd(self, k: int) -> pd.Timestamp:
        if k not in self._ltd:
            self._ltd[k] = self._ltd_fn(self.cal, k)
        return self._ltd[k]

    def front_month(self, d: pd.Timestamp) -> int:
        k = ym_of(d)
        while self.ltd(k) < d:
            k = ym_add(k, 1)
        return k

    def price(self, j: int, k: int) -> float:
        c = self.col.get(k)
        return np.nan if c is None else self.F[j, c]

    # ---- trailing features (point-in-time) -----------------------------------
    def _features(self):
        T = len(self.dates)
        fc = np.array([self.col.get(k, -1) for k in self.front])

        def px(j, k):
            c = self.col.get(int(k))
            return np.nan if c is None else self.F[j, c]

        front_px = np.array([px(j, self.front[j]) for j in range(T)])
        c2 = np.array([px(j, ym_add(self.front[j], 1)) for j in range(T)])
        c3 = np.array([px(j, ym_add(self.front[j], 2)) for j in range(T)])
        dF = np.full(T, np.nan)
        dS = np.full(T, np.nan)
        for j in range(1, T):  # same-contract changes (roll-free)
            f = self.front[j - 1]
            dF[j] = px(j, f) - px(j - 1, f)
            dS[j] = (px(j, ym_add(f, 2)) - px(j, f)) - (px(j - 1, ym_add(f, 2)) - px(j - 1, f))
        dI = np.r_[np.nan, np.diff(self.I)]
        roll = np.r_[True, self.front[1:] != self.front[:-1]]
        basis = self.I - front_px
        df = pd.DataFrame({"dF": dF, "dI": np.where(roll, np.nan, dI), "dS": dS, "basis": basis,
                           "slope": (c2 - front_px) / np.abs(front_px)})
        # Min-variance hedge ratio on 10-day changes: daily changes of prices observed at
        # different times of day (spot close vs futures settle) bias a daily beta toward zero
        # (Epps effect); multi-day changes remove most of that bias.
        ok = df["dI"].notna() & df["dF"].notna()
        sI = df["dI"].where(ok, 0.0).rolling(10).sum()
        sF = df["dF"].where(ok, 0.0).rolling(10).sum()
        cov = sI.rolling(250, min_periods=60).cov(sF)
        var = sF.rolling(250, min_periods=60).var()
        self.beta = (cov / var).clip(0.5, 1.5).fillna(1.0).to_numpy()
        self.vol_front = df["dF"].rolling(60, min_periods=20).std().bfill().to_numpy()
        self.vol_spread = df["dS"].rolling(60, min_periods=20).std().bfill().to_numpy()
        self.basis_hat = df["basis"].rolling(20, min_periods=5).mean().fillna(0.0).to_numpy()
        # how unusual today's index-vs-futures gap is against the last 250 days (trailing, no look-ahead)
        bm = df["basis"].rolling(250, min_periods=60).mean()
        bs = df["basis"].rolling(250, min_periods=60).std()
        self.basis_z = ((df["basis"] - bm) / bs).replace([np.inf, -np.inf], np.nan).ffill().fillna(0.0).clip(-5, 5).to_numpy()
        self.basis = basis
        self.front_px = front_px
        self.slope = df["slope"].to_numpy()
        self.slope_mom = (df["slope"] - df["slope"].shift(20)).fillna(0.0).to_numpy()
        self.c2 = c2
        self.c3 = c3
        self.front_col = fc

    def j_of(self, d) -> int:
        """Index of first market date >= d."""
        return int(np.searchsorted(self.dates.values, np.datetime64(pd.Timestamp(d)), "left"))



def panel_from_positions(series: list[pd.Series], root: str, cal: TradingCalendar) -> pd.DataFrame:
    """Turn contract-1..n-by-position series into a dates x contract-month panel."""
    df = pd.concat(series, axis=1).sort_index()
    ltd_fn = LTD_RULES[root]
    cache: dict[int, pd.Timestamp] = {}

    def ltd(k):
        if k not in cache:
            cache[k] = ltd_fn(cal, k)
        return cache[k]

    out: dict[int, dict] = {}
    for d, row in df.iterrows():
        k = ym_of(d)
        while ltd(k) < d:
            k = ym_add(k, 1)
        for i, v in enumerate(row.values):
            if np.isfinite(v):
                out.setdefault(ym_add(k, i), {})[d] = v
    return pd.DataFrame(out).sort_index()


def load_market(kind: str = "crude", raw_dir: str = "data/eia", rate: float = 0.04) -> MarketData:
    if kind == "crude":
        futs = [load_eia_series(f"CL{i}", raw_dir) for i in range(1, 5)]
        idx = load_eia_series("WTI_SPOT", raw_dir)
        root, name, mult = "CL", "WTI Cushing spot vs NYMEX CL", 1.0
    elif kind == "ulsd":
        futs = [load_eia_series(f"HO{i}", raw_dir) for i in range(1, 5)]
        idx = load_eia_series("ULSD_GC", raw_dir)
        root, name, mult = "HO", "USGC ULSD spot vs NYMEX HO", BBL_PER_GAL
    else:
        raise ValueError(kind)
    futs = [s * mult for s in futs]
    idx = idx * mult
    cal = TradingCalendar(futs[0].index)  # exchange trading days
    panel = panel_from_positions(futs, root, cal)
    panel = panel[panel.index >= idx.index[0]]
    return MarketData(name, root, panel, idx, cal=cal, rate=rate)


# ---- gold: spot (EODHD) + USD rates (FRED via Nimble) -> carry-model forward curve ----

def load_fred(series_id: str = "DTB3", cache_dir: str = "data/fred") -> pd.Series:
    """FRED series as decimals. Fetched through Nimble (FRED is unreachable directly
    from some networks) and cached as CSV."""
    path = os.path.join(cache_dir, f"{series_id}.csv")
    if not os.path.exists(path):
        from . import nimble
        import base64
        r = nimble.extract(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}", formats=["html"])
        h = r["data"].get("html") or ""
        try:
            txt = base64.b64decode(h).decode()
        except Exception:
            txt = h
        os.makedirs(cache_dir, exist_ok=True)
        open(path, "w").write(txt)
    df = pd.read_csv(path)
    s = pd.to_numeric(df.iloc[:, 1], errors="coerce")
    return pd.Series(s.values / 100.0, index=pd.to_datetime(df.iloc[:, 0])).dropna()


def load_gold_spot(path: str = "data/gold_prices.parquet", ticker: str = "XAUUSD.FOREX") -> pd.Series:
    df = pd.read_parquet(path)
    s = df[df.ticker == ticker].set_index("date")["close"].astype(float)
    s.index = pd.to_datetime(s.index).normalize()
    s = s[s.index.dayofweek < 5]          # drop weekend prints
    return s[~s.index.duplicated()].sort_index()


def carry_panel(dates, spot, rate, lease, cal: TradingCalendar, root: str = "GC",
                n_months: int = 7) -> pd.DataFrame:
    """Monthly forwards F(t,k) = S_t * exp((r_t - lease_t) * tau_k), tau to the contract's
    last trading day: the cash-and-carry curve bullion desks hedge against."""
    ltd_fn = LTD_RULES[root]
    cache: dict[int, pd.Timestamp] = {}
    lease = np.broadcast_to(np.asarray(lease, float), (len(dates),))
    out: dict[int, dict] = {}
    for d, S, r, l in zip(dates, spot, rate, lease):
        k = ym_of(d)
        while (cache.setdefault(k, ltd_fn(cal, k))) < d:
            k = ym_add(k, 1)
        for i in range(n_months):
            kk = ym_add(k, i)
            tau = (cache.setdefault(kk, ltd_fn(cal, kk)) - d).days / 365.0
            out.setdefault(kk, {})[d] = S * np.exp((r - l) * tau)
    return pd.DataFrame(out).sort_index()


def load_yahoo_close(symbol: str = "GC=F", cache_dir: str = "data/yahoo") -> pd.Series:
    """Daily closes from Yahoo Finance's chart API (free; front-month continuous for GC=F).
    Cached as JSON so backtests are reproducible offline."""
    import json
    import time
    import urllib.request
    path = os.path.join(cache_dir, symbol.replace("=", "_") + ".json")
    if not os.path.exists(path):
        url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
               f"?period1=946684800&period2={int(time.time())}&interval=1d")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        os.makedirs(cache_dir, exist_ok=True)
        with urllib.request.urlopen(req, timeout=60) as r, open(path, "wb") as f:
            f.write(r.read())
    j = json.load(open(path))["chart"]["result"][0]
    idx = pd.to_datetime(j["timestamp"], unit="s").normalize()
    s = pd.Series(j["indicators"]["quote"][0]["close"], index=idx, dtype=float).dropna()
    return s[~s.index.duplicated(keep="last")].sort_index()


GC_ACTIVE = (2, 4, 6, 8, 10, 12)


def gc_active_month(cal: TradingCalendar, d: pd.Timestamp) -> int:
    """Contract held by the GC=F continuous series: the next even month whose first notice
    day (last business day of the prior month) is after d. Matches the roll jumps in the data."""
    k = ym_of(d)
    while True:
        if k % 100 in GC_ACTIVE and cal.last_bday_of_month(ym_add(k, -1)) > d:
            return k
        k = ym_add(k, 1)


def anchored_panel(dates, fut_active, rate, lease, cal: TradingCalendar, n_months: int = 7):
    """Monthly gold contracts anchored on the real COMEX active-month price:
    F(t,k) = GC_active(t) * exp((r_t - lease) * (tau_k - tau_active)). The active contract is the
    real settlement; other months differ from it only by carry (gold's curve is near pure carry)."""
    ltd_fn = LTD_RULES["GC"]
    cache: dict[int, pd.Timestamp] = {}
    ltd = lambda k: cache.setdefault(k, ltd_fn(cal, k))
    out: dict[int, dict] = {}
    for d, Fa, r in zip(dates, fut_active, rate):
        a = gc_active_month(cal, d)
        tau_a = (ltd(a) - d).days / 365.0
        k = ym_of(d)
        while ltd(k) < d:
            k = ym_add(k, 1)
        for i in range(n_months):
            kk = ym_add(k, i)
            out.setdefault(kk, {})[d] = Fa * np.exp((r - lease) * ((ltd(kk) - d).days / 365.0 - tau_a))
    return pd.DataFrame(out).sort_index()


def load_gold(lease: float = 0.005, start: str = "1990-01-01", source: str = "comex") -> MarketData:
    """Index = spot gold (EODHD XAUUSD close; proxy for the LBMA Gold Price, which is licensed).

    source="comex" (default): hedge instrument = REAL COMEX front/active-month futures
      (Yahoo GC=F, Aug 2000-today); non-active months differ by carry only. Captures real
      futures-vs-spot dislocations (2020 Covid, 2025-26 tariff/EFP premia).
    source="model": cash-and-carry forwards from spot (longer history, 1990-, no basis risk).
    The live layer uses the full real COMEX curve via Nimble."""
    spot = load_gold_spot()
    r = load_fred("DTB3")
    if source == "model":
        spot = spot[spot.index >= start]
        rr = r.reindex(spot.index.union(r.index)).ffill().reindex(spot.index).fillna(0.0)
        cal = TradingCalendar(spot.index)
        panel = carry_panel(spot.index, spot.values, rr.values, lease, cal)
        return MarketData("Spot gold (XAUUSD) vs carry forwards", "GC", panel, spot, cal=cal,
                          lot_bbl=100.0, rate=0.04, rate_series=r, unit="oz")
    fut = load_yahoo_close("GC=F")
    fut = fut[fut.index >= start]
    sp_al = spot.reindex(fut.index)
    bad = np.abs(np.log(fut / sp_al)) > 0.10        # bad prints (e.g. first days of the series)
    fut = fut[~bad.fillna(False)]
    dates = fut.index
    rr = r.reindex(dates.union(r.index)).ffill().reindex(dates).fillna(0.0)
    cal = TradingCalendar(dates)
    panel = anchored_panel(dates, fut.values, rr.values, lease, cal)
    m = MarketData("Spot gold (XAUUSD) vs real COMEX futures", "GC", panel, spot, cal=cal,
                   lot_bbl=100.0, rate=0.04, rate_series=r, unit="oz")
    # real futures-vs-spot basis beyond carry (log), for the synthetic generator and reporting
    sp = spot.reindex(m.dates).to_numpy()
    fa = fut.reindex(m.dates).to_numpy()
    tau_a = np.array([(m.ltd(gc_active_month(cal, d)) - d).days / 365.0 for d in m.dates])
    m.gc_basis = np.log(fa / sp) - (m.r - lease) * tau_a
    m.lease = lease
    return m