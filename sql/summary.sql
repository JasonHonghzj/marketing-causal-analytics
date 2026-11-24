WITH customer_outcomes AS (
    SELECT
        segment AS arm,
        CASE
            WHEN recency <= 3 THEN '01-03 months'
            WHEN recency <= 6 THEN '04-06 months'
            ELSE '07-12 months'
        END AS recency_band,
        conversion,
        visit,
        spend_cents
    FROM experiment
),
populations AS (
    SELECT 'All customers' AS audience, arm, conversion, visit, spend_cents
    FROM customer_outcomes
    UNION ALL
    SELECT recency_band, arm, conversion, visit, spend_cents
    FROM customer_outcomes
)
SELECT
    audience,
    arm,
    COUNT(*) AS customers,
    SUM(conversion) AS conversions,
    SUM(visit) AS visits,
    SUM(spend_cents) AS spend_cents,
    SUM(spend_cents * spend_cents) AS spend_squared_cents,
    1.0 * SUM(conversion) / COUNT(*) AS conversion_rate
FROM populations
GROUP BY audience, arm
ORDER BY audience, arm;
