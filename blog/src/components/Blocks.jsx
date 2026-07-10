import { Fragment } from "react";

/** 解析段落里的 **加粗** 标记为 <strong> */
function renderInline(text) {
  if (!text) return null;
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((p, i) => {
    if (p.startsWith("**") && p.endsWith("**")) {
      return <strong key={i}>{p.slice(2, -2)}</strong>;
    }
    return <Fragment key={i}>{p}</Fragment>;
  });
}

export default function Blocks({ blocks = [] }) {
  return (
    <div className="blocks">
      {blocks.map((b, i) => {
        switch (b.type) {
          case "paragraph":
            return (
              <p className="b-paragraph" key={i}>
                {renderInline(b.text)}
              </p>
            );
          case "heading":
            return (
              <h2 className="b-heading" key={i}>
                {b.text}
              </h2>
            );
          case "caption":
            return (
              <div className="b-caption" key={i}>
                {b.text}
              </div>
            );
          case "image":
            return (
              <figure className="b-image" key={i}>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={b.url || b.full_url} alt={b.alt || ""} loading="lazy" />
              </figure>
            );
          case "grid":
            return (
              <div
                className="b-grid"
                key={i}
                style={{ gridTemplateColumns: `repeat(${b.columns || 2}, 1fr)` }}
              >
                {(b.items || []).map((it, j) => (
                  <div className="gi" key={j}>
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={it.url || it.full_url} alt="" loading="lazy" />
                    {it.price && <span className="price">{it.price}</span>}
                  </div>
                ))}
              </div>
            );
          default:
            return null;
        }
      })}
    </div>
  );
}
