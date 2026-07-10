import fs from "fs";
import path from "path";

const ARTICLES_DIR = path.join(process.cwd(), "content", "articles");

function readJson(file) {
  try {
    return JSON.parse(fs.readFileSync(file, "utf-8"));
  } catch {
    return null;
  }
}

/** 列出全部文章元数据（按日期倒序） */
export function getAllArticles() {
  if (!fs.existsSync(ARTICLES_DIR)) return [];
  const items = fs
    .readdirSync(ARTICLES_DIR)
    .filter((f) => f.endsWith(".json") && f !== "index.json")
    .map((f) => readJson(path.join(ARTICLES_DIR, f)))
    .filter(Boolean)
    .map((a) => ({
      slug: a.slug || a.entry_id,
      title: a.title,
      date: a.date_iso,
      cover: a.cover_image,
      excerpt: a.excerpt,
      tags: a.tags || [],
      source: a.source,
      author: a.author,
    }));
  items.sort((a, b) => (a.date < b.date ? 1 : a.date > b.date ? -1 : 0));
  return items;
}

/** 按 slug 读取单篇文章完整内容 */
export function getArticle(slug) {
  return readJson(path.join(ARTICLES_DIR, `${slug}.json`));
}

/** 枚举所有 slug，用于静态生成 */
export function getAllSlugs() {
  return getAllArticles().map((a) => a.slug);
}
