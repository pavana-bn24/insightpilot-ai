/** Renders a readable pandas snippet for a plan step (for the explainability panel). */
export function stepToPandasSnippet(step) {
  const p = step.params || {};
  const q = (v) => {
    if (typeof v === "string") return `"${v}"`;
    return JSON.stringify(v);
  };
  switch (step.action) {
    case "filter":
      return `df = df[df[${q(p.column)}] ${opFor(p.condition)} ${q(p.value)}]`;
    case "group_agg":
      return `df = df.groupby(${q(p.group_by)}, observed=True)["${p.metric}"]\n      .agg("${p.aggregate}").reset_index()`;
    case "sort":
      return `df = df.sort_values(${q(p.column)}, ascending=${p.ascending !== true}).reset_index(drop=True)`;
    case "top_n":
      return `df = df.nlargest(${p.n}, ${q(p.column)})`;
    case "bottom_n":
      return `df = df.nsmallest(${p.n}, ${q(p.column)})`;
    case "time_series":
      return `df = (df.set_index(${q(p.time_col)})\n      .groupby(pd.Grouper(freq="${periodFreq(p.period)}"))["${p.value_col}"]\n      .agg("${p.aggfunc || "sum"}").reset_index())`;
    case "growth":
      return `df["growth_%"] = (df["${p.value_col}"] - df["${p.value_col}"].shift(1))\n      / df["${p.value_col}"].shift(1) * 100`;
    case "correlation":
      return `r = df[["${p.x}", "${p.y}"]].dropna().corr().iloc[0, 1]`;
    case "kpi_margin":
      return `df["profit"] = df["${p.revenue_col}"] - df["${p.cost_col}"]\ndf["profit_margin_%"] = df["profit"] / df["${p.revenue_col}"] * 100`;
    case "rolling":
      return `df["rolling_mean"] = df["${p.column}"].rolling(${p.window}, min_periods=1).mean()`;
    case "compare":
      return `df = df.groupby(${q(p.group_by)}, observed=True)["${p.metric}"].agg("${p.aggregate || "sum"}").reset_index()`;
    case "pivot":
      return `df = df.pivot_table(index=${q(p.index)}, columns=${q(p.columns)},\n      values=${q(p.values)}, aggfunc="${p.aggfunc || "sum"}", fill_value=0)`;
    case "value_counts":
      return `df = df["${p.column}"].value_counts().head(${p.n || 10}).reset_index()`;
    case "describe":
      return `df = df[${p.column ? `"${p.column}"` : "numeric columns"}].describe()`;
    case "insights":
      return `facts = df["${p.metric_col}"].describe()`;
    case "head":
      return `df = df.head(${p.n || 10})`;
    default:
      return `# ${step.action}(${Object.entries(p).map(([k, v]) => `${k}=${typeof v === "string" ? `"${v}"` : JSON.stringify(v)}`).join(", ")})`;
  }
}

function opFor(cond) {
  return {
    eq: "==",
    neq: "!=",
    gt: ">",
    gte: ">=",
    lt: "<",
    lte: "<=",
    in: ".isin()",
    contains: ".str.contains()",
  }[cond] || cond;
}

function periodFreq(period) {
  return { D: "D", W: "W", M: "ME", Q: "QE", Y: "YE" }[period] || "ME";
}
