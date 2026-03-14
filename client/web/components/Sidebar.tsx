"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  FileText,
  Users,
  Mic,
  Activity,
  Stethoscope,
  ClipboardList,
} from "lucide-react";

const NAV = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/samples", label: "Samples", icon: FileText },
  { href: "/providers", label: "Providers", icon: Users },
  { href: "/specialties", label: "Specialties", icon: Stethoscope },
  { href: "/templates", label: "Templates", icon: ClipboardList },
  { href: "/capture", label: "Capture", icon: Mic },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside
      className="flex flex-col w-60 min-h-screen flex-shrink-0"
      style={{ background: "var(--sidebar-bg)" }}
    >
      {/* Logo / Brand */}
      <div className="flex items-center gap-3 px-5 py-6 border-b border-white/10">
        <Image
          src="/talisman-logo.svg"
          alt="Talisman Solutions"
          width={36}
          height={36}
          className="flex-shrink-0"
        />
        <div>
          <div className="text-white font-semibold text-sm leading-tight">
            Talisman Solutions
          </div>
          <div className="text-white/40 text-xs">AI Scribe Enterprise</div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4 space-y-1">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active =
            href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors"
              style={{
                background: active ? "var(--sidebar-active)" : "transparent",
                color: active ? "#FFFFFF" : "rgba(255,255,255,0.6)",
              }}
              onMouseEnter={(e) => {
                if (!active)
                  (e.currentTarget as HTMLElement).style.background =
                    "var(--sidebar-hover)";
              }}
              onMouseLeave={(e) => {
                if (!active)
                  (e.currentTarget as HTMLElement).style.background =
                    "transparent";
              }}
            >
              <Icon size={16} />
              {label}
            </Link>
          );
        })}
      </nav>

      {/* Version badge */}
      <div className="px-5 py-4 border-t border-white/10">
        <div className="flex items-center gap-2">
          <Activity size={12} className="text-green-400" />
          <span className="text-white/40 text-xs">Pipeline v8 · 4.44/5.0</span>
        </div>
      </div>
    </aside>
  );
}
