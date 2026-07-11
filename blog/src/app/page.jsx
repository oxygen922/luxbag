import Link from "next/link";
import { getAllArticles } from "@/lib/content";

export default function HomePage() {
  const articles = getAllArticles();
  const feature = articles.filter((a) => a.source === "feature");
  const today = articles.filter((a) => a.source === "today");

  return (
    <div className="wrap">
      <section className="hero">
        <h1>KYNBAG</h1>
        <p>Discover · Decode · The newest designer handbags</p>
      </section>

      <a href="https://kynbag.com" className="shop-cta" target="_blank" rel="noopener noreferrer">
        <span className="shop-cta-text">
          Looking for the best deals on luxury bags?
          <strong> Shop KYNBAG.com &rarr;</strong>
        </span>
      </a>

      {today.length > 0 && (
        <section id="today">
          <h2 className="section-title">Daily Edit · TODAY</h2>
          <div className="grid">
            {today.map((a) => (
              <Card key={a.slug} a={a} />
            ))}
          </div>
        </section>
      )}

      {feature.length > 0 && (
        <section id="feature">
          <h2 className="section-title">Magazine · FEATURE</h2>
          <div className="grid">
            {feature.map((a) => (
              <Card key={a.slug} a={a} />
            ))}
          </div>
        </section>
      )}

      {articles.length === 0 && (
        <p style={{ textAlign: "center", color: "var(--muted)", padding: "60px 0" }}>
          No stories yet. Run the collector <code>python main.py run</code> and content will appear here.
        </p>
      )}
    </div>
  );
}

function Card({ a }) {
  return (
    <Link href={`/articles/${a.slug}/`} className="card">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img className="card-cover" src={a.cover} alt={a.title} loading="lazy" />
      <div className="card-body">
        {a.tags?.[0] && <span className="card-tag">{a.tags[0]}</span>}
        <h3 className="card-title">{a.title}</h3>
        {a.excerpt && <p className="card-excerpt">{a.excerpt}</p>}
        <div className="card-date">{a.date}</div>
      </div>
    </Link>
  );
}
