# Data files

Price history pulled from [EODHD](https://eodhd.com/). All prices are in USD unless the ticker or unit says otherwise.

## gold_prices.parquet

Daily spot gold OHLC from the EODHD `eod` endpoint, one row per ticker per trading day. The app reads it in the browser through `src/lib/spot.ts`.

| Ticker | Quote currency | From | To | Rows |
|---|---|---|---|---|
| `XAUUSD.FOREX` | USD | 1979-12-26 | 2026-10-10 | 12,557 |
| `XAUEUR.FOREX` | EUR | 1998-01-02 | 2026-10-10 | 8,344 |
| `XAUAUD.FOREX` | AUD | 2015-01-02 | 2026-10-09 | 3,192 |

Columns: `ticker`, `date`, `open`, `high`, `low`, `close`, `adjusted_close`, `volume`. Prices are per troy ounce. `volume` is always 0 for forex pairs.

## commodities.parquet

Energy, metal and grain prices from the EODHD Commodities API (`/api/commodities/historical/{code}`). Each series is a single price per period, not OHLC. Each series is stored at the finest interval EODHD provides for it, so the file mixes daily, weekly and monthly rows. Filter on `code` (or `interval`) before using it as a time series.

Long format, one row per code per date:

| Column | Type | Description |
|---|---|---|
| `code` | string | EODHD commodity code, e.g. `WTI` |
| `group` | string | `oil`, `fuel`, `gas`, `metal` or `agri` |
| `date` | datetime | Observation date; for monthly series, the first of the month |
| `value` | float | Price in `unit` |
| `interval` | string | `daily`, `weekly` or `monthly` |
| `unit` | string | Unit as reported by EODHD |
| `name` | string | Series name as reported by EODHD |

| Code | Group | Series | Unit | Interval | From | To | Rows |
|---|---|---|---|---|---|---|---|
| `WTI` | oil | WTI crude, Cushing OK | $/barrel | daily | 1986-01-02 | 2026-10-06 | 10,260 |
| `BRENT` | oil | Brent crude, Europe | $/barrel | daily | 1987-05-20 | 2026-10-06 | 9,992 |
| `GASOLINE_US` | fuel | US regular gasoline, retail | $/gallon | weekly | 1990-08-20 | 2026-10-05 | 1,880 |
| `DIESEL_USGULF` | fuel | Ultra-low-sulfur No. 2 diesel, US Gulf Coast | $/gallon | daily | 2006-06-14 | 2026-10-06 | 5,097 |
| `HEATING_OIL_NYH` | fuel | No. 2 heating oil, New York Harbor | $/gallon | daily | 1986-06-02 | 2026-10-06 | 10,134 |
| `JET_FUEL_USGULF` | fuel | Kerosene-type jet fuel, US Gulf Coast | $/gallon | daily | 1990-04-02 | 2026-10-06 | 9,169 |
| `PROPANE_MBTX` | gas | Propane, Mont Belvieu TX | $/gallon | daily | 1992-07-09 | 2026-10-06 | 8,583 |
| `NATURAL_GAS` | gas | Henry Hub natural gas spot | $/MMBtu | daily | 1997-01-07 | 2026-10-06 | 7,470 |
| `NATGAS_EU` | gas | Natural gas, EU | $/MMBtu | monthly | 1992-01-01 | 2026-07-01 | 415 |
| `LNG_ASIA` | gas | LNG, Asia | $/MMBtu | monthly | 1992-01-01 | 2026-07-01 | 415 |
| `ALUMINUM` | metal | Global price of aluminium | $/metric ton | monthly | 1992-01-01 | 2026-07-01 | 415 |
| `COPPER` | metal | Global price of copper | $/metric ton | monthly | 1992-01-01 | 2026-07-01 | 415 |
| `WHEAT` | agri | Global price of wheat | $/metric ton | monthly | 1992-01-01 | 2026-07-01 | 415 |

Notes:

- Daily series only have rows for days with a published price, so weekends and US holidays are missing. They are not forward-filled.
- `WTI` closed at -36.98 on 2020-04-20. This is the real settlement price, not a data error.
- The monthly series lag by about three months. On 2026-10-11, the latest available month was 2026-07.
- `GASOLINE_US` is a weekly retail pump price. The other fuel series are daily wholesale spot prices.

### Refreshing

```bash
EODHD_API_TOKEN=... python3 scripts/fetch_commodities.py
```

The script overwrites `data/commodities.parquet`. Add or remove series in the `SERIES` dict at the top of the script. Each request costs 5 EODHD API calls and returns up to 1,000 rows, so a full refresh uses about 70 requests (about 350 calls).

Reading it:

```python
import pandas as pd

df = pd.read_parquet("data/commodities.parquet")
wti = df[df.code == "WTI"].set_index("date")["value"]
daily = df[df.interval == "daily"].pivot(index="date", columns="code", values="value")
```
