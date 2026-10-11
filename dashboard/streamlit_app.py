"""Goldmine dashboard, run as Streamlit in Snowflake over GOLDMINE.PUBLIC (deployed by scripts/load_snowflake.py)."""
import streamlit as st
from snowflake.snowpark.context import get_active_session

session = get_active_session()
q = lambda sql: session.sql(sql).to_pandas()

st.title("Goldmine")
st.caption("QP choice and futures hedge for physical gold and crude cargoes")

market = st.selectbox("Market", ["gold", "crude"])

st.subheader("Today's recommendation")
rec = q(f"SELECT qp, qp_month, hedged_value, is_best, declare_now, unit, asof FROM recommendations "
        f"WHERE market = '{market}' ORDER BY qp_ym")
if len(rec):
    best = rec[rec.IS_BEST].iloc[0]
    st.metric(f"Best QP (as of {best.ASOF})", f"{best.QP} · {best.QP_MONTH}",
              f"{best.HEDGED_VALUE:+.2f} $/{best.UNIT}")
    st.write("Declare now." if best.DECLARE_NOW else "Wait to declare; hedge now.")
    st.bar_chart(rec.set_index("QP")["HEDGED_VALUE"])

st.subheader("Walk-forward backtest: policy scorecard")
st.dataframe(q(f"SELECT policy, cargoes, mean_unit, std_unit, worst_unit, p5_unit, total_pnl_musd "
               f"FROM policy_scorecard WHERE market = '{market}' ORDER BY mean_unit DESC"), hide_index=True)

st.subheader("Cumulative realized P&L ($m)")
ep = q(f"SELECT policy, delivery, SUM(pnl) OVER (PARTITION BY policy ORDER BY delivery) / 1e6 AS cum "
       f"FROM backtest_episodes WHERE market = '{market}' ORDER BY delivery")
if len(ep):
    st.line_chart(ep.pivot_table(index="DELIVERY", columns="POLICY", values="CUM"))

st.subheader("QP elected by policy")
st.dataframe(q(f"SELECT policy, elected, cargoes, ROUND(share * 100, 1) AS pct FROM qp_elections "
               f"WHERE market = '{market}' ORDER BY policy, elected"), hide_index=True)

st.subheader("CME curve spreads vs front contract")
st.dataframe(q("SELECT * FROM curve_spreads ORDER BY trade_date DESC, product_id"), hide_index=True)
