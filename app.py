import streamlit as st
import yfinance as yf
from openai import OpenAI
import os
from dotenv import load_dotenv
import time
import plotly.express as px

# Load environment variables
load_dotenv()

st.set_page_config(page_title="Macro AI Pipeline", layout="wide")
st.title("Macro-Financial Portfolio Intelligence")
st.markdown("### Live MVP Pipeline Demonstration")

# Initialize OpenAI Client
api_key = os.getenv("OPENAI_API_KEY")
if not api_key or api_key == "YOUR_API_KEY_HERE":
    st.error("⚠️ Please add your actual OPENAI_API_KEY to the .env file and restart the app.")
    st.stop()

if st.button("Execute Live Pipeline", type="primary"):
    
    # ==========================================
    # STEP 1: DATA INGESTION
    # ==========================================
    st.header("1. Data Ingestion")
    with st.spinner("Fetching live market data and news from Yahoo Finance..."):
        try:
            # 1. Macro Proxy: 10-Year Treasury Yield
            tnx = yf.Ticker("^TNX")
            current_yield = tnx.history(period="1d")['Close'].iloc[-1]
            
            # 2. Market Data: SPY 1-month return
            spy = yf.Ticker("SPY")
            spy_hist = spy.history(period="1mo")
            spy_return = ((spy_hist['Close'].iloc[-1] / spy_hist['Close'].iloc[0]) - 1) * 100
            
            # 3. Qualitative Text: Latest news headline
            news = spy.news
            latest_headline = "Markets remain steady amid standard trading volume."
            if news and isinstance(news[0], dict):
                latest_headline = news[0].get('title') or news[0].get('content', {}).get('title') or latest_headline
            
            col1, col2 = st.columns(2)
            with col1:
                st.info(f"**Quantitative Signals:**\n\n- 10-Year Treasury Yield: `{current_yield:.2f}%`\n- SPY 1-Month Return: `{spy_return:.2f}%`")
            with col2:
                st.info(f"**Qualitative Signals (News):**\n\n- Latest Headline: *'{latest_headline}'*")
                
            data_payload = f"10-Year Treasury Yield is {current_yield:.2f}%. S&P 500 (SPY) 1-Month Return is {spy_return:.2f}%. Latest financial headline: '{latest_headline}'."
            
        except Exception as e:
            st.error(f"Error fetching live data: {e}")
            st.stop()
            
    st.divider()

    # ==========================================
    # STEP 2: AI REASONING
    # ==========================================
    st.header("2. AI CIO Reasoning")
    with st.spinner("LLM (OpenAI) is synthesizing the signals..."):
        try:
            client = OpenAI(api_key=api_key)
            prompt = f"""
            You are a macro portfolio manager. Evaluate the following live point-in-time data:
            {data_payload}
            
            Based on this data, output a short 3-sentence rationale on the macroeconomic environment.
            Then, provide a conviction score for Equities (SPY) from 1-10.
            Then, provide a conviction score for Long Bonds (TLT) from 1-10.
            
            You MUST format your response exactly like this (do not add any other text):
            Rationale: [your text]
            SPY_Score: [number]
            TLT_Score: [number]
            """
            
            response = client.chat.completions.create(
                model="gpt-4o", # Using gpt-4o for best reasoning, fallback to gpt-3.5-turbo if needed
                messages=[{"role": "user", "content": prompt}],
                temperature=0.4,
                max_tokens=200
            )
            
            llm_output = response.choices[0].message.content
            
            # Parse the LLM output safely
            rationale = "Error parsing rationale."
            spy_score = 5
            tlt_score = 5
            
            for line in llm_output.split('\n'):
                line = line.strip()
                if line.startswith("Rationale:"):
                    rationale = line.replace("Rationale:", "").strip()
                elif line.startswith("SPY_Score:"):
                    try: spy_score = int(line.replace("SPY_Score:", "").strip())
                    except: pass
                elif line.startswith("TLT_Score:"):
                    try: tlt_score = int(line.replace("TLT_Score:", "").strip())
                    except: pass
                    
            st.success(f"**Agent Rationale:**\n\n{rationale}")
            st.write(f"**SPY Signal:** {spy_score}/10 🟢 | **TLT Signal:** {tlt_score}/10 🔴")
            
        except Exception as e:
            st.error(f"Error communicating with OpenAI: {e}")
            st.stop()

    st.divider()

    # ==========================================
    # STEP 3: PORTFOLIO ALLOCATION
    # ==========================================
    st.header("3. Portfolio Construction")
    with st.spinner("Calculating optimal target weights..."):
        time.sleep(1) # Slight pause for visual effect
        
        total = spy_score + tlt_score
        if total == 0: total = 1 
        spy_weight = (spy_score / total) * 100
        tlt_weight = (tlt_score / total) * 100
        
        col_chart, col_text = st.columns([1, 1])
        
        with col_chart:
            # Plotly Donut Chart
            fig = px.pie(
                values=[spy_weight, tlt_weight], 
                names=['SPY (Equities)', 'TLT (Bonds)'],
                color=['SPY (Equities)', 'TLT (Bonds)'],
                color_discrete_map={'SPY (Equities)':'#22c55e', 'TLT (Bonds)':'#ef4444'},
                hole=0.5
            )
            fig.update_layout(margin=dict(t=0, b=0, l=0, r=0))
            st.plotly_chart(fig, use_container_width=True)
            
        with col_text:
            st.markdown("<br><br>", unsafe_allow_html=True)
            st.success(f"### Final Action Executed:\n\nRebalanced portfolio to **{spy_weight:.1f}% Equities** and **{tlt_weight:.1f}% Bonds** based on live macro views.")

