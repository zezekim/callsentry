"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { PageHeader } from "@/components/ui";

const SECTIONS = [
  { href: "/settings", label: "Business" },
  { href: "/settings/users", label: "Users" },
  { href: "/settings/calendar", label: "Calendar" },
  { href: "/settings/providers", label: "Provider status" },
  { href: "/settings/platform", label: "Platform configuration" },
  { href: "/settings/account", label: "Your account" },
];

export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  return (
    <div>
      <PageHeader title="Settings" lede="How the receptionist answers, who can administer it, and which services it relies on." />
      <div className="grid gap-8 lg:grid-cols-[14rem_1fr]">
        <nav aria-label="Settings sections" className="subnav">
          <ul>
            {SECTIONS.map((section) => {
              const active = section.href === "/settings" ? pathname === "/settings" : pathname.startsWith(section.href);
              return (
                <li key={section.href}>
                  <Link href={section.href} className={active ? "active" : ""} aria-current={active ? "page" : undefined}>
                    {section.label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>
        <div className="min-w-0">{children}</div>
      </div>
    </div>
  );
}
