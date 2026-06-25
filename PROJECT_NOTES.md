# SMART F&O ENGINE V6 DESIGN DOCUMENT

---

# 1. OBJECTIVE

Build a professional intraday stock ranking engine for Indian F&O stocks.

The engine should identify the highest probability intraday trading opportunities using market structure, sector rotation, institutional participation and price action.

The objective is **not** to predict every market move.

The objective is to consistently rank the best trading opportunities available on a particular trading day.

The dashboard should display only the final trading opportunities.

---

# 2. CORE DESIGN DECISION

V6 will NOT be a pass/fail screener.

V6 will be an Institutional Stock Ranking Engine.

The engine will internally evaluate dozens of conditions.

The trader should never see this complexity.

The dashboard must remain extremely simple.

Output should display only:

* Rank
* Stock
* Action (BUY / SELL)
* Entry
* Stop Loss
* Target 1
* Target 2

Nothing else.

---

# 3. MAIN PHILOSOPHY

The purpose of the scanner is NOT to generate many trades.

The purpose is to generate only the highest quality intraday opportunities.

The scanner should prefer quality over quantity.

If only one high-quality opportunity exists, it should show only one.

If three high-quality opportunities exist, it should show the best three.

If no opportunity exists, it should not force a trade.

---

# 4. TRADING EDGE PHILOSOPHY

The scanner is not designed to predict the future.

The scanner is designed to identify situations where the probability of continuation is higher than average.

No single indicator can provide a sustainable trading edge.

The edge comes from combining multiple independent market factors.

---

# 5. SOURCES OF EDGE

The scanner should evaluate every stock using the following independent components.

## Market Regime

Determine whether today's market is:

* Trending Up
* Trending Down
* Range Bound
* High Volatility

This determines the overall trading environment.

---

## Sector Rotation

Institutional money rotates between sectors.

The scanner should identify:

* Strongest sectors for BUY opportunities.
* Weakest sectors for SELL opportunities.

Stocks should always be evaluated within the context of their own sector.

---

## Relative Strength vs Sector

Every stock should be compared with its own sector index.

Examples:

LT → Capital Goods

TCS → Nifty IT

SRF → Chemicals

BUY candidates should outperform their sector.

SELL candidates should underperform their sector.

---

## Institutional Participation

The engine should identify institutional activity using:

* Relative Volume (ROLV)
* Price Expansion
* VWAP Acceptance
* Breakout Quality
* Volatility Expansion

---

## Trend Quality

Trend should never depend upon only one moving average.

Trend quality should evaluate:

* Trend direction
* Trend strength
* Pullback quality
* Momentum continuation

---

## Risk Structure

Every trade must provide acceptable risk.

Trades with excessive stop-loss distance or poor reward potential should be rejected.

---

## Execution Quality

Every trade should have:

* Confirmed Entry
* Logical Stop Loss
* Target 1
* Target 2

No discretionary changes after entry.

---

# 6. IMPORTANT DESIGN PRINCIPLE

Every indicator must answer one question.

Examples:

VWAP

→ Is institutional money accepting higher or lower prices?

Volume

→ Is participation increasing?

ATR

→ Is current volatility suitable?

Sector Strength

→ Where is money flowing today?

If an indicator cannot answer a meaningful market question, it should not be included.

---

# 7. IMPORTANT RULES

Never modify the strategy after one or two trades.

Every future modification must be supported by a statistically meaningful sample of live trades.

The engine should evolve only through evidence.

---

# 8. DEVELOPMENT PHILOSOPHY

Coding begins only after design is complete.

Every module must have a clearly defined responsibility.

No duplicate logic.

No unnecessary indicators.

No overfitting.

The final engine should be modular, maintainable, explainable and suitable for continuous research and improvement.
