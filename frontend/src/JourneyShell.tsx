import type { ReactNode } from "react";

export function JourneyLinks({
  active,
}: {
  active: "business" | "prospect" | "member";
}) {
  return (
    <nav className="experience-links" aria-label="Experience journeys">
      {[
        ["prospect", "Prospect"],
        ["member", "Card Member"],
        ["business", "Small Business"],
      ].map(([id, name]) => (
        <a
          key={id}
          href={`?journey=${id}`}
          aria-current={active === id ? "page" : undefined}
        >
          {name}
        </a>
      ))}
    </nav>
  );
}
export function MobileNavigation() {
  return (
    <nav className="mobile-nav" aria-label="Mobile navigation">
      <a href="#top">
        <span>◎</span>Home
      </a>
      <a href="#value">
        <span>◇</span>Value
      </a>
      <a href="#pipeline">
        <span>☷</span>Why
      </a>
      <a href="#preferences">
        <span>⊙</span>Profile
      </a>
    </nav>
  );
}
export function BusinessShell({
  children,
  provider,
}: {
  children: ReactNode;
  provider: string;
}) {
  return (
    <div className="business-shell" id="top">
      <header className="business-topbar">
        <a href="?journey=member" className="business-wordmark">
          intent <span>companion</span>
        </a>
        <span className="demo-badge">
          SYNTHETIC DEMO · {provider.toUpperCase()}
        </span>
      </header>
      <div className="business-body">
        <JourneyLinks active="business" />
        {children}
        <footer className="main-footer">
          <span>Built around your next chapter.</span>
          <p>
            Fictional businesses, cards, suppliers and values. Local
            demonstration only.
          </p>
        </footer>
      </div>
      <MobileNavigation />
    </div>
  );
}
