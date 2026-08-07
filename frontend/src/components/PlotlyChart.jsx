import React from "react";

/** Renders a Plotly figure JSON on a div. Plotly is lazy-loaded so the main
 *  bundle stays small and charts only pull in the library when needed. */
export function PlotlyChart({ figure, height = 420 }) {
  const ref = React.useRef(null);
  const id = React.useRef(`plot_${Math.random().toString(36).slice(2, 10)}`);

  React.useEffect(() => {
    let cancelled = false;
    if (!ref.current || !figure) return undefined;
    import("plotly.js-dist-min")
      .then((mod) => {
        if (cancelled || !ref.current) return;
        const Plotly = mod.default || mod;
        Plotly.react(id.current, figure.data || [], figure.layout || {}, {
          responsive: true,
          displaylogo: false,
          modeBarButtonsToRemove: ["lasso2d", "select2d"],
        });
      })
      .catch((err) => console.error("Failed to load plotly", err));
    return () => {
      cancelled = true;
    };
  }, [figure]);

  return (
    <div
      ref={ref}
      id={id.current}
      className="plotly-container"
      style={{ width: "100%", height }}
    />
  );
}
