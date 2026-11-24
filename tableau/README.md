# Tableau Workbook

Open [Marketing Causal Analytics.twbx](Marketing%20Causal%20Analytics.twbx) and select the **Campaign decision** dashboard. The workbook uses the Tableau 2026.1 format and contains four worksheets and four aggregate CSVs referenced by relative paths. [Tableau packaged workbook documentation](https://help.tableau.com/current/pro/desktop/en-us/save_savework_packagedworkbooks.htm)

| Worksheet | What it shows | Supporting data |
| --- | --- | --- |
| Conversion by assignment | Purchase rate per assigned group, as a percentage | [Assignment summary](../reports/arm_summary.csv) |
| Conversion lift | Purchase-rate difference for the three comparisons, in percentage points | [Overall effects](../reports/overall_effects.csv) |
| Lift by months since last purchase | Purchase-rate difference against no email within each group, in percentage points | [Segment effects](../reports/segment_effects.csv) |
| Break-even cost by margin scenario | Cost ceiling per assigned customer under different margins, in US dollars | [Budget scenarios](../reports/budget_scenarios.csv) |

Hover over the bars for the associated counts and 95% confidence intervals. In the budget worksheet, the tooltip also shows the estimated net contribution per 1,000 assigned customers for four cost scenarios. The full scenario intervals and men's email retest plan are in the decision report. [Decision report](../reports/decision.md)

The workbook XML and embedded data have been validated. Rendering and interactions still need verification in Tableau Desktop, which was unavailable in the project environment. [Tableau workbook schema](https://github.com/tableau/tableau-document-schemas)
