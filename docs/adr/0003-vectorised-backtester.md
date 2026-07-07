# ADR-0003: Vectorised backtester with explicit look-ahead control

**Status:** accepted · 2026-07-07

## Problem
We need a backtesting engine that produces an equity curve, Sharpe ratio, and max drawdown
for rule-based strategies, models transaction costs, and — critically — cannot peek at
future data (look-ahead bias).

## Options
1. **Vectorised (pandas/NumPy)** — compute the full signal series, shift by one bar, apply
   returns as array ops. Fast, concise, testable against hand-computed values.
2. Event-driven loop — simulates order lifecycle bar by bar. More realistic (partial fills,
   intrabar stops) but 10× the code and unnecessary for daily-bar strategies.
3. An existing framework (backtrader, vectorbt) — defeats the purpose; the engine IS the
   portfolio piece.

## Decision
Vectorised engine. Core rule: **a signal computed from bar *t* earns the return of bar
*t+1*** — implemented as a single explicit `positions = signal.shift(1)` at the engine
boundary (not inside strategies), so the no-look-ahead guarantee lives in exactly one
audited line. Transaction costs are charged in basis points on every position *change*
(|Δposition| × cost_bps). Strategies are pure functions `prices → signal in {-1, 0, +1}`
(short/flat/long), which keeps them trivially unit-testable.

## Trade-offs
Vectorisation can't model intrabar execution, slippage curves, or order queuing — stated in
the README as a known simplification. Daily-close fills with bps costs are the standard
first-order approximation, and the hand-computed test vectors make the maths auditable.
