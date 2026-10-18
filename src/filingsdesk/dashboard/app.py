"""Streamlit dashboard: backtest explorer + filings Q&A, talking to the API.

Run: streamlit run src/filingsdesk/dashboard/app.py
Configure the API base URL with FILINGSDESK_API_URL (default http://localhost:8000).
"""

import os

import httpx
import pandas as pd
import streamlit as st

API_URL = os.environ.get("FILINGSDESK_API_URL", "http://localhost:8000")

st.set_page_config(page_title="FilingsDesk", page_icon="📈", layout="wide")
st.title("FilingsDesk")
st.caption("Market data · vectorised backtesting · citation-grounded filings Q&A")


@st.cache_data(ttl=60)
def fetch_instruments() -> list[str]:
    response = httpx.get(f"{API_URL}/instruments", timeout=10)
    response.raise_for_status()
    return [row["symbol"] for row in response.json()]


try:
    symbols = fetch_instruments()
except Exception:
    st.error(f"API unreachable at {API_URL}. Start it and ingest data first.")
    st.stop()

if not symbols:
    st.warning("No instruments ingested yet — run `filingsdesk-ingest --fixtures`.")
    st.stop()

backtest_tab, ask_tab = st.tabs(["Backtest", "Ask the filings"])

with backtest_tab:
    controls, chart = st.columns([1, 3])
    with controls:
        symbol = st.selectbox("Instrument", symbols)
        strategy = st.selectbox("Strategy", ["ma_crossover", "momentum"])
        if strategy == "ma_crossover":
            fast = st.slider("Fast MA", 2, 100, 20)
            slow = st.slider("Slow MA", 5, 250, 50)
            params = {"fast": fast, "slow": slow}
        else:
            params = {"lookback": st.slider("Lookback", 5, 250, 63)}
        cost_bps = st.slider("Cost (bps)", 0, 100, 10)
        run = st.button("Run backtest", type="primary")

    if run:
        response = httpx.post(
            f"{API_URL}/backtest",
            json={"symbol": symbol, "strategy": strategy, "params": params, "cost_bps": cost_bps},
            timeout=30,
        )
        if response.status_code != 200:
            st.error(response.json().get("detail", response.text))
        else:
            body = response.json()
            with chart:
                curve = pd.DataFrame(body["equity_curve"]).set_index("date")
                st.line_chart(curve, y="equity")
            metric_cols = st.columns(5)
            metrics = body["metrics"]
            metric_cols[0].metric("Total return", f"{metrics['total_return']:.1%}")
            metric_cols[1].metric("Sharpe", f"{metrics['sharpe']:.2f}")
            metric_cols[2].metric("Max drawdown", f"-{metrics['max_drawdown']:.1%}")
            metric_cols[3].metric("Volatility", f"{metrics['volatility']:.1%}")
            metric_cols[4].metric("Trades", int(metrics["n_trades"]))

with ask_tab:
    question = st.text_input(
        "Question", placeholder="How fast did Apple's Services segment net sales grow?"
    )
    if question:
        with st.spinner("Searching the filings..."):
            response = httpx.post(f"{API_URL}/ask", json={"question": question}, timeout=60)
        if response.status_code != 200:
            st.error(response.text)
        else:
            body = response.json()
            answered_by = body.get("answered_by", "extractive")
            st.caption(
                f"Answered by **{'Claude' if answered_by == 'claude' else 'extractive quotes'}**"
                f" · confidence **{body['confidence']}**"
            )
            if body["refused"]:
                st.warning(body["answer"])
            else:
                if body["confidence"] == "low":
                    st.info("Low confidence: a claim was dropped or retrieval was weak.")
                st.write(body["answer"])
                if body.get("evidence"):
                    with st.expander(
                        "Verified quotes (each checked word for word against its source)"
                    ):
                        for quote in body["evidence"]:
                            st.markdown(f"> {quote}")
                st.subheader("Sources")
                for citation in body["citations"]:
                    label = f"{citation['symbol']} {citation['form_type']}"
                    if citation.get("url"):
                        label = f"[{label}]({citation['url']})"
                    st.markdown(
                        f"**[{citation['marker']}]** {label} · {citation['section'] or 'n/a'} · "
                        f"`{citation['accession_no']}`"
                    )
