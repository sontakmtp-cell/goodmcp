# Operating review template
1. Period, timezone, scope, sources and data-quality limitations.
2. Observed counts/rates with numerator, denominator and definitions.
3. Cash, unit economics, founder hours and concentration; explicit unknowns.
4. Up to three bottleneck hypotheses: evidence, counterevidence, uncertainty.
5. One recommended priority: mechanism, owner, action, time/budget cap, measure,
   success/failure/inconclusive thresholds and review date.
6. Stop/shrink/continue decision; distinguish recommendation from adoption.
7. Confirmation, proposed state/assumption changes and actual save result.

Example new structured history entry (replace illustrative values with real data):
```json
{
  "id": "review-20261026-153000",
  "recorded_at": "2026-10-26T15:30:00+07:00",
  "stage": "08-dashboard-review",
  "period": {"from": "2026-10-19", "to": "2026-10-25", "timezone": "Asia/Saigon"},
  "metrics": [{"name": "purchase_conversion", "numerator": 5, "denominator": 40, "value": 0.125}],
  "evidence": ["User-confirmed cohort counts; illustrative example only"],
  "unknowns": ["Delivery hours not tracked"],
  "priority": "Check largest observed drop-off with one bounded follow-up test",
  "confirmation_status": "draft",
  "next_stage": "execution"
}
```
Lead merges the real confirmed entry into existing history, preserving its shape
and earlier records.
