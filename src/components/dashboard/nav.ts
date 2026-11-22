import {
  Activity,
  Bell,
  Beaker,
  Briefcase,
  FolderKanban,
  History,
  Landmark,
  LayoutGrid,
  LineChart,
  CreditCard,
  Database,
  Eye,
  FileText,
  Sparkles,
  Settings,
  Users,
  type LucideIcon,
} from "lucide-react";
import { brand } from "@/lib/brand";

export interface DashNav {
  label: string;
  href: string;
  icon: LucideIcon;
  keywords: string;
  status?: "live" | "soon";
}

export const DASH_NAV: DashNav[] = [
  { label: "Overview", href: "/dashboard", icon: LayoutGrid, keywords: "home summary control center personalized dashboard customize", status: "live" },
  { label: brand.products.sports.name, href: "/dashboard/sports", icon: Activity, keywords: "football soccer match fixtures poisson", status: "live" },
  { label: brand.products.strategy.name, href: "/dashboard/business", icon: Briefcase, keywords: "game theory nash payoff pricing", status: "live" },
  { label: brand.products.politics.name, href: "/dashboard/politics", icon: Landmark, keywords: "coalition voting power policy turnout", status: "live" },
  { label: brand.products.markets.name, href: "/dashboard/finance", icon: LineChart, keywords: "portfolio var risk monte carlo stress expected shortfall", status: "live" },
  { label: brand.products.simlab.name, href: "/dashboard/simulations", icon: Beaker, keywords: "monte carlo seed scenario", status: "live" },
  { label: "AI Analyst", href: "/dashboard/analyst", icon: Sparkles, keywords: "ask chat assistant explain questions analyst sources", status: "live" },
  { label: "Watchlists", href: "/dashboard/watchlists", icon: Eye, keywords: "watch follow track clubs teams fixtures companies indicators elections instruments favourites", status: "live" },
  { label: "Reports", href: "/dashboard/reports", icon: FileText, keywords: "evidence provenance backtest accuracy export print briefings library saved intelligence", status: "live" },
  { label: "Notifications", href: "/dashboard/notifications", icon: Bell, keywords: "alerts rules inbox unread quiet hours", status: "live" },
  { label: "Data", href: "/dashboard/data", icon: Database, keywords: "upload csv import dataset results prices returns seats series", status: "live" },
  { label: "Settings", href: "/dashboard/settings", icon: Settings, keywords: "account profile preferences quiet hours briefings", status: "live" },
  { label: "Prediction History", href: "/dashboard/history", icon: History, keywords: "forecasts past saved", status: "live" },
  { label: "My Workspace", href: "/dashboard/workspace", icon: FolderKanban, keywords: "team members organization library", status: "live" },
  { label: "Team", href: "/dashboard/team", icon: Users, keywords: "members invite roles comments activity colleagues", status: "live" },
  { label: "Plan & Billing", href: "/dashboard/billing", icon: CreditCard, keywords: "subscription upgrade payment invoice stripe", status: "live" },
];

/** Quick actions offered by global search (a verb the person might type), alongside pages. */
export const QUICK_ACTIONS: { label: string; href: string; keywords: string }[] = [
  { label: "Ask the AI Analyst", href: "/dashboard/analyst", keywords: "ask question chat" },
  { label: "Add to a watchlist", href: "/dashboard/watchlists", keywords: "add watch follow track" },
  { label: "Generate a briefing", href: "/dashboard/reports?tab=briefings", keywords: "briefing brief daily weekly" },
  { label: "Switch on alerts", href: "/dashboard/notifications", keywords: "alert notify rules" },
  { label: "Import football data", href: "/dashboard/data", keywords: "import upload csv results" },
  { label: "Run a simulation", href: "/dashboard/simulations", keywords: "simulate scenario run" },
  { label: "Saved intelligence library", href: "/dashboard/reports?tab=library", keywords: "saved library search export delete" },
];
