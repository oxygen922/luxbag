import "./globals.css";

export const metadata = {
  title: "KYNBAG · The Latest in Designer Handbags",
  description:
    "Discover and decode the newest handbag releases from the world's leading luxury houses — KYNBAG",
  metadataBase: new URL("https://kynbag.blog"),
  openGraph: {
    title: "KYNBAG · The Latest in Designer Handbags",
    description:
      "Discover and decode the newest handbag releases from the world's leading luxury houses.",
    type: "website",
    url: "https://kynbag.blog",
  },
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>
        <header className="site-header">
          <div className="wrap header-inner">
            <a href="/" className="brand">
              <span className="brand-mark">K</span>
              <span className="brand-name">KYNBAG</span>
            </a>
            <nav className="site-nav">
              <a href="/">Stories</a>
              <a href="/#today">Daily Edit</a>
              <a href="/#feature">Magazine</a>
            </nav>
          </div>
        </header>
        <main className="site-main">{children}</main>
        <footer className="site-footer">
          <div className="wrap">
            <span>© {new Date().getFullYear()} KYNBAG</span>
            <span className="muted">
              Tracking the world of designer handbags · kynbag.blog
            </span>
          </div>
        </footer>
      </body>
    </html>
  );
}
