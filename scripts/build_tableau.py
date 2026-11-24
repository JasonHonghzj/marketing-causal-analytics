"""Build a portable Tableau workbook using only the experiment result aggregates."""

from pathlib import Path
from uuid import NAMESPACE_URL, uuid5
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TITLE = "Marketing Causal Analytics"
VERSION = "26.1"
ARM_LABEL = {"Mens E-Mail": "Men’s email", "Womens E-Mail": "Women’s email", "No E-Mail": "No email"}


def add(parent, tag, text=None, **attributes):
    node = ET.SubElement(parent, tag, attributes)
    node.text = text
    return node


def results(filename):
    return pd.read_csv(ROOT / "reports" / f"{filename}.csv")


def result_views():
    rates = results("arm_summary").query("audience == 'All customers'")
    overall = results("overall_effects")
    segments = results("segment_effects")
    budget = results("budget_scenarios")
    budget_marks = []
    for (arm, margin), scenarios in budget.groupby(["arm", "margin_assumption"], sort=False):
        reference = scenarios.iloc[0]
        net_by_cost = " | ".join(
            f"${row.contact_cost_assumption_usd:.2f} cost: {row.net_per_1000_usd:+,.0f}"
            for row in scenarios.sort_values("contact_cost_assumption_usd").itertuples()
        )
        budget_marks.append((
            f"{margin:.0%} margin · {ARM_LABEL[arm]}",
            reference.breakeven_cost_usd,
            f"95% CI [${reference.breakeven_cost_low_usd:.3f}, "
            f"${reference.breakeven_cost_high_usd:.3f}] | Net USD per 1,000: {net_by_cost}",
        ))
    return [
        ("rates", "Conversion by assignment", "Purchase rate (%)", [
            (ARM_LABEL[r.arm], 100 * r.conversion_rate,
             f"{r.conversions:,} purchases / {r.customers:,} customers")
            for r in rates.itertuples()
        ]),
        ("overall", "Conversion lift", "Difference (percentage points)", [
            (f"{ARM_LABEL[r.arm]} vs {ARM_LABEL[r.baseline]}", r.lift_pp,
             f"95% CI [{r.lift_low_pp:.3f}, {r.lift_high_pp:.3f}] pp | "
             f"Holm-adjusted p = {r.p_holm:.3g}")
            for r in overall.itertuples()
        ]),
        ("segments", "Lift by months since last purchase", "Difference vs no email (percentage points)", [
            (f"{r.audience} · {ARM_LABEL[r.arm]}", r.lift_pp,
             f"95% CI [{r.lift_low_pp:.3f}, {r.lift_high_pp:.3f}] pp | "
             f"Treatment n = {r.customers:,} | Control n = {r.baseline_customers:,}")
            for r in segments.itertuples()
        ]),
        ("budget", "Break-even cost by margin scenario", "USD per assigned customer", budget_marks),
    ]


def add_datasource(parent, key, title, fields):
    source_name = f"federated.{key}"
    datasource = add(parent, "datasource", caption=title, inline="true", name=source_name, version=VERSION)
    connection = add(datasource, "connection", **{"class": "federated"})
    named = add(connection, "named-connections")
    csv_connection = f"textscan.{key}"
    file = f"{key}.csv"
    named = add(named, "named-connection", caption=title, name=csv_connection)
    add(named, "connection", **{
        "class": "textscan", "directory": "Data", "filename": file, "password": "",
        "server": "", "workgroup-auth-mode": "as-is",
    })
    relation = add(connection, "relation", connection=csv_connection, name=file,
                   table=f"[{key}#csv]", type="table")
    columns = add(relation, "columns", **{
        "character-set": "UTF-8", "header": "yes", "locale": "en_US", "separator": ",",
    })
    for ordinal, field in enumerate(fields):
        add(columns, "column", datatype=field["datatype"], name=field["name"][1:-1], ordinal=str(ordinal))
        add(datasource, "column", **field)


def add_text(parent, text, size, color="#172532", bold=False):
    formatted = add(parent, "formatted-text")
    add(formatted, "run", text, fontname="Tableau Book", fontsize=str(size),
        fontcolor=color, bold=str(bold).lower())


def add_id(parent, title):
    identifier = uuid5(NAMESPACE_URL, f"marketing-causal-analytics/{title}")
    add(parent, "simple-id", uuid="{" + str(identifier).upper() + "}")


def add_sheet(parent, key, title, fields):
    sheet = add(parent, "worksheet", name=title)
    add_text(add(add(sheet, "layout-options"), "title"), title, 13, bold=True)
    table = add(sheet, "table")
    view = add(table, "view")
    source = f"federated.{key}"
    add(add(view, "datasources"), "datasource", caption=title, name=source)
    deps = add(view, "datasource-dependencies", datasource=source)
    for field in fields:
        add(deps, "column", **field)

    refs = []
    for field in fields:
        measure = field["role"] == "measure"
        derivation = "Avg" if measure else "None"
        name = "[" + derivation.lower() + ":" + field["name"][1:-1] + (":qk]" if measure else ":nk]")
        add(deps, "column-instance", column=field["name"], derivation=derivation,
            name=name, pivot="key", type=field["type"])
        refs.append(f"[{source}].{name}")

    label, value, detail = refs
    add(view, "aggregation", value="true")
    style = add(table, "style")
    mark_style = add(style, "style-rule", element="mark")
    add(mark_style, "format", attr="mark-labels-show", value="true")
    add(mark_style, "format", attr="mark-labels-cull", value="true")
    panes = add(table, "panes")
    pane = add(panes, "pane", **{"selection-relaxation-option": "selection-relaxation-allow"})
    add(add(pane, "view"), "breakdown", **{"value": "auto"})
    add(pane, "mark", **{"class": "Bar"})
    encodings = add(pane, "encodings")
    add(encodings, "text", column=value)
    add(encodings, "tooltip", column=detail)
    tooltip = add(pane, "customized-tooltip")
    add_text(tooltip, f"<{label}>\n<{value}>\n<{detail}>", 10)
    add(table, "rows", label)
    add(table, "cols", value)
    add_id(sheet, title)


def add_dashboard(root, titles):
    dashboard = add(add(root, "dashboards"), "dashboard", name="Campaign decision")
    add(dashboard, "size", minwidth="1260", maxwidth="1260", minheight="850",
        maxheight="850", **{"sizing-mode": "fixed"})
    zones = add(dashboard, "zones")
    canvas = add(zones, "zone", id="1", x="0", y="0", w="100000", h="100000",
                 **{"type-v2": "layout-flow", "param": "vert"})

    header = add(canvas, "zone", id="2", x="2300", y="1900", w="95400", h="5000",
                 **{"type-v2": "text", "fixed-size": "42", "is-fixed": "true"})
    add_text(header, "Retail email campaign incrementality", 24, bold=True)
    context = add(canvas, "zone", id="3", x="2300", y="7300", w="95400", h="6200",
                  **{"type-v2": "text", "fixed-size": "57", "is-fixed": "true"})
    add_text(context,
             "64,000 customers · 2008 MineThatData randomized experiment · two-week outcomes\n"
             "Retest the men’s email with a no-email holdout. Validate current margin and cost before scaling.",
             12, "#405263")

    for index, (y, height) in enumerate([("15500", "31500"), ("50100", "41800")]):
        row_id = 4 + 3 * index
        row = add(canvas, "zone", id=str(row_id), x="2300", y=y, w="95400", h=height,
                  **{"type-v2": "layout-flow", "param": "horz"})
        for column, x in enumerate(["2300", "51000"]):
            zone = add(row, "zone", name=titles[2 * index + column], id=str(row_id + column + 1),
                       x=x, y=y, w="46700", h=height, **{"show-title": "true"})
            style = add(zone, "zone-style")
            add(style, "format", attr="border-style", value="solid")
            add(style, "format", attr="border-color", value="#D9E2E9")
            add(style, "format", attr="border-width", value="1")
            add(style, "format", attr="margin", value="6")

    source = add(canvas, "zone", id="10", x="2300", y="93800", w="95400", h="4000",
                 **{"type-v2": "text", "fixed-size": "32", "is-fixed": "true"})
    add_text(source, "Source  Kevin Hillstrom, MineThatData (2008). Hover for counts and intervals. Margin is an assumption.", 10, "#405263")
    add(add(canvas, "zone-style"), "format", attr="padding", value="18")
    add_id(dashboard, "Campaign decision")


def add_windows(root, titles):
    windows = add(root, "windows", **{"source-height": "30", "saved-dpi-scale-factor": "1"})
    dashboard = add(windows, "window", name="Campaign decision", **{"class": "dashboard", "maximized": "true"})
    viewpoints = add(dashboard, "viewpoints")
    for title in titles:
        add(add(viewpoints, "viewpoint", name=title), "zoom", type="entire-view")
    add(dashboard, "active", id="-1")
    add_id(dashboard, "Campaign decision")
    for title in titles:
        window = add(windows, "window", name=title, **{"class": "worksheet"})
        cards = add(window, "cards")
        left = add(cards, "edge", name="left")
        strip = add(left, "strip", size="160")
        for card_type in ("pages", "filters", "marks"):
            add(strip, "card", type=card_type)
        top = add(cards, "edge", name="top")
        for card_type in ("columns", "rows"):
            add(add(top, "strip", size="2147483647"), "card", type=card_type)
        add(add(top, "strip", size="31"), "card", type="title")
        add(add(window, "viewpoint"), "zoom", type="entire-view")
        add_id(window, title)


def main():
    root = ET.Element("workbook", {
        "original-version": VERSION, "version": VERSION,
        "source-build": "2026.1.0 (20261.26.0211.1127)", "source-platform": "win",
        "xmlns:user": "http://www.tableausoftware.com/xml/user",
    })
    manifest = add(root, "document-format-change-manifest")
    add(manifest, "SheetIdentifierTracking")
    add(manifest, "WindowsPersistSimpleIdentifiers")
    add(root, "preferences")
    sources = add(root, "datasources")
    worksheets = add(root, "worksheets")
    titles = []
    csv_files = {}
    for key, title, measure, rows in result_views():
        fields = [
            {"name": "[Comparison]", "datatype": "string", "role": "dimension", "type": "nominal"},
            {"name": f"[{measure}]", "datatype": "real", "role": "measure", "type": "quantitative",
             "default-format": "n#,##0.000"},
            {"name": "[Details]", "datatype": "string", "role": "dimension", "type": "nominal"},
        ]
        add_datasource(sources, key, title, fields)
        add_sheet(worksheets, key, title, fields)
        titles.append(title)
        csv_files[f"Data/{key}.csv"] = pd.DataFrame(rows, columns=["Comparison", measure, "Details"])
    add_dashboard(root, titles)
    add_windows(root, titles)
    explain_data = add(root, "explain-data", **{
        "enabled-for-viewer": "false", "extreme-values-enabled-for-all": "false",
    })
    add(explain_data, "explanation-types")
    ET.indent(root, space="  ")
    xml = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    output = ROOT / "tableau" / f"{TITLE}.twbx"
    temporary = output.with_suffix(".tmp")
    with ZipFile(temporary, "w", ZIP_DEFLATED) as package:
        package.writestr(f"{TITLE}.twb", xml)
        for path, data in csv_files.items():
            package.writestr(path, data.to_csv(index=False, float_format="%.12g"))
    temporary.replace(output)
    print(f"Built {output.relative_to(ROOT)} with {len(titles)} views and {len(csv_files)} CSV sources.")


if __name__ == "__main__":
    main()
