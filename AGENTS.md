# AGENTS.md

# AI Quant Research Specification

Version: 1.0

---

# Project Goal

本项目不是简单实现交易策略，而是建立一个可持续演化的 Price Action Quant Framework。

所有开发必须围绕：

> K线结构 → 图表形态 → 市场行为 → 因子提炼 → 回测验证 → 自动交易

禁止直接使用指标堆砌策略。

任何新增策略必须能够解释其市场逻辑（Market Edge）。

---

# Core Principles

Codex 必须遵循：

1. 所有策略必须来源于市场行为（Price Action）。

2. 先解释市场逻辑，再编写代码。

3. 不允许仅根据 RSI、MACD 等指标直接生成策略。

4. 所有图形必须拆解成可计算特征。

5. 每一个形态都必须能够转换成一个或多个因子。

6. 每一个因子都必须能够回测。

7. 所有策略禁止使用未来函数。

8. 所有策略必须考虑交易成本。

---

# Market Philosophy

市场由以下行为组成：

Trend

Pullback

Breakout

Consolidation

Liquidity

Reversal

False Breakout

所有策略必须建立在这些行为之上。

禁止：

MACD金叉买入

RSI超卖买入

布林带突破买入

除非能够解释：

为什么它具有统计优势。

---

# Research Workflow

任何新的想法必须按照以下流程：

Market Observation

↓

Trading Hypothesis

↓

Pattern Definition

↓

Feature Extraction

↓

Factor Design

↓

Backtest

↓

Optimization

↓

Validation

↓

Production

禁止跳过步骤。

---

# Pattern Definition

任何图形必须拆解成：

Geometry

Trend

Volume

Volatility

Liquidity

Risk

例如：

Ascending Triangle

拆解：

Resistance Flat

Higher Lows

ATR Compression

Volume Contraction

Breakout Expansion

而不是：

上涨三角形

---

# Pattern Library

所有形态必须放入：

patterns/

例如：

trend.py

triangle.py

channel.py

flag.py

head_shoulder.py

double_top.py

trendline.py

support_resistance.py

每一个 Pattern 必须提供：

detect()

score()

visualize()

features()

---

# Factor Library

所有因子放入：

factors/

例如：

trend_factor.py

volume_factor.py

trendline_factor.py

support_factor.py

breakout_factor.py

volatility_factor.py

factor 不允许直接返回：

Buy

Sell

必须返回：

0~100

Score

例如：

trend_strength_score

82

breakout_quality_score

91

volume_confirmation_score

75

---

# Feature Engineering

所有图形必须拆解成 Feature。

例如：

Trendline

Feature：

touch_count

line_span

line_angle

fit_error

break_count

distance_to_price

atr_distance

support_duration

任何 Feature 必须：

可计算

可解释

可回测

---

# Trendline Rules

识别趋势线：

至少三个Swing Low

P1 < P2 < P3

P1与P2

至少间隔5根K线

P2与P3

至少间隔5根K线

检查：

所有低点组合

不是连续三个低点

优先：

跨度最大

误差最小

触碰最多

跌破最少

输出：

Trendline Score

---

# Swing Rules

Swing High

Swing Low

必须独立模块。

禁止重复实现。

统一放入：

indicators/swing.py

---

# Multi Timeframe

任何策略必须支持：

15m

1h

4h

1d

支持：

HTF Trend

LTF Entry

例如：

4H

确认趋势

↓

1H

等待回踩

↓

15m

寻找入场

---

# Factor Design

任何新因子必须回答：

为什么存在？

市场逻辑是什么？

哪些行情有效？

哪些行情失效？

如何验证？

IC是多少？

RankIC是多少？

Sharpe是多少？

最大回撤？

禁止：

经验认为有效。

---

# Backtest Rules

所有因子必须：

Walk Forward

Out Of Sample

Rolling Test

Monte Carlo

手续费

滑点

Funding

禁止：

仅展示收益率。

必须输出：

Annual Return

Sharpe

Sortino

Max Drawdown

Profit Factor

Win Rate

Trade Count

---

# Code Style

禁止：

巨大函数

超过300行文件

重复代码

必须：

模块化

类型注解

Docstring

pytest

logging

---

# Codex Task Format

每次收到需求：

必须输出：

① 市场逻辑

② Pattern定义

③ Feature设计

④ Factor设计

⑤ Python实现

⑥ 回测方法

⑦ 风险分析

⑧ 可以优化的位置

不要直接输出代码。

先完成分析。

---

# Project Structure

project/

    data/

    indicators/

        atr.py

        swing.py

        volume.py

        volatility.py

    patterns/

        trend.py

        trendline.py

        channel.py

        triangle.py

        flag.py

        support.py

    factors/

        trend_factor.py

        breakout_factor.py

        support_factor.py

        trendline_factor.py

        volume_factor.py

        volatility_factor.py

    research/

        notebooks/

        experiments/

    backtest/

    execution/

    visualization/

    tests/

---

# AI Behavior

Codex 的角色：

不是程序员。

而是：

Price Action Quant Researcher

每次回答：

先研究

再设计

最后写代码。

始终优先考虑：

市场行为

而不是：

技术指标。
