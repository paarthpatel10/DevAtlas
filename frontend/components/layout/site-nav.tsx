"use client";

import { Menu, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

const LINKS = [
  { href: "/explore", label: "Explore" },
  { href: "/ask", label: "Ask AI" },
  { href: "/saved", label: "Saved" },
];

function isActive(pathname: string, href: string) {
  if (href === "/explore") return pathname === "/explore" || pathname.startsWith("/repositories");
  return pathname.startsWith(href);
}

export function SiteNav() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  const links = LINKS.map((link) => {
    const active = isActive(pathname, link.href);
    return (
      <li key={link.href}>
        <Link
          href={link.href}
          aria-current={active ? "page" : undefined}
          onClick={() => setOpen(false)}
          className={`block rounded px-3 py-2 text-sm font-medium transition-colors ${
            active ? "bg-accent-soft text-accent" : "text-muted hover:text-ink"
          }`}
        >
          {link.label}
        </Link>
      </li>
    );
  });

  return (
    <nav aria-label="Primary" className="flex items-center">
      <ul className="hidden items-center gap-1 sm:flex">{links}</ul>
      <button
        type="button"
        className="rounded p-2 text-muted hover:text-ink sm:hidden"
        aria-expanded={open}
        aria-controls="mobile-nav"
        onClick={() => setOpen((v) => !v)}
      >
        {open ? <X aria-hidden size={20} /> : <Menu aria-hidden size={20} />}
        <span className="sr-only">{open ? "Close menu" : "Open menu"}</span>
      </button>
      {open && (
        <ul
          id="mobile-nav"
          className="absolute inset-x-0 top-full z-20 border-b border-rule bg-surface px-4 py-2 sm:hidden"
        >
          {links}
        </ul>
      )}
    </nav>
  );
}
