# Changelog

## [Unreleased]

- Added timezone-aware scheduling fields (`TIMEZONE`, `SCHEDULE_TIME`, `POST_MARKET_DELAY`) for post-close delivery.
- Switched the default historical lookback to 252 trading days and added long-term context enrichment such as fundamentals, 52-week range, and relative strength vs `SPY`.
- Changed stock news search to merge multiple providers in parallel, including Yahoo Finance RSS, with URL deduplication and fuller article excerpts.
- Updated the LLM/report flow toward long-term investing outputs with `Accumulate / Hold / Trim / Exit / Watch`, `time_horizon`, macro context, and more actionable email summaries.
