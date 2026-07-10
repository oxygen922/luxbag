import Link from "next/link";
import { notFound } from "next/navigation";
import { getAllSlugs, getArticle } from "@/lib/content";
import Blocks from "@/components/Blocks";

export function generateStaticParams() {
  return getAllSlugs().map((slug) => ({ slug }));
}

export function generateMetadata({ params }) {
  const a = getArticle(params.slug);
  if (!a) return {};
  return {
    title: a.title,
    description: a.excerpt,
    openGraph: {
      title: a.title,
      description: a.excerpt,
      images: a.cover_image ? [{ url: a.cover_image }] : [],
      type: "article",
    },
  };
}

export default function ArticlePage({ params }) {
  const a = getArticle(params.slug);
  if (!a) notFound();

  return (
    <article className="article wrap">
      <div className="article-head">
        <div className="article-tags">
          {(a.tags || []).map((t) => (
            <span className="pill" key={t}>
              {t}
            </span>
          ))}
        </div>
        <h1 className="article-title">{a.title}</h1>
        <div className="article-meta">
          {a.author ? `${a.author} · ` : ""}
          {a.date_label || a.date_iso}
        </div>
      </div>

      {a.cover_image && (
        <div className="article-hero">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={a.cover_image} alt={a.title} />
        </div>
      )}

      <Blocks blocks={a.blocks} />

      <div className="article-cta">
        <h3>Shop the Best Deals on Designer Bags</h3>
        <p>Find authenticated luxury handbags at unbeatable prices.</p>
        <a href="https://kynbag.com" target="_blank" rel="noopener noreferrer" className="article-cta-btn">
          Visit KYNBAG.com &rarr;
        </a>
      </div>

      <div style={{ maxWidth: "var(--reading)", margin: "48px auto 0" }}>
        <Link href="/" className="back-link">
          ← Back to all stories
        </Link>
      </div>
    </article>
  );
}
